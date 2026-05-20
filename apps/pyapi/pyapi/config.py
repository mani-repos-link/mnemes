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
    context_memory_trigger_message_limit: int
    context_memory_buffer_message_limit: int
    retrieval_top_k: int
    retrieval_min_score: float
    memory_max_chars: int
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
class ToolConfig:
    enabled: bool
    database_url: str
    workspace_root: Path
    max_iterations: int
    max_output_chars: int
    internet_enabled: bool
    network_timeout_seconds: float
    max_network_bytes: int
    crawl_max_pages: int
    memory_mode: str
    context_memory_trigger_message_limit: int
    context_memory_buffer_message_limit: int
    retrieval_top_k: int


@dataclass(frozen=True)
class Config:
    addr: str
    database_url: str
    frontend_origins: list[str]
    chat: ChatConfig
    embedding: EmbeddingConfig
    context: ContextConfig
    tools: ToolConfig

    @property
    def host(self) -> str:
        if self.addr.startswith(":"):
            return "127.0.0.1"
        return self.addr.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        return int(self.addr.rsplit(":", 1)[-1])


def load_config() -> Config:
    dotenv_path = load_dotenv_upwards()
    provider = env("DEFAULT_CHAT_PROVIDER", "openrouter").lower()
    embedding_provider = env("DEFAULT_EMBEDDING_PROVIDER", provider).lower()
    memory_mode = context_memory_mode()
    workspace_root = resolve_path_env("TOOL_WORKSPACE_ROOT", "../..", dotenv_path.parent if dotenv_path else Path.cwd())

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
            context_memory_trigger_message_limit=int_env("CONTEXT_MEMORY_TRIGGER_MESSAGE_LIMIT", 24),
            context_memory_buffer_message_limit=max(1, int_env("CONTEXT_MEMORY_BUFFER_MESSAGE_LIMIT", 6)),
            retrieval_top_k=int_env("RETRIEVAL_TOP_K", 5),
            retrieval_min_score=float_env("RETRIEVAL_MIN_SCORE", 0.2),
            memory_max_chars=int_env("MEMORY_MAX_CHARS", 4000),
            max_response_tokens=int_env("MAX_RESPONSE_TOKENS", 2000),
        ),
        tools=ToolConfig(
            enabled=bool_env("TOOLS_ENABLED", False),
            database_url=env("DATABASE_URL", "file:../../data/chatbot.sqlite"),
            workspace_root=workspace_root,
            max_iterations=max(1, int_env("MAX_TOOL_ITERATIONS", 3)),
            max_output_chars=max(1000, int_env("MAX_TOOL_OUTPUT_CHARS", 12000)),
            internet_enabled=bool_env("INTERNET_TOOLS_ENABLED", False),
            network_timeout_seconds=max(1.0, float_env("TOOL_NETWORK_TIMEOUT_SECONDS", 10.0)),
            max_network_bytes=max(1000, int_env("MAX_TOOL_NETWORK_BYTES", 300000)),
            crawl_max_pages=max(1, int_env("TOOL_CRAWL_MAX_PAGES", 5)),
            memory_mode=memory_mode,
            context_memory_trigger_message_limit=int_env("CONTEXT_MEMORY_TRIGGER_MESSAGE_LIMIT", 24),
            context_memory_buffer_message_limit=max(1, int_env("CONTEXT_MEMORY_BUFFER_MESSAGE_LIMIT", 6)),
            retrieval_top_k=int_env("RETRIEVAL_TOP_K", 5),
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


def load_dotenv_upwards(filename: str = ".env") -> Path | None:
    directory = Path.cwd()
    for path in [directory, *directory.parents]:
        dotenv = path / filename
        if dotenv.exists():
            load_dotenv(dotenv)
            return dotenv
    return None


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


def resolve_path_env(key: str, fallback: str, base_dir: Path) -> Path:
    raw_value = env(key, fallback)
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
