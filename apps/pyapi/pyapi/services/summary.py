from __future__ import annotations

import logging

from pyapi.config import ContextConfig
from pyapi.context import messages_for_summary_update
from pyapi.providers import ChatProvider, EmptyModelResponseError
from pyapi.store import MessageRecord, SessionSummaryRecord, Store

logger = logging.getLogger("pyapi.routes.summaries")


async def update_summary_if_needed(
    store: Store,
    chat_provider: ChatProvider,
    context: ContextConfig,
    session_id: str,
) -> None:
    if not context.enable_summaries:
        return

    try:
        current_summary = store.get_session_summary(session_id)
        context_messages = store.list_context_messages(session_id)
        messages_to_summarize = messages_for_summary_update(context_messages, current_summary, context)
        if not messages_to_summarize:
            return

        summary_result = await chat_provider.complete(
            build_summary_prompt(current_summary, messages_to_summarize),
            max_response_tokens=900,
        )
        store.upsert_session_summary(
            session_id,
            summary_result.content,
            messages_to_summarize[-1].id,
        )
    except EmptyModelResponseError:
        logger.warning("summary update skipped because model returned empty content session_id=%s", session_id)
    except Exception:
        logger.exception("summary update failed session_id=%s", session_id)


def build_summary_prompt(
    current_summary: SessionSummaryRecord | None,
    messages: list[MessageRecord],
) -> list[MessageRecord]:
    transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
    existing_summary = current_summary.content if current_summary else "No existing summary."

    return [
        MessageRecord(
            id="summary_instruction",
            session_id=messages[0].session_id,
            role="system",
            content=(
                "You maintain compact long-term memory for a local chatbot. "
                "Update the existing summary using the new transcript. Preserve facts, user preferences, "
                "decisions, open tasks, names, constraints, and corrections. Do not invent details."
            ),
            provider=None,
            model=None,
            parent_message_id=None,
            active_response_id=None,
            created_at=messages[0].created_at,
        ),
        MessageRecord(
            id="summary_request",
            session_id=messages[0].session_id,
            role="user",
            content=(
                "Existing summary:\n"
                f"{existing_summary}\n\n"
                "New transcript to merge:\n"
                f"{transcript}\n\n"
                "Return only the updated summary. Keep it concise but specific."
            ),
            provider=None,
            model=None,
            parent_message_id=None,
            active_response_id=None,
            created_at=messages[-1].created_at,
        ),
    ]
