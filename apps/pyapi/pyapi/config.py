from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class ChatConfig:
    provider: str
    model: str
    openrouter_api_key: str
    openrouter_base_url: str
    huggingface_api_key: str
    huggingface_base_url: str
    http_referer: str
    app_title: str


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    openrouter_api_key: str
    openrouter_base_url: str
    huggingface_api_key: str
    huggingface_base_url: str
    http_referer: str
    app_title: str


@dataclass(frozen=True)
class ContextConfig:
    memory_mode: str
    recent_message_limit: int
    retrieval_top_k: int
    retrieval_min_score: float
    memory_max_chars: int
    summary_keep_recent_messages: int
    summary_trigger_message_limit: int
    max_response_tokens: int

    @property
    def enable_summaries(self) -> bool:
        return self.memory_mode == "summary"

    @property
    def enable_retrieval(self) -> bool:
        return self.memory_mode == "rag-vector"

    @property
    def enable_vectorless_retrieval(self) -> bool:
        return self.memory_mode == "rag-vectorless"


@dataclass(frozen=True)
class Config:
    addr: str
    database_url: str
    frontend_origins: list[str]
    chat: ChatConfig
    embedding: EmbeddingConfig
    context: ContextConfig

    @property
    def host(self) -> str:
        if self.addr.startswith(":"):
            return "127.0.0.1"
        return self.addr.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        return int(self.addr.rsplit(":", 1)[-1])


def load_config() -> Config:
    load_dotenv_upwards()
    provider = env("DEFAULT_CHAT_PROVIDER", "openrouter").lower()
    embedding_provider = env("DEFAULT_EMBEDDING_PROVIDER", provider).lower()
    memory_mode = context_memory_mode()
    recent_message_limit = int_env("RECENT_MESSAGE_LIMIT", 3)

    return Config(
        addr=env("APP_ADDR", ":8080"),
        database_url=env("DATABASE_URL", "file:../../data/chatbot.sqlite"),
        frontend_origins=split_csv(env("FRONTEND_ORIGINS", env("FRONTEND_ORIGIN", "http://localhost:5173"))),
        chat=ChatConfig(
            provider=provider,
            model=chat_model(),
            openrouter_api_key=env("OPENROUTER_API_KEY", ""),
            openrouter_base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            huggingface_api_key=env("HUGGINGFACE_API_KEY", env("HF_TOKEN", "")),
            huggingface_base_url=env("HUGGINGFACE_BASE_URL", "https://router.huggingface.co/v1").rstrip("/"),
            http_referer=provider_http_referer(),
            app_title=provider_app_title(),
        ),
        embedding=EmbeddingConfig(
            provider=embedding_provider,
            model=embedding_model(),
            openrouter_api_key=env("OPENROUTER_API_KEY", ""),
            openrouter_base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            huggingface_api_key=env("HUGGINGFACE_API_KEY", env("HF_TOKEN", "")),
            huggingface_base_url=env("HUGGINGFACE_BASE_URL", "https://router.huggingface.co/v1").rstrip("/"),
            http_referer=provider_http_referer(),
            app_title=provider_app_title(),
        ),
        context=ContextConfig(
            memory_mode=memory_mode,
            recent_message_limit=recent_message_limit,
            retrieval_top_k=int_env("RETRIEVAL_TOP_K", 5),
            retrieval_min_score=float_env("RETRIEVAL_MIN_SCORE", 0.2),
            memory_max_chars=int_env("MEMORY_MAX_CHARS", 4000),
            summary_keep_recent_messages=int_env("SUMMARY_KEEP_RECENT_MESSAGES", recent_message_limit),
            summary_trigger_message_limit=int_env("SUMMARY_TRIGGER_MESSAGE_LIMIT", 24),
            max_response_tokens=int_env("MAX_RESPONSE_TOKENS", 2000),
        ),
    )


def chat_model() -> str:
    return env("CHAT_MODEL", "meta-llama/llama-3.1-8b-instruct:free")


def embedding_model() -> str:
    return env("EMBEDDING_MODEL", "openai/text-embedding-3-small")


def context_memory_mode() -> str:
    value = env("CONTEXT_MEMORY_MODE", "").strip().lower()
    if not value:
        return "summary"
    aliases = {
        "summarization": "summary",
        "summarisation": "summary",
        "embedding": "rag-vector",
        "embeddings": "rag-vector",
        "rag": "rag-vector",
        "rag_vector": "rag-vector",
        "vector": "rag-vector",
        "vector-rag": "rag-vector",
        "rag_vectorless": "rag-vectorless",
        "vectorless": "rag-vectorless",
        "pageindex": "rag-vectorless",
        "off": "none",
        "disabled": "none",
    }
    normalized = aliases.get(value, value)
    if normalized in {"summary", "rag-vector", "rag-vectorless", "none"}:
        return normalized
    return "summary"


def provider_http_referer() -> str:
    return env("PROVIDER_HTTP_REFERER", env("FRONTEND_ORIGIN", "http://localhost:5173"))


def provider_app_title() -> str:
    return env("PROVIDER_APP_TITLE", "Mnemes")


def load_dotenv_upwards(filename: str = ".env") -> None:
    directory = Path.cwd()
    for path in [directory, *directory.parents]:
        dotenv = path / filename
        if dotenv.exists():
            load_dotenv(dotenv)
            return


def load_dotenv(path: Path) -> None:
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ[key] = value


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def env(key: str, fallback: str) -> str:
    return os.environ.get(key) or fallback


def int_env(key: str, fallback: int) -> int:
    try:
        return int(os.environ.get(key, ""))
    except ValueError:
        return fallback


def float_env(key: str, fallback: float) -> float:
    try:
        return float(os.environ.get(key, ""))
    except ValueError:
        return fallback


def bool_env(key: str, fallback: bool) -> bool:
    value = os.environ.get(key, "")
    if not value:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}
