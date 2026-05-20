from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException

from pyapi.context import messages_for_memory_index_update, messages_for_summary_update
from pyapi.store import MemoryItemRecord, MessageRecord, NotFoundError

from pyapi.dependencies import AppServices
from pyapi.services import (
    index_messages_for_retrieval,
    indexed_memory_source_ids_for_context,
    update_summary_if_needed,
)

logger = logging.getLogger("pyapi.routes.metrics")


def create_metrics_router(services: AppServices) -> APIRouter:
    router = APIRouter()
    store = services.store

    @router.get("/api/sessions/{session_id}/metrics")
    async def get_session_metrics(session_id: str) -> dict[str, object]:
        try:
            session = store.get_session(session_id)
            messages = store.list_context_messages(session_id)
            memory_items = store.list_memory_items(session_id)
            summary = store.get_session_summary(session_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err

        indexed_source_ids = indexed_memory_source_ids_for_context(
            store,
            services.embedding_provider,
            services.context,
            messages,
        )
        pending_memory = (
            messages_for_memory_index_update(messages, indexed_source_ids, services.context)
            if indexed_source_ids is not None
            else []
        )
        pending_summary = messages_for_summary_update(messages, summary, services.context)
        return build_session_metrics(
            session.to_api(),
            messages,
            memory_items,
            summary,
            indexed_source_ids or set(),
            {message.id for message in pending_memory},
            {message.id for message in pending_summary},
            services.context.memory_mode,
            services.context.context_memory_trigger_message_limit,
            services.context.context_memory_buffer_message_limit,
        )

    @router.post("/api/sessions/{session_id}/metrics/generate", status_code=202)
    async def generate_session_memory(session_id: str) -> dict[str, object]:
        try:
            store.get_session(session_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err

        if services.context.enable_retrieval or services.context.enable_vectorless_retrieval:
            await index_messages_for_retrieval(
                store,
                services.embedding_provider,
                services.context,
                store.list_context_messages(session_id),
            )
        if services.context.enable_summaries:
            await update_summary_if_needed(store, services.chat_provider, services.context, session_id)

        return await get_session_metrics(session_id)

    return router


def build_session_metrics(
    session: dict[str, str],
    messages: list[MessageRecord],
    memory_items: list[MemoryItemRecord],
    summary: object,
    indexed_source_ids: set[str],
    pending_memory_ids: set[str],
    pending_summary_ids: set[str],
    memory_mode: str,
    trigger_limit: int,
    buffer_limit: int,
) -> dict[str, object]:
    memory_by_source = {item.source_id: item for item in memory_items}
    summarized_source_ids = (
        summarized_message_ids(messages, summary_to_covered_message_id(summary)) if memory_mode == "summary" else set()
    )
    vector_items = [item for item in memory_items if item.embedding_dim is not None]
    text_items = [item for item in memory_items if item.embedding_provider == "vectorless"]
    summary_items = [item for item in memory_items if item.source_type == "summary"]
    keywords = top_keywords(messages)
    raw_count = min(len(messages), trigger_limit)
    compacted_count = max(0, len(messages) - raw_count)

    return {
        "session": session,
        "config": {
            "memoryMode": memory_mode,
            "triggerMessageLimit": trigger_limit,
            "bufferMessageLimit": buffer_limit,
        },
        "stats": {
            "totalMessages": len(messages),
            "userMessages": sum(1 for message in messages if message.role == "user"),
            "assistantMessages": sum(1 for message in messages if message.role == "assistant"),
            "rawMessageWindow": raw_count,
            "compactedMessageEstimate": compacted_count,
            "indexedTextMemories": len(text_items),
            "indexedVectorMemories": len(vector_items),
            "totalEmbeddings": len(vector_items),
            "summaries": len(summary_items),
            "pendingMemoryMessages": len(pending_memory_ids),
            "pendingSummaryMessages": len(pending_summary_ids),
            "activeMemoryMessages": len(indexed_source_ids) + len(summarized_source_ids),
            "inactiveVectorMemories": 0 if memory_mode == "rag-vector" else len(vector_items),
            "inactiveSummaries": 0 if memory_mode == "summary" else len(summary_items),
        },
        "summary": summary_to_api(summary, active=memory_mode == "summary"),
        "keywords": keywords,
        "messages": [
            {
                **message.to_api(),
                "preview": preview_text(message.content),
                "memoryStatus": message_memory_status(
                    message,
                    memory_by_source,
                    summarized_source_ids,
                    indexed_source_ids,
                    pending_memory_ids,
                    pending_summary_ids,
                    memory_mode,
                ),
            }
            for message in messages
        ],
    }


def summary_to_api(summary: object, active: bool) -> dict[str, str | bool | None] | None:
    if summary is None:
        return None
    return {
        "id": summary.id,
        "content": summary.content,
        "preview": preview_text(summary.content, 240),
        "coveredMessageId": summary.covered_message_id,
        "createdAt": summary.created_at,
        "updatedAt": summary.updated_at,
        "active": active,
    }


def message_memory_status(
    message: MessageRecord,
    memory_by_source: dict[str, MemoryItemRecord],
    summarized_source_ids: set[str],
    indexed_source_ids: set[str],
    pending_memory_ids: set[str],
    pending_summary_ids: set[str],
    memory_mode: str,
) -> str:
    if message.id in summarized_source_ids:
        return "summarized"
    if message.id in indexed_source_ids:
        return "indexed-vector" if memory_mode == "rag-vector" else "indexed-text"
    if message.id in pending_memory_ids:
        return "pending-index"
    if message.id in pending_summary_ids:
        return "pending-summary"
    memory = memory_by_source.get(message.id)
    if memory is not None:
        return "inactive-vector" if memory.embedding_dim is not None else "inactive-text"
    return "raw"


def summary_to_covered_message_id(summary: object) -> str | None:
    if summary is None:
        return None
    return summary.covered_message_id


def summarized_message_ids(messages: list[MessageRecord], covered_message_id: str | None) -> set[str]:
    if not covered_message_id:
        return set()

    ids: set[str] = set()
    for message in messages:
        ids.add(message.id)
        if message.id == covered_message_id:
            break
    return ids


def preview_text(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def top_keywords(messages: list[MessageRecord], limit: int = 16) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for message in messages:
        if message.role != "user":
            continue
        for word in keyword_terms(message.content):
            counts[word] = counts.get(word, 0) + 1
    return [
        {"term": term, "count": count}
        for term, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


KEYWORD_STOPWORDS = frozenset(
    {
        "about", "after", "all", "also", "and", "any", "are", "because", "before", "but",
        "can", "could", "did", "does", "don", "for", "from", "get", "got", "great",
        "have", "how", "into", "just", "know", "like", "mean", "more", "not", "now",
        "okay", "ok", "our", "out", "should", "so", "that", "the", "their", "then",
        "there", "they", "this", "want", "wanted", "was", "were", "what", "when",
        "with", "would", "you", "your",
    }
)


def keyword_terms(value: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", value.lower())
        if term not in KEYWORD_STOPWORDS
    ]
