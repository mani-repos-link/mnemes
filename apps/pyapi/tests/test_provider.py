import unittest

from pyapi.providers import EmptyModelResponseError
from pyapi.providers.compatible import extract_message_content


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


if __name__ == "__main__":
    unittest.main()
