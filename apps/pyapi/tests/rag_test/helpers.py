from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Callable
import unittest

from pyapi.config import ContextConfig
from pyapi.store import MessageRecord, Store


def context_config(memory_mode: str) -> ContextConfig:
    return ContextConfig(
        memory_mode=memory_mode,
        context_memory_trigger_message_limit=4,
        context_memory_buffer_message_limit=3,
        retrieval_top_k=2,
        retrieval_min_score=0.2,
        memory_max_chars=4000,
        max_response_tokens=100,
    )


class StoreRagTestCase(unittest.TestCase):
    def with_store(self, callback: Callable[[Store], None]) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            try:
                callback(store)
            finally:
                store.close()


def create_user_messages(store: Store, contents: list[str]) -> tuple[str, list[MessageRecord]]:
    session = store.create_session("RAG test")
    messages: list[MessageRecord] = []
    for content in contents:
        messages.append(store.create_message(session.id, "user", content))
        time.sleep(0.001)
    return session.id, messages
