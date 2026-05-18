from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyapi.store import MessageRecord


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str


class ChatProvider(Protocol):
    async def complete(self, history: list[MessageRecord], max_response_tokens: int) -> ChatResult: ...
