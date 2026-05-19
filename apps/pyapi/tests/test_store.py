from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from pyapi.store import Store
from pyapi.config import ContextConfig
from pyapi.context import messages_for_summary_update


class StoreTest(unittest.TestCase):
    def test_session_and_message_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")
            message = store.create_message(session.id, "user", "Hello")

            self.assertEqual(store.list_sessions()[0].id, session.id)
            self.assertEqual(store.list_messages(session.id)[0].id, message.id)

            renamed = store.update_session_title(session.id, "Renamed chat")
            self.assertEqual(renamed.title, "Renamed chat")
            self.assertEqual(store.get_session(session.id).title, "Renamed chat")

            store.delete_session(session.id)
            self.assertEqual(store.list_sessions(), [])
            store.close()

    def test_message_pagination_returns_latest_and_older_pages(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")

            for content in ["one", "two", "three", "four"]:
                store.create_message(session.id, "user", content)
                time.sleep(0.001)

            latest, has_more = store.list_messages_page(session.id, limit=2)
            self.assertTrue(has_more)
            self.assertEqual([message.content for message in latest], ["three", "four"])

            older, has_more = store.list_messages_page(session.id, limit=2, before=latest[0].created_at)
            self.assertFalse(has_more)
            self.assertEqual([message.content for message in older], ["one", "two"])

            store.close()

    def test_context_uses_only_active_response_for_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")
            prompt = store.create_message(session.id, "user", "Explain this")
            first = store.create_message(
                session.id,
                "assistant",
                "First answer",
                parent_message_id=prompt.id,
                make_active=True,
            )
            second = store.create_message(
                session.id,
                "assistant",
                "Second answer",
                parent_message_id=prompt.id,
                make_active=True,
            )

            context = store.list_context_messages(session.id)
            self.assertEqual([message.content for message in context], ["Explain this", "Second answer"])

            store.set_active_response(session.id, first.id)
            context = store.list_context_messages(session.id)
            self.assertEqual([message.content for message in context], ["Explain this", "First answer"])

            self.assertEqual(store.list_messages(session.id)[0].active_response_id, first.id)
            self.assertEqual(store.list_messages(session.id)[1].parent_message_id, prompt.id)
            self.assertEqual(store.list_messages(session.id)[2].parent_message_id, prompt.id)
            self.assertEqual(second.content, "Second answer")
            store.close()

    def test_summary_storage_and_cutoff_selection(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")

            for content in ["one", "two", "three", "four", "five"]:
                store.create_message(session.id, "user", content)
                time.sleep(0.001)

            context = ContextConfig(
                memory_mode="summary",
                recent_message_limit=3,
                retrieval_top_k=2,
                retrieval_min_score=0.2,
                memory_max_chars=4000,
                summary_keep_recent_messages=2,
                summary_trigger_message_limit=4,
                max_response_tokens=100,
            )
            messages = store.list_context_messages(session.id)
            to_summarize = messages_for_summary_update(messages, None, context)
            self.assertEqual([message.content for message in to_summarize], ["one", "two", "three"])

            summary = store.upsert_session_summary(
                session.id,
                "User mentioned one, two, and three.",
                to_summarize[-1].id,
            )
            self.assertEqual(summary.content, "User mentioned one, two, and three.")
            self.assertEqual(store.get_session_summary(session.id).covered_message_id, to_summarize[-1].id)

            to_summarize = messages_for_summary_update(messages, summary, context)
            self.assertEqual(to_summarize, [])
            store.close()

    def test_memory_vectors_are_searched_by_similarity(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")
            first = store.create_message(session.id, "user", "I like SQLite RAG")
            second = store.create_message(session.id, "assistant", "Vue styling notes")

            store.upsert_memory_item(
                session.id,
                "message",
                first.id,
                "User: I like SQLite RAG",
                [1.0, 0.0, 0.0],
                "test-embedding",
                "test",
            )
            store.upsert_memory_item(
                session.id,
                "message",
                second.id,
                "Assistant: Vue styling notes",
                [0.0, 1.0, 0.0],
                "test-embedding",
                "test",
            )

            memories = store.search_memory_items(
                session.id,
                [0.9, 0.1, 0.0],
                "test-embedding",
                "test",
                limit=1,
                min_score=0.0,
            )

            self.assertEqual([memory.source_id for memory in memories], [first.id])
            self.assertTrue(store.has_indexed_memory(session.id, "test-embedding", "test"))
            self.assertFalse(store.has_indexed_memory(session.id, "other-model", "test"))
            self.assertEqual(
                store.list_indexed_memory_source_ids(
                    session.id,
                    [first.id, second.id],
                    "test-embedding",
                    "test",
                ),
                {first.id, second.id},
            )
            store.close()


if __name__ == "__main__":
    unittest.main()
