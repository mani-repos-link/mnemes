from __future__ import annotations

import logging

from pyapi.config import ContextConfig
from pyapi.context import build_memory_content, build_rag_query, context_memory_buffer_limit, context_memory_raw_limit, messages_for_memory_index_update
from pyapi.providers import EmbeddingProvider
from pyapi.store import MemoryItemRecord, MessageRecord, Store

logger = logging.getLogger("pyapi.routes.memory")


async def retrieve_memories_for_message(
    store: Store,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
    message: MessageRecord,
    context_message_count: int,
    exclude_source_ids: set[str] | None = None,
) -> list[MemoryItemRecord]:
    if context_message_count < context_memory_raw_limit(context) + context_memory_buffer_limit(context):
        logger.info(
            "retrieval skipped session_id=%s message_id=%s reason=below_memory_trigger messages=%d trigger=%d",
            message.session_id,
            message.id,
            context_message_count,
            context.context_memory_trigger_message_limit,
        )
        return []
    if context.retrieval_top_k <= 0:
        return []
    if context.enable_vectorless_retrieval:
        return retrieve_vectorless_memories(store, context, message, exclude_source_ids)
    if not context.enable_retrieval:
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


def retrieve_vectorless_memories(
    store: Store,
    context: ContextConfig,
    message: MessageRecord,
    exclude_source_ids: set[str] | None = None,
) -> list[MemoryItemRecord]:
    try:
        if not store.has_text_memory(message.session_id):
            logger.info(
                "vectorless retrieval skipped session_id=%s message_id=%s reason=no_text_memory",
                message.session_id,
                message.id,
            )
            return []

        memories = store.search_text_memory_items(
            message.session_id,
            build_rag_query(message, context.memory_max_chars),
            limit=context.retrieval_top_k,
            exclude_source_ids=exclude_source_ids,
        )
        logger.info(
            "vectorless retrieval done session_id=%s message_id=%s memories=%d",
            message.session_id,
            message.id,
            len(memories),
        )
        return memories
    except Exception:
        logger.exception("vectorless retrieval failed session_id=%s message_id=%s", message.session_id, message.id)
        return []


async def index_messages_for_retrieval(
    store: Store,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
    messages: list[MessageRecord],
) -> None:
    indexed_source_ids = indexed_memory_source_ids_for_context(store, embedding_provider, context, messages)
    if indexed_source_ids is None:
        return

    messages = messages_for_memory_index_update(messages, indexed_source_ids, context)
    if not messages:
        return

    if context.enable_vectorless_retrieval:
        index_messages_for_vectorless_retrieval(store, context, messages)
        return
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


def index_messages_for_vectorless_retrieval(
    store: Store,
    context: ContextConfig,
    messages: list[MessageRecord],
) -> None:
    items = [
        (message, build_memory_content(message, context.memory_max_chars))
        for message in messages
        if message.role in {"user", "assistant"}
    ]
    if not items:
        return

    try:
        for message, content in items:
            store.upsert_text_memory_item(
                message.session_id,
                "message",
                message.id,
                content,
            )
    except Exception:
        logger.exception("vectorless memory indexing failed messages=%d", len(items))


def indexed_memory_source_ids_for_context(
    store: Store,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
    messages: list[MessageRecord],
) -> set[str] | None:
    if not (context.enable_retrieval or context.enable_vectorless_retrieval):
        return None

    source_ids = [message.id for message in messages if message.role in {"user", "assistant"}]
    if not source_ids:
        return set()

    if context.enable_vectorless_retrieval:
        return store.list_text_memory_source_ids(messages[0].session_id, source_ids)

    return store.list_indexed_memory_source_ids(
        messages[0].session_id,
        source_ids,
        embedding_provider.model,
        embedding_provider.provider,
    )
