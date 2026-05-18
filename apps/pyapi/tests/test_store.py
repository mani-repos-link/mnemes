from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pyapi.store import Store


class StoreTest(unittest.TestCase):
    def test_session_and_message_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(f"file:{Path(directory) / 'test.sqlite'}")
            session = store.create_session("Test")
            message = store.create_message(session.id, "user", "Hello")

            self.assertEqual(store.list_sessions()[0].id, session.id)
            self.assertEqual(store.list_messages(session.id)[0].id, message.id)

            store.delete_session(session.id)
            self.assertEqual(store.list_sessions(), [])
            store.close()


if __name__ == "__main__":
    unittest.main()
