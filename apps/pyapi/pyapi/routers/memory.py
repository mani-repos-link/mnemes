from __future__ import annotations

import logging

from pyapi.config import ContextConfig
from pyapi.context import build_memory_content, build_rag_query
from pyapi.providers import EmbeddingProvider
from pyapi.store import MemoryItemRecord, MessageRecord, Store

logger = logging.getLogger("pyapi.routes.memory")


async def retrieve_memories_for_message(
    store: Store,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
    message: MessageRecord,
    exclude_source_ids: set[str] | None = None,
) -> list[MemoryItemRecord]:
    if not context.enable_retrieval or context.retrieval_top_k <= 0:
        return []

    try:
        if not store.has_indexed_memory(message.session_id, embedding_provider.model, embedding_provider.provider):
            logger.info(
                "retrieval skipped session_id=%s message_id=%s reason=no_indexed_memory",
                message.session_id,
                message.id,
            )
            return []

        query = build_rag_query(message, context.memory_max_chars)
        result = await embedding_provider.embed([query])
        if not result.embeddings:
            return []

        memories = store.search_memory_items(
            message.session_id,
            result.embeddings[0],
            result.model,
            result.provider,
            limit=context.retrieval_top_k,
            min_score=context.retrieval_min_score,
            exclude_source_ids=exclude_source_ids,
        )
        logger.info(
            "retrieval done session_id=%s message_id=%s memories=%d",
            message.session_id,
            message.id,
            len(memories),
        )
        return memories
    except Exception:
        logger.exception("retrieval failed session_id=%s message_id=%s", message.session_id, message.id)
        return []


async def index_messages_for_retrieval(
    store: Store,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
    messages: list[MessageRecord],
) -> None:
    if not context.enable_retrieval:
        return

    items = [
        (message, build_memory_content(message, context.memory_max_chars))
        for message in messages
        if message.role in {"user", "assistant"}
    ]
    if not items:
        return

    try:
        result = await embedding_provider.embed([content for _message, content in items])
        for (message, content), embedding in zip(items, result.embeddings, strict=True):
            store.upsert_memory_item(
                message.session_id,
                "message",
                message.id,
                content,
                embedding,
                result.model,
                result.provider,
            )
    except Exception:
        logger.exception("memory indexing failed messages=%d", len(items))
