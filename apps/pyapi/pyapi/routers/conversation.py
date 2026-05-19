from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from pyapi.context import build_llm_context
from pyapi.providers import MODEL_EMPTY_RESPONSE_MESSAGE, ChatResult, EmptyModelResponseError
from pyapi.store import MessageRecord, NotFoundError

from .dependencies import RouterServices
from .memory import index_messages_for_retrieval, retrieve_memories_for_message
from .summaries import update_summary_if_needed
from .titles import title_session_from_first_prompt


@dataclass(frozen=True)
class AssistantResponseResult:
    user_message: MessageRecord
    assistant_message: MessageRecord
    after_response: Callable[[], Awaitable[None]]


async def answer_user_message(
    services: RouterServices,
    session_id: str,
    user_message: MessageRecord,
    *,
    update_title: bool,
) -> AssistantResponseResult:
    store = services.store
    if update_title:
        title_session_from_first_prompt(store, session_id, user_message.content)

    context_messages = store.list_context_messages(session_id, through_user_message_id=user_message.id)
    return await create_assistant_response(services, session_id, user_message, context_messages)


async def regenerate_assistant_response(
    services: RouterServices,
    session_id: str,
    message_id: str,
) -> AssistantResponseResult:
    history = services.store.list_messages(session_id)
    anchor_user = find_regeneration_anchor(history, message_id)
    context_messages = services.store.list_context_messages(session_id, through_user_message_id=anchor_user.id)
    return await create_assistant_response(services, session_id, anchor_user, context_messages)


async def create_assistant_response(
    services: RouterServices,
    session_id: str,
    user_message: MessageRecord,
    context_messages: list[MessageRecord],
) -> AssistantResponseResult:
    store = services.store
    memories = await retrieve_memories_for_message(
        store,
        services.embedding_provider,
        services.context,
        user_message,
        exclude_source_ids={user_message.id},
    )
    summary = store.get_session_summary(session_id) if services.context.enable_summaries else None
    history = build_llm_context(
        context_messages,
        summary,
        services.context,
        memories,
    )
    result = await complete_with_fallback(services, history)
    assistant_message = store.create_message(
        session_id,
        "assistant",
        result.content,
        provider=result.provider,
        model=result.model,
        parent_message_id=user_message.id,
        make_active=True,
    )
    return AssistantResponseResult(
        user_message=user_message,
        assistant_message=assistant_message,
        after_response=lambda: run_post_response_maintenance(services, session_id, user_message, assistant_message),
    )


async def run_post_response_maintenance(
    services: RouterServices,
    session_id: str,
    user_message: MessageRecord,
    assistant_message: MessageRecord,
) -> None:
    store = services.store
    if services.context.enable_retrieval:
        await index_messages_for_retrieval(
            store,
            services.embedding_provider,
            services.context,
            [user_message, assistant_message],
        )
    if services.context.enable_summaries:
        await update_summary_if_needed(
            store,
            services.chat_provider,
            services.context,
            session_id,
        )


async def complete_with_fallback(
    services: RouterServices,
    history: list[MessageRecord],
) -> ChatResult:
    try:
        return await services.chat_provider.complete(history, services.context.max_response_tokens)
    except EmptyModelResponseError:
        return ChatResult(
            content=MODEL_EMPTY_RESPONSE_MESSAGE,
            provider=services.chat_provider.provider,
            model=services.chat_provider.model,
        )


def find_regeneration_anchor(history: list[MessageRecord], message_id: str) -> MessageRecord:
    target_index = next((index for index, message in enumerate(history) if message.id == message_id), None)
    if target_index is None:
        raise NotFoundError("message not found")

    target = history[target_index]
    if target.role == "user":
        return target
    if target.role != "assistant":
        raise ValueError("only user or assistant messages can be regenerated")

    parent_id = target.parent_message_id
    if parent_id:
        anchor = next((message for message in history if message.id == parent_id), None)
        if anchor is not None:
            return anchor

    anchor = next(
        (message for message in reversed(history[:target_index]) if message.role == "user"),
        None,
    )
    if anchor is None:
        raise ValueError("no user message to regenerate from")
    return anchor
