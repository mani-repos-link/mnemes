from pyapi.context import build_llm_context

from .helpers import StoreRagTestCase, context_config, create_user_messages


class NoneMemoryModeTest(StoreRagTestCase):
    def test_none_mode_only_keeps_raw_window_and_never_compacts(self) -> None:
        def run(store):
            _session_id, messages = create_user_messages(
                store,
                ["one", "two", "three", "four", "five", "six", "seven"],
            )
            context = context_config("none")

            self.assertEqual(
                [message.content for message in build_llm_context(messages, None, context)],
                ["four", "five", "six", "seven"],
            )
        self.with_store(run)
