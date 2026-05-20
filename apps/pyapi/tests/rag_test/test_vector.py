from pyapi.context import build_llm_context, messages_for_memory_index_update
from pyapi.providers.types import EmbeddingResult
from pyapi.services.memory import index_messages_for_retrieval, retrieve_memories_for_message

from .helpers import StoreRagTestCase, context_config, create_user_messages


class FakeEmbeddingProvider:
    provider = "test"
    model = "fake-embedding"

    async def embed(self, inputs: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            embeddings=[self.vector_for_text(value) for value in inputs],
            provider=self.provider,
            model=self.model,
        )

    def vector_for_text(self, value: str) -> list[float]:
        lower = value.lower()
        if "sqlite" in lower:
            return [1.0, 0.0, 0.0]
        if "vue" in lower:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class VectorRagModeTest(StoreRagTestCase):
    def test_vector_mode_batches_embedding_indexing_and_uses_indexed_prefix(self) -> None:
        async def run_async(store):
            _session_id, messages = create_user_messages(
                store,
                ["sqlite notes", "vue styling", "provider settings", "raw four", "raw five", "raw six", "raw seven"],
            )
            context = context_config("rag-vector")
            provider = FakeEmbeddingProvider()

            batch = messages_for_memory_index_update(messages, set(), context)
            self.assertEqual([message.content for message in batch], ["sqlite notes", "vue styling", "provider settings"])

            await index_messages_for_retrieval(store, provider, context, messages)
            indexed_ids = store.list_indexed_memory_source_ids(
                messages[0].session_id,
                [message.id for message in messages],
                provider.model,
                provider.provider,
            )
            self.assertEqual(indexed_ids, {message.id for message in messages[:3]})

            llm_context = build_llm_context(messages, None, context, indexed_memory_source_ids=indexed_ids)
            self.assertEqual([message.content for message in llm_context], ["raw four", "raw five", "raw six", "raw seven"])

        def run(store):
            import asyncio

            asyncio.run(run_async(store))

        self.with_store(run)

    def test_vector_retrieval_uses_query_embedding_similarity(self) -> None:
        async def run_async(store):
            _session_id, messages = create_user_messages(
                store,
                ["sqlite full text search", "vue component styling", "provider settings", "raw four", "raw five", "raw six", "sqlite question"],
            )
            context = context_config("rag-vector")
            provider = FakeEmbeddingProvider()
            await index_messages_for_retrieval(store, provider, context, messages)

            memories = await retrieve_memories_for_message(
                store,
                provider,
                context,
                messages[-1],
                context_message_count=len(messages),
            )
            self.assertTrue(memories)
            self.assertIn("sqlite", memories[0].content.lower())
            self.assertEqual(memories[0].embedding_provider, provider.provider)
            self.assertEqual(memories[0].embedding_model, provider.model)

        def run(store):
            import asyncio

            asyncio.run(run_async(store))

        self.with_store(run)
