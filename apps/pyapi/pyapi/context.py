from __future__ import annotations

from .config import ContextConfig
from .store import MemoryItemRecord, MessageRecord, SessionSummaryRecord


def build_llm_context(
    messages: list[MessageRecord],
    summary: SessionSummaryRecord | None,
    config: ContextConfig,
    memories: list[MemoryItemRecord] | None = None,
) -> list[MessageRecord]:
    if summary is None and config.enable_summaries and len(messages) <= config.summary_trigger_message_limit:
        recent_messages = messages
    else:
        recent_messages = messages[-config.recent_message_limit :]
    system_messages: list[MessageRecord] = []

    if summary is not None:
        system_messages.append(
            MessageRecord(
                id=f"summary_{summary.id}",
                session_id=summary.session_id,
                role="system",
                content=(
                    "Relevant summary of earlier conversation. Use this as background context, "
                    "but prefer the recent messages when they conflict.\n\n"
                    f"{summary.content}"
                ),
                provider=None,
                model=None,
                parent_message_id=None,
                active_response_id=None,
                created_at=summary.updated_at,
            )
        )

    if memories:
        system_messages.append(
            MessageRecord(
                id="retrieved_memory",
                session_id=memories[0].session_id,
                role="system",
                content=(
                    "Relevant retrieved memory from this chat. Use these snippets only when they help answer "
                    "the current user request. Recent messages are more authoritative.\n\n"
                    f"{format_retrieved_memories(memories, config)}"
                ),
                provider=None,
                model=None,
                parent_message_id=None,
                active_response_id=None,
                created_at=memories[0].updated_at,
            ),
        )

    return [*system_messages, *recent_messages]


def format_retrieved_memories(memories: list[MemoryItemRecord], config: ContextConfig) -> str:
    blocks: list[str] = []
    for index, memory in enumerate(memories, start=1):
        score = f"{memory.score:.3f}" if memory.score is not None else "unknown"
        content = memory.content[: config.memory_max_chars]
        blocks.append(f"[{index}] source={memory.source_type} similarity={score}\n{content}")
    return "\n\n".join(blocks)


def build_memory_content(message: MessageRecord, max_chars: int) -> str:
    role = "User" if message.role == "user" else "Assistant" if message.role == "assistant" else message.role.title()
    content = message.content.strip()
    if len(content) > max_chars:
        content = f"{content[:max_chars].rstrip()}..."
    return f"{role}: {content}"


def build_rag_query(message: MessageRecord, max_chars: int) -> str:
    content = message.content.strip()
    if len(content) > max_chars:
        content = content[:max_chars]
    return content


def messages_for_summary_update(
    messages: list[MessageRecord],
    summary: SessionSummaryRecord | None,
    config: ContextConfig,
) -> list[MessageRecord]:
    if len(messages) < config.summary_trigger_message_limit:
        return []

    covered_message_id = summary.covered_message_id if summary else None
    unsummarized = messages_after(messages, covered_message_id)
    if len(unsummarized) <= config.summary_keep_recent_messages:
        return []

    return unsummarized[: -config.summary_keep_recent_messages]


def messages_after(messages: list[MessageRecord], message_id: str | None) -> list[MessageRecord]:
    if not message_id:
        return messages

    for index, message in enumerate(messages):
        if message.id == message_id:
            return messages[index + 1 :]

    return messages
