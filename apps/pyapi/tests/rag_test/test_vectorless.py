from pathlib import Path

from pyapi.context import build_llm_context, messages_for_memory_index_update
from pyapi.config import ToolConfig
from pyapi.dependencies import AppServices
from pyapi.providers import ChatResult
from pyapi.services.conversation import create_assistant_response
from pyapi.services.memory import index_messages_for_vectorless_retrieval, retrieve_vectorless_memories, vectorless_retrieval_limit
from pyapi.store import MessageRecord

from .helpers import StoreRagTestCase, context_config, create_user_messages


class VectorlessRagModeTest(StoreRagTestCase):
    def test_vectorless_indexes_only_after_buffer_and_keeps_unindexed_tail_raw(self) -> None:
        def run(store):
            _session_id, messages = create_user_messages(
                store,
                ["sqlite notes", "vue styling", "rag memory", "raw four", "raw five", "raw six"],
            )
            context = context_config("rag-vectorless")

            self.assertEqual(messages_for_memory_index_update(messages, set(), context), [])

            session_id = messages[0].session_id
            seven = store.create_message(session_id, "user", "raw seven")
            messages = [*messages, seven]
            batch = messages_for_memory_index_update(messages, set(), context)
            self.assertEqual([message.content for message in batch], ["sqlite notes", "vue styling", "rag memory"])

            index_messages_for_vectorless_retrieval(store, context, batch)
            indexed_ids = store.list_text_memory_source_ids(session_id, [message.id for message in messages])
            llm_context = build_llm_context(messages, None, context, indexed_memory_source_ids=indexed_ids)
            self.assertEqual([message.content for message in llm_context], ["raw four", "raw five", "raw six", "raw seven"])

        self.with_store(run)

    def test_vectorless_retrieval_returns_fts_matches_without_embeddings(self) -> None:
        async def run_async(store):
            session_id, messages = create_user_messages(
                store,
                ["sqlite full text search", "frontend layout", "provider settings", "raw four", "raw five", "raw six", "ask sqlite"],
            )
            context = context_config("rag-vectorless")
            batch = messages_for_memory_index_update(messages, set(), context)
            index_messages_for_vectorless_retrieval(store, context, batch)

            memories = retrieve_vectorless_memories(store, context, messages[-1])
            self.assertTrue(memories)
            self.assertEqual(memories[0].session_id, session_id)
            self.assertIn("sqlite", memories[0].content.lower())
            self.assertEqual(memories[0].embedding_provider, "vectorless")
            self.assertIsNone(memories[0].embedding_dim)

        def run(store):
            import asyncio

            asyncio.run(run_async(store))

        self.with_store(run)

    def test_vectorless_query_ignores_common_prompt_words(self) -> None:
        async def run_async(store):
            session_id, messages = create_user_messages(
                store,
                [
                    "Are you reasoning model? I mean do you think?",
                    "Relevant summary memory should be concise",
                    "workspace capability notes",
                    "older filler one",
                    "older filler two",
                    "older filler three",
                    "older filler four",
                    "current ask about relevant memory",
                ],
            )
            context = context_config("rag-vectorless")
            batch = messages_for_memory_index_update(messages, set(), context)
            index_messages_for_vectorless_retrieval(store, context, batch)

            query = store.create_message(session_id, "user", "do you think is this relevant summary memory to provide")
            memories = retrieve_vectorless_memories(store, context, query)

            self.assertTrue(memories)
            self.assertIn("Relevant summary memory", memories[0].content)

        def run(store):
            import asyncio

            asyncio.run(run_async(store))

        self.with_store(run)

    def test_vectorless_retrieval_is_capped_to_reduce_noise(self) -> None:
        context = context_config("rag-vectorless")
        self.assertLessEqual(vectorless_retrieval_limit(context), 4)

    def test_vectorless_indexes_pending_messages_before_chat_context_is_sent(self) -> None:
        async def run_async(store):
            session_id, messages = create_user_messages(
                store,
                ["old one", "old two", "old three", "old four", "raw five", "raw six", "raw seven", "current ask"],
            )
            context = context_config("rag-vectorless")
            chat_provider = CapturingChatProvider()
            services = AppServices(
                store=store,
                chat_provider=chat_provider,
                embedding_provider=FakeEmbeddingProvider(),
                context=context,
                tools=ToolConfig(
                    enabled=False,
                    database_url="file::memory:",
                    workspace_root=Path("."),
                    max_iterations=1,
                    max_output_chars=1000,
                    internet_enabled=False,
                    network_timeout_seconds=1,
                    max_network_bytes=1000,
                    crawl_max_pages=1,
                    memory_mode="rag-vectorless",
                    context_memory_trigger_message_limit=4,
                    context_memory_buffer_message_limit=3,
                    retrieval_top_k=2,
                ),
            )

            await create_assistant_response(services, session_id, messages[-1], messages)

            raw_user_contents = [message.content for message in chat_provider.history if message.role == "user"]
            self.assertEqual(raw_user_contents, ["raw five", "raw six", "raw seven", "current ask"])
            indexed_ids = store.list_text_memory_source_ids(session_id, [message.id for message in messages])
            self.assertEqual({message.content for message in messages[:4]}, {message.content for message in messages if message.id in indexed_ids})

        def run(store):
            import asyncio

            asyncio.run(run_async(store))

        self.with_store(run)


class CapturingChatProvider:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.history: list[MessageRecord] = []

    async def complete(
        self,
        history: list[MessageRecord],
        max_response_tokens: int,
        system_prompt: str | None = None,
    ) -> ChatResult:
        self.history = history
        return ChatResult(content="answer", provider=self.provider, model=self.model)


class FakeEmbeddingProvider:
    provider = "fake"
    model = "fake-embedding"

    async def embed(self, inputs: list[str]):
        raise AssertionError("vectorless mode should not call embeddings")
