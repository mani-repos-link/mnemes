from pyapi.context import build_llm_context, messages_for_summary_update

from .helpers import StoreRagTestCase, context_config, create_user_messages


class SummaryMemoryModeTest(StoreRagTestCase):
    def test_summary_waits_for_buffer_then_keeps_recent_raw_tail(self) -> None:
        def run(store):
            session_id, messages = create_user_messages(
                store,
                ["one", "two", "three", "four", "five", "six"],
            )
            context = context_config("summary")

            self.assertEqual(messages_for_summary_update(messages, None, context), [])
            self.assertEqual(
                [message.content for message in build_llm_context(messages, None, context)],
                ["one", "two", "three", "four", "five", "six"],
            )

            seven = store.create_message(session_id, "user", "seven")
            messages = [*messages, seven]
            to_summarize = messages_for_summary_update(messages, None, context)
            self.assertEqual([message.content for message in to_summarize], ["one", "two", "three"])

            summary = store.upsert_session_summary(session_id, "Earlier: one, two, three.", to_summarize[-1].id)
            llm_context = build_llm_context(messages, summary, context)

            self.assertEqual(llm_context[0].role, "system")
            self.assertIn("Earlier: one, two, three.", llm_context[0].content)
            self.assertEqual([message.content for message in llm_context[1:]], ["four", "five", "six", "seven"])

        self.with_store(run)

    def test_summary_updates_only_new_overflow_after_previous_summary(self) -> None:
        def run(store):
            session_id, messages = create_user_messages(
                store,
                ["one", "two", "three", "four", "five", "six", "seven"],
            )
            context = context_config("summary")
            first_batch = messages_for_summary_update(messages, None, context)
            summary = store.upsert_session_summary(session_id, "Earlier batch.", first_batch[-1].id)

            for content in ["eight", "nine", "ten"]:
                store.create_message(session_id, "user", content)
                messages = store.list_context_messages(session_id)

            second_batch = messages_for_summary_update(messages, summary, context)
            self.assertEqual([message.content for message in second_batch], ["four", "five", "six"])

        self.with_store(run)
