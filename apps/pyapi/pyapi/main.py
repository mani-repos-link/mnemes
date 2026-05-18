from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import load_config
from .logging import redacted_key
from .providers import create_chat_provider
from .routes import create_router
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def localhost_origin_regex() -> str:
    return r"https?://(localhost|127\.0\.0\.1|\[::1\]):\d+"


config = load_config()
logger = logging.getLogger("pyapi")
logger.info(
    "config loaded addr=%s database=%s chat_provider=%s chat_model=%s openrouter_base_url=%s openrouter_key=%s huggingface_base_url=%s huggingface_key=%s frontend_origins=%s recent_limit=%d max_response_tokens=%d",
    config.addr,
    config.database_url,
    config.chat.provider,
    config.chat.model,
    config.chat.openrouter_base_url,
    redacted_key(config.chat.openrouter_api_key),
    config.chat.huggingface_base_url,
    redacted_key(config.chat.huggingface_api_key),
    ",".join(config.frontend_origins),
    config.context.recent_message_limit,
    config.context.max_response_tokens,
)

store = Store(config.database_url)
chat_provider = create_chat_provider(config.chat)
app = FastAPI(title="Mneme API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.frontend_origins,
    allow_origin_regex=localhost_origin_regex(),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(create_router(store, chat_provider, config.context))


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.on_event("shutdown")
def close_store() -> None:
    store.close()
