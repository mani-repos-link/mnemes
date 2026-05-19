from __future__ import annotations

import logging
import time

import httpx

from pyapi.config import EmbeddingConfig

from .types import EmbeddingProvider, EmbeddingResult

logger = logging.getLogger("pyapi.embedding")


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        http_referer: str,
        app_title: str,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_referer = http_referer
        self.app_title = app_title

    async def embed(self, inputs: list[str]) -> EmbeddingResult:
        texts = [text.strip() for text in inputs if text.strip()]
        if not texts:
            return EmbeddingResult(embeddings=[], provider=self.provider, model=self.model)
        if not self.api_key:
            raise ValueError(f"{self.provider} embedding API key is required")
        if not self.model:
            raise ValueError(f"{self.provider} embedding model is required")

        endpoint = f"{self.base_url}/embeddings"
        body = {"model": self.model, "input": texts}

        start = time.monotonic()
        logger.info(
            "%s embedding request endpoint=%s model=%s inputs=%d",
            self.provider,
            endpoint,
            self.model,
            len(texts),
        )

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self.http_referer,
                    "X-Title": self.app_title,
                },
                json=body,
            )

        logger.info(
            "%s embedding response status=%d duration=%.3fs bytes=%d",
            self.provider,
            response.status_code,
            time.monotonic() - start,
            len(response.content),
        )

        payload = response.json()
        if response.status_code < 200 or response.status_code >= 300:
            message = payload.get("error", {}).get("message") or response.reason_phrase
            raise ValueError(f"{self.provider} embedding error: {message}")

        data = sorted(payload.get("data") or [], key=lambda item: item.get("index", 0))
        embeddings = [item.get("embedding") for item in data]
        if len(embeddings) != len(texts) or any(not isinstance(item, list) for item in embeddings):
            raise ValueError(f"{self.provider} returned invalid embeddings")

        return EmbeddingResult(
            embeddings=[[float(value) for value in item] for item in embeddings],
            provider=self.provider,
            model=payload.get("model") or self.model,
        )


class UnsupportedEmbeddingProvider:
    def __init__(self, provider: str):
        self.provider = provider
        self.model = ""

    async def embed(self, _inputs: list[str]) -> EmbeddingResult:
        raise ValueError(f'unsupported embedding provider "{self.provider}"')


def create_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "openrouter":
        return OpenAICompatibleEmbeddingProvider(
            provider="openrouter",
            base_url=config.openrouter_base_url,
            api_key=config.openrouter_api_key,
            model=config.model,
            http_referer=config.http_referer,
            app_title=config.app_title,
        )
    if config.provider == "huggingface":
        return OpenAICompatibleEmbeddingProvider(
            provider="huggingface",
            base_url=config.huggingface_base_url,
            api_key=config.huggingface_api_key,
            model=config.model,
            http_referer=config.http_referer,
            app_title=config.app_title,
        )
    return UnsupportedEmbeddingProvider(config.provider)
