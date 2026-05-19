from __future__ import annotations

from pyapi.config import ChatConfig

from .huggingface import HuggingFaceProvider
from .openrouter import OpenRouterProvider
from .types import ChatProvider, ChatResult


def create_chat_provider(config: ChatConfig) -> ChatProvider:
    if config.provider == "openrouter":
        return OpenRouterProvider(config)
    if config.provider == "huggingface":
        return HuggingFaceProvider(config)
    return UnsupportedProvider(config.provider)


class UnsupportedProvider:
    def __init__(self, provider: str):
        self.provider = provider
        self.model = ""

    async def complete(self, *_object: object) -> ChatResult:
        raise ValueError(f'unsupported chat provider "{self.provider}"')
