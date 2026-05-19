from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query, Response

from .config import ContextConfig
from .providers import ChatProvider
from .schemas import CreateMessageRequest, CreateSessionRequest
from .store import NotFoundError, Store

logger = logging.getLogger("pyapi.routes")


def create_router(store: Store, chat_provider: ChatProvider, context: ContextConfig) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/providers")
    async def providers() -> dict[str, list[str]]:
        return {"chat": ["openrouter", "huggingface"], "embedding": ["openrouter", "huggingface"]}

    @router.get("/api/sessions")
    async def list_sessions() -> dict[str, list[dict[str, str]]]:
        return {"sessions": [session.to_api() for session in store.list_sessions()]}

    @router.post("/api/sessions", status_code=201)
    async def create_session(request: CreateSessionRequest) -> dict[str, dict[str, str]]:
        return {"session": store.create_session(request.title).to_api()}

    @router.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> Response:
        try:
            store.delete_session(session_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err
        logger.info("session deleted session_id=%s", session_id)
        return Response(status_code=204)

    @router.get("/api/sessions/{session_id}/messages")
    async def list_messages(
        session_id: str,
        limit: int = Query(default=15, ge=1, le=100),
        before: str | None = None,
    ) -> dict[str, object]:
        try:
            messages, has_more = store.list_messages_page(session_id, limit=limit, before=before)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err
        return {
            "messages": [message.to_api() for message in messages],
            "page": {
                "hasMore": has_more,
                "nextBefore": messages[0].created_at if has_more and messages else None,
            },
        }

    @router.post("/api/sessions/{session_id}/messages", status_code=201)
    async def create_message(session_id: str, request: CreateMessageRequest) -> dict[str, object]:
        started = time.monotonic()
        logger.info(
            "message create start session_id=%s role=%s content_chars=%d",
            session_id,
            request.role,
            len(request.content),
        )

        try:
            user_message = store.create_message(session_id, request.role, request.content)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

        messages = [user_message]
        if request.role == "user":
            try:
                history = store.list_context_messages(session_id)
                history = history[-context.recent_message_limit :]
                result = await chat_provider.complete(history, context.max_response_tokens)
                assistant_message = store.create_message(
                    session_id,
                    "assistant",
                    result.content,
                    provider=result.provider,
                    model=result.model,
                    parent_message_id=user_message.id,
                    make_active=True,
                )
            except Exception as err:
                logger.exception("message create chat_error session_id=%s", session_id)
                raise HTTPException(status_code=502, detail=str(err)) from err
            messages.append(assistant_message)

        logger.info(
            "message create done session_id=%s returned_messages=%d duration=%.3fs",
            session_id,
            len(messages),
            time.monotonic() - started,
        )
        return {"message": user_message.to_api(), "messages": [message.to_api() for message in messages]}

    @router.post("/api/sessions/{session_id}/messages/{message_id}/activate")
    async def activate_message(session_id: str, message_id: str) -> dict[str, dict[str, str | None]]:
        try:
            message = store.set_active_response(session_id, message_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="message not found") from err
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {"message": message.to_api()}

    @router.post("/api/sessions/{session_id}/messages/{message_id}/regenerate", status_code=201)
    async def regenerate_message(session_id: str, message_id: str) -> dict[str, object]:
        started = time.monotonic()
        try:
            history = store.list_messages(session_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err

        target_index = next((index for index, message in enumerate(history) if message.id == message_id), None)
        if target_index is None:
            raise HTTPException(status_code=404, detail="message not found")

        anchor_index = target_index
        if history[target_index].role == "assistant":
            parent_id = history[target_index].parent_message_id
            anchor_index = (
                next((index for index, message in enumerate(history) if message.id == parent_id), -1)
                if parent_id
                else next(
                    (
                        index
                        for index in range(target_index - 1, -1, -1)
                        if history[index].role == "user"
                    ),
                    -1,
                )
            )
            if anchor_index < 0:
                raise HTTPException(status_code=400, detail="no user message to regenerate from")
        elif history[target_index].role != "user":
            raise HTTPException(status_code=400, detail="only user or assistant messages can be regenerated")

        try:
            anchor_user = history[anchor_index]
            context_history = store.list_context_messages(session_id, through_user_message_id=anchor_user.id)
            context_history = context_history[-context.recent_message_limit :]
            result = await chat_provider.complete(context_history, context.max_response_tokens)
            assistant_message = store.create_message(
                session_id,
                "assistant",
                result.content,
                provider=result.provider,
                model=result.model,
                parent_message_id=anchor_user.id,
                make_active=True,
            )
        except Exception as err:
            logger.exception("message regenerate chat_error session_id=%s message_id=%s", session_id, message_id)
            raise HTTPException(status_code=502, detail=str(err)) from err

        logger.info(
            "message regenerate done session_id=%s message_id=%s duration=%.3fs",
            session_id,
            message_id,
            time.monotonic() - started,
        )
        return {"message": assistant_message.to_api()}

    return router
