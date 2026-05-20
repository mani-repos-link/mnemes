from __future__ import annotations

from dataclasses import dataclass

from pyapi.config import ContextConfig
from pyapi.providers import ChatProvider, EmbeddingProvider
from pyapi.store import Store


@dataclass(frozen=True)
class AppServices:
    store: Store
    chat_provider: ChatProvider
    embedding_provider: EmbeddingProvider
    context: ContextConfig
