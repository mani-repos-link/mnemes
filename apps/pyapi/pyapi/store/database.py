from __future__ import annotations

from pathlib import Path
import sqlite3
from threading import RLock

from .errors import NotFoundError
from .ids import new_id, timestamp
from .models import MessageRecord, SessionRecord


class Store:
    def __init__(self, database_url: str):
        ensure_sqlite_dir(database_url)
        self._db = sqlite3.connect(database_url, uri=database_url.startswith("file:"), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = RLock()
        self.migrate()

    def close(self) -> None:
        self._db.close()

    def migrate(self) -> None:
        with self._lock, self._db:
            self._db.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  archived_at TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
                  content TEXT NOT NULL,
                  provider TEXT,
                  model TEXT,
                  parent_message_id TEXT,
                  active_response_id TEXT,
                  token_count INTEGER,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                  FOREIGN KEY (parent_message_id) REFERENCES messages(id) ON DELETE SET NULL,
                  FOREIGN KEY (active_response_id) REFERENCES messages(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_session_created_at ON messages(session_id, created_at ASC);
                """
            )
            self._ensure_message_branch_columns()
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_messages_parent_message_id ON messages(parent_message_id)")
            self._backfill_message_branches()

    def list_sessions(self) -> list[SessionRecord]:
        rows = self._query_all(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE archived_at IS NULL
            ORDER BY updated_at DESC
            """
        )
        return [session_from_row(row) for row in rows]

    def create_session(self, title: str) -> SessionRecord:
        now = timestamp()
        session = SessionRecord(
            id=new_id("ses"),
            title=title.strip() or "New chat",
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session.id, session.title, session.created_at, session.updated_at),
            )
        return session

    def get_session(self, session_id: str) -> SessionRecord:
        row = self._query_one(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE id = ? AND archived_at IS NULL
            """,
            (session_id,),
        )
        if row is None:
            raise NotFoundError("session not found")
        return session_from_row(row)

    def delete_session(self, session_id: str) -> None:
        now = timestamp()
        with self._lock, self._db:
            cursor = self._db.execute(
                """
                UPDATE sessions
                SET archived_at = ?, updated_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (now, now, session_id),
            )
        if cursor.rowcount == 0:
            raise NotFoundError("session not found")

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        self.get_session(session_id)
        rows = self._query_all(
            """
            SELECT id, session_id, role, content, provider, model, parent_message_id, active_response_id, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return [message_from_row(row) for row in rows]

    def list_context_messages(
        self,
        session_id: str,
        through_user_message_id: str | None = None,
    ) -> list[MessageRecord]:
        messages = self.list_messages(session_id)
        by_id = {message.id: message for message in messages}
        context: list[MessageRecord] = []

        for message in messages:
            if message.role == "assistant" and message.parent_message_id:
                continue

            if message.role == "user":
                context.append(message)
                if message.active_response_id:
                    active_response = by_id.get(message.active_response_id)
                    if active_response is not None:
                        context.append(active_response)
                if message.id == through_user_message_id:
                    break
                continue

            if message.role in {"assistant", "system"}:
                context.append(message)

        return context

    def list_messages_page(
        self,
        session_id: str,
        limit: int = 15,
        before: str | None = None,
    ) -> tuple[list[MessageRecord], bool]:
        self.get_session(session_id)
        limit = max(1, limit)
        params: list[object] = [session_id]
        before_clause = ""
        if before:
            before_clause = "AND created_at < ?"
            params.append(before)
        params.append(limit + 1)

        rows = self._query_all(
            f"""
            SELECT id, session_id, role, content, provider, model, parent_message_id, active_response_id, created_at
            FROM messages
            WHERE session_id = ?
            {before_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        return [message_from_row(row) for row in reversed(rows)], has_more

    def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
        parent_message_id: str | None = None,
        make_active: bool = False,
    ) -> MessageRecord:
        role = role.strip()
        content = content.strip()
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("invalid role")
        if not content:
            raise ValueError("content is required")
        if parent_message_id and role != "assistant":
            raise ValueError("only assistant messages can have a parent")

        self.get_session(session_id)
        if parent_message_id:
            parent = self._query_one(
                """
                SELECT id, role
                FROM messages
                WHERE id = ? AND session_id = ?
                """,
                (parent_message_id, session_id),
            )
            if parent is None:
                raise NotFoundError("parent message not found")
            if parent["role"] != "user":
                raise ValueError("assistant parent must be a user message")

        now = timestamp()
        message = MessageRecord(
            id=new_id("msg"),
            session_id=session_id,
            role=role,
            content=content,
            provider=provider,
            model=model,
            parent_message_id=parent_message_id,
            active_response_id=None,
            created_at=now,
        )

        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO messages (id, session_id, role, content, provider, model, parent_message_id, active_response_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.session_id,
                    message.role,
                    message.content,
                    message.provider,
                    message.model,
                    message.parent_message_id,
                    message.active_response_id,
                    message.created_at,
                ),
            )
            if parent_message_id and make_active:
                self._db.execute(
                    """
                    UPDATE messages
                    SET active_response_id = ?
                    WHERE id = ? AND session_id = ?
                    """,
                    (message.id, parent_message_id, session_id),
                )
            self._db.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
        return message

    def set_active_response(self, session_id: str, assistant_message_id: str) -> MessageRecord:
        self.get_session(session_id)
        assistant = self._query_one(
            """
            SELECT id, session_id, role, content, provider, model, parent_message_id, active_response_id, created_at
            FROM messages
            WHERE id = ? AND session_id = ?
            """,
            (assistant_message_id, session_id),
        )
        if assistant is None:
            raise NotFoundError("message not found")
        if assistant["role"] != "assistant" or not assistant["parent_message_id"]:
            raise ValueError("only assistant alternatives can be activated")

        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE messages
                SET active_response_id = ?
                WHERE id = ? AND session_id = ?
                """,
                (assistant_message_id, assistant["parent_message_id"], session_id),
            )
            self._db.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (timestamp(), session_id),
            )
        return message_from_row(assistant)

    def _ensure_message_branch_columns(self) -> None:
        columns = {
            row["name"]
            for row in self._db.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "parent_message_id" not in columns:
            self._db.execute("ALTER TABLE messages ADD COLUMN parent_message_id TEXT")
        if "active_response_id" not in columns:
            self._db.execute("ALTER TABLE messages ADD COLUMN active_response_id TEXT")

    def _backfill_message_branches(self) -> None:
        rows = self._db.execute(
            """
            SELECT id, session_id, role, parent_message_id
            FROM messages
            ORDER BY session_id ASC, created_at ASC
            """
        ).fetchall()
        last_user_by_session: dict[str, str] = {}
        active_response_by_user: dict[str, str] = {}

        for row in rows:
            if row["role"] == "user":
                last_user_by_session[row["session_id"]] = row["id"]
                continue
            if row["role"] != "assistant" or row["parent_message_id"]:
                continue

            parent_id = last_user_by_session.get(row["session_id"])
            if not parent_id:
                continue
            self._db.execute(
                """
                UPDATE messages
                SET parent_message_id = ?
                WHERE id = ?
                """,
                (parent_id, row["id"]),
            )
            active_response_by_user[parent_id] = row["id"]

        for user_id, assistant_id in active_response_by_user.items():
            self._db.execute(
                """
                UPDATE messages
                SET active_response_id = COALESCE(active_response_id, ?)
                WHERE id = ?
                """,
                (assistant_id, user_id),
            )

    def _query_one(self, query: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(query, params).fetchone()

    def _query_all(self, query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._db.execute(query, params).fetchall())


def session_from_row(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def message_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        provider=row["provider"],
        model=row["model"],
        parent_message_id=row["parent_message_id"],
        active_response_id=row["active_response_id"],
        created_at=row["created_at"],
    )


def ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("file:"):
        return

    path = database_url.removeprefix("file:").split("?", 1)[0]
    if not path or path == ":memory:":
        return

    directory = Path(path).parent
    if str(directory) not in {"", "."}:
        directory.mkdir(parents=True, exist_ok=True)
