from __future__ import annotations

from fastapi import APIRouter

from pyapi.config import ContextConfig
from pyapi.providers import ChatProvider, EmbeddingProvider
from pyapi.store import Store

from .dependencies import RouterServices
from .sessions import create_sessions_router


def create_router(
    store: Store,
    chat_provider: ChatProvider,
    embedding_provider: EmbeddingProvider,
    context: ContextConfig,
) -> APIRouter:
    services = RouterServices(
        store=store,
        chat_provider=chat_provider,
        embedding_provider=embedding_provider,
        context=context,
    )
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/providers")
    async def providers() -> dict[str, object]:
        return {
            "chat": ["openrouter", "huggingface"],
            "embedding": ["openrouter", "huggingface"],
            "active": {
                "chat": {"provider": chat_provider.provider, "model": chat_provider.model},
                "embedding": {"provider": embedding_provider.provider, "model": embedding_provider.model},
                "memory": {"mode": context.memory_mode},
            },
        }

    router.include_router(create_sessions_router(services))
    return router


__all__ = ["create_router"]
