from __future__ import annotations

import logging
import time

import httpx

from pyapi.store import MessageRecord

from .types import ChatResult

logger = logging.getLogger("pyapi.provider")


class OpenAICompatibleProvider:
    def __init__(self, provider: str, base_url: str, api_key: str, model: str):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def complete(self, history: list[MessageRecord], max_response_tokens: int) -> ChatResult:
        if not self.api_key:
            raise ValueError(f"{self.provider} API key is required")
        if not self.model:
            raise ValueError(f"{self.provider} chat model is required")

        endpoint = f"{self.base_url}/chat/completions"
        messages = build_messages(history)
        body = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_response_tokens,
            "temperature": 0.7,
            "stream": False,
        }

        start = time.monotonic()
        logger.info(
            "%s request endpoint=%s model=%s messages=%d",
            self.provider,
            endpoint,
            self.model,
            len(messages),
        )

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:5173",
                    "X-Title": "Mneme",
                },
                json=body,
            )

        logger.info(
            "%s response status=%d duration=%.3fs bytes=%d",
            self.provider,
            response.status_code,
            time.monotonic() - start,
            len(response.content),
        )

        payload = response.json()
        if response.status_code < 200 or response.status_code >= 300:
            message = payload.get("error", {}).get("message") or response.reason_phrase
            logger.warning("%s error status=%d message=%s", self.provider, response.status_code, message)
            raise ValueError(f"{self.provider} error: {message}")

        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"{self.provider} returned no choices")

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            raise ValueError(f"{self.provider} returned an empty message")

        return ChatResult(
            content=content,
            provider=self.provider,
            model=payload.get("model") or self.model,
        )


def build_messages(history: list[MessageRecord]) -> list[dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant in a local, self-hosted chatbot. Answer clearly and concisely.",
        }
    ]
    for message in history:
        if message.role in {"user", "assistant", "system"}:
            messages.append({"role": message.role, "content": message.content})
    return messages
