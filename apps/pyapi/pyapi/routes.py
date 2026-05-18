from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Response

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
    async def list_messages(session_id: str) -> dict[str, list[dict[str, str | None]]]:
        try:
            messages = store.list_messages(session_id)
        except NotFoundError as err:
            raise HTTPException(status_code=404, detail="session not found") from err
        return {"messages": [message.to_api() for message in messages]}

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
                history = store.list_messages(session_id)
                history = history[-context.recent_message_limit :]
                result = await chat_provider.complete(history, context.max_response_tokens)
                assistant_message = store.create_message(
                    session_id,
                    "assistant",
                    result.content,
                    provider=result.provider,
                    model=result.model,
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

    return router
