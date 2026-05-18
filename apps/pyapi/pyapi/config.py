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


@dataclass(frozen=True)
class ContextConfig:
    recent_message_limit: int
    max_response_tokens: int


@dataclass(frozen=True)
class Config:
    addr: str
    database_url: str
    frontend_origins: list[str]
    chat: ChatConfig
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

    return Config(
        addr=env("APP_ADDR", ":8080"),
        database_url=env("DATABASE_URL", "file:../../data/chatbot.sqlite"),
        frontend_origins=split_csv(env("FRONTEND_ORIGINS", env("FRONTEND_ORIGIN", "http://localhost:5173"))),
        chat=ChatConfig(
            provider=provider,
            model=chat_model(provider),
            openrouter_api_key=env("OPENROUTER_API_KEY", ""),
            openrouter_base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            huggingface_api_key=env("HUGGINGFACE_API_KEY", env("HF_TOKEN", "")),
            huggingface_base_url=env("HUGGINGFACE_BASE_URL", "https://router.huggingface.co/v1").rstrip("/"),
        ),
        context=ContextConfig(
            recent_message_limit=int_env("RECENT_MESSAGE_LIMIT", 20),
            max_response_tokens=int_env("MAX_RESPONSE_TOKENS", 2000),
        ),
    )


def chat_model(provider: str) -> str:
    if value := env("CHAT_MODEL", ""):
        return value
    if provider == "huggingface":
        return env("HUGGINGFACE_CHAT_MODEL", "")
    return env("OPENROUTER_CHAT_MODEL", "meta-llama/llama-3.1-8b-instruct:free")


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
        if key and key not in os.environ:
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
