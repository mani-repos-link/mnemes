import unittest

from pyapi.providers import EmptyModelResponseError
from pyapi.providers.compatible import build_messages, extract_message_content
from pyapi.providers.prompts import assistant_system_prompt


class ProviderParsingTest(unittest.TestCase):
    def test_extract_message_content_handles_null_content(self) -> None:
        self.assertEqual(extract_message_content({"message": {"content": None}}), "")

    def test_extract_message_content_handles_text_parts(self) -> None:
        content = extract_message_content(
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "text", "text": "world"},
                    ]
                }
            }
        )

        self.assertEqual(content, "hello\nworld")

    def test_extract_message_content_uses_refusal_text(self) -> None:
        content = extract_message_content({"message": {"content": None, "refusal": "I cannot help with that."}})

        self.assertEqual(content, "I cannot help with that.")

    def test_empty_model_response_error_message_is_stable(self) -> None:
        self.assertEqual(str(EmptyModelResponseError("openrouter")), "openrouter returned an empty message")

    def test_tool_prompt_names_role_and_available_tools(self) -> None:
        messages = build_messages([], assistant_system_prompt(True, True))
        prompt = messages[0]["content"]

        self.assertIn("Mnemes", prompt)
        self.assertIn("<tool_call>", prompt)
        self.assertIn("grep", prompt)
        self.assertIn("ls", prompt)
        self.assertIn("fetch_url", prompt)
        self.assertIn("/llms.txt", prompt)
        self.assertIn("Do not claim you cannot browse", prompt)
        self.assertIn("https://example.com", prompt)
        self.assertIn("canonical format", prompt)
        self.assertIn("Do not use any other tag name", prompt)


if __name__ == "__main__":
    unittest.main()
