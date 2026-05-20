from pyapi.context import build_llm_context, messages_for_memory_index_update
from pyapi.routers.memory import index_messages_for_vectorless_retrieval, retrieve_vectorless_memories

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
