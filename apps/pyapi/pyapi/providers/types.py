from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyapi.store import MessageRecord


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str


MODEL_EMPTY_RESPONSE_MESSAGE = (
    "I'm sorry, I couldn't generate a useful response for that request. "
    "Please rephrase it or add a little more context."
)


class EmptyModelResponseError(ValueError):
    def __init__(self, provider: str):
        super().__init__(f"{provider} returned an empty message")
        self.provider = provider


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    provider: str
    model: str


class ChatProvider(Protocol):
    provider: str
    model: str

    async def complete(self, history: list[MessageRecord], max_response_tokens: int) -> ChatResult: ...


class EmbeddingProvider(Protocol):
    provider: str
    model: str

    async def embed(self, inputs: list[str]) -> EmbeddingResult: ...
