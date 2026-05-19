from __future__ import annotations

import importlib.resources
import logging
import math
from pathlib import Path
import sqlite3
import struct
from threading import RLock

from .errors import NotFoundError
from .ids import new_id, timestamp
from .models import MemoryItemRecord, MessageRecord, SessionRecord, SessionSummaryRecord

logger = logging.getLogger("pyapi.store")


class Store:
    def __init__(self, database_url: str):
        ensure_sqlite_dir(database_url)
        self._db = sqlite3.connect(database_url, uri=database_url.startswith("file:"), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.create_function("vec_cosine_similarity", 2, sqlite_cosine_similarity)
        self._sqlite_vector_available = self._load_sqlite_vector()
        self._sqlite_vector_dimensions: set[int] = set()
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

                CREATE TABLE IF NOT EXISTS session_summaries (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL UNIQUE,
                  content TEXT NOT NULL,
                  covered_message_id TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                  FOREIGN KEY (covered_message_id) REFERENCES messages(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  source_type TEXT NOT NULL CHECK (source_type IN ('message', 'summary')),
                  source_id TEXT NOT NULL,
                  content TEXT NOT NULL,
                  embedding BLOB,
                  embedding_dim INTEGER,
                  embedding_model TEXT,
                  embedding_provider TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_session_created_at ON messages(session_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_memory_items_session_source ON memory_items(session_id, source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_memory_items_embedding_meta ON memory_items(session_id, embedding_provider, embedding_model, embedding_dim);
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

    def update_session_title(self, session_id: str, title: str) -> SessionRecord:
        title = title.strip()
        if not title:
            raise ValueError("title is required")

        with self._lock, self._db:
            cursor = self._db.execute(
                """
                UPDATE sessions
                SET title = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (title, session_id),
            )
        if cursor.rowcount == 0:
            raise NotFoundError("session not found")
        return self.get_session(session_id)

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

    def get_session_summary(self, session_id: str) -> SessionSummaryRecord | None:
        self.get_session(session_id)
        row = self._query_one(
            """
            SELECT id, session_id, content, covered_message_id, created_at, updated_at
            FROM session_summaries
            WHERE session_id = ?
            """,
            (session_id,),
        )
        return summary_from_row(row) if row is not None else None

    def upsert_session_summary(
        self,
        session_id: str,
        content: str,
        covered_message_id: str | None,
    ) -> SessionSummaryRecord:
        self.get_session(session_id)
        content = content.strip()
        if not content:
            raise ValueError("summary content is required")

        existing = self.get_session_summary(session_id)
        now = timestamp()
        summary_id = existing.id if existing else new_id("sum")
        created_at = existing.created_at if existing else now

        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO session_summaries (id, session_id, content, covered_message_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  content = excluded.content,
                  covered_message_id = excluded.covered_message_id,
                  updated_at = excluded.updated_at
                """,
                (summary_id, session_id, content, covered_message_id, created_at, now),
            )
            self._db.execute(
                """
                INSERT INTO memory_items (
                  id, session_id, source_type, source_id, content, embedding, embedding_dim,
                  embedding_model, embedding_provider, created_at, updated_at
                )
                VALUES (?, ?, 'summary', ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  content = excluded.content,
                  updated_at = excluded.updated_at
                """,
                (f"mem_{summary_id}", session_id, summary_id, content, now, now),
            )

        return SessionSummaryRecord(
            id=summary_id,
            session_id=session_id,
            content=content,
            covered_message_id=covered_message_id,
            created_at=created_at,
            updated_at=now,
        )

    def upsert_memory_item(
        self,
        session_id: str,
        source_type: str,
        source_id: str,
        content: str,
        embedding: list[float],
        embedding_model: str,
        embedding_provider: str,
    ) -> MemoryItemRecord:
        self.get_session(session_id)
        if source_type not in {"message", "summary"}:
            raise ValueError("invalid memory source type")
        content = content.strip()
        if not content:
            raise ValueError("memory content is required")
        if not embedding:
            raise ValueError("embedding is required")

        now = timestamp()
        memory_id = f"mem_{source_id}"
        embedding_blob = serialize_vector(embedding)
        embedding_dim = len(embedding)

        with self._lock, self._db:
            existing = self._query_one(
                """
                SELECT created_at
                FROM memory_items
                WHERE id = ?
                """,
                (memory_id,),
            )
            created_at = existing["created_at"] if existing is not None else now
            self._db.execute(
                """
                INSERT INTO memory_items (
                  id, session_id, source_type, source_id, content, embedding, embedding_dim,
                  embedding_model, embedding_provider, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  content = excluded.content,
                  embedding = excluded.embedding,
                  embedding_dim = excluded.embedding_dim,
                  embedding_model = excluded.embedding_model,
                  embedding_provider = excluded.embedding_provider,
                  updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    session_id,
                    source_type,
                    source_id,
                    content,
                    embedding_blob,
                    embedding_dim,
                    embedding_model,
                    embedding_provider,
                    created_at,
                    now,
                ),
            )
            self._refresh_sqlite_vector_index(embedding_dim)

        return MemoryItemRecord(
            id=memory_id,
            session_id=session_id,
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            embedding_provider=embedding_provider,
            score=None,
            created_at=created_at,
            updated_at=now,
        )

    def search_memory_items(
        self,
        session_id: str,
        query_embedding: list[float],
        embedding_model: str,
        embedding_provider: str,
        limit: int,
        min_score: float,
        exclude_source_ids: set[str] | None = None,
    ) -> list[MemoryItemRecord]:
        self.get_session(session_id)
        if not query_embedding:
            return []

        if self._ensure_sqlite_vector(len(query_embedding)):
            try:
                return self._search_memory_items_with_sqlite_vector(
                    session_id,
                    query_embedding,
                    embedding_model,
                    embedding_provider,
                    limit,
                    min_score,
                    exclude_source_ids,
                )
            except sqlite3.Error:
                logger.exception("sqlite-vector search failed; falling back to Python cosine search")

        return self._search_memory_items_with_python_cosine(
            session_id,
            query_embedding,
            embedding_model,
            embedding_provider,
            limit,
            min_score,
            exclude_source_ids,
        )

    def _search_memory_items_with_python_cosine(
        self,
        session_id: str,
        query_embedding: list[float],
        embedding_model: str,
        embedding_provider: str,
        limit: int,
        min_score: float,
        exclude_source_ids: set[str] | None = None,
    ) -> list[MemoryItemRecord]:
        exclude_source_ids = exclude_source_ids or set()
        query_blob = serialize_vector(query_embedding)
        params: list[object] = [
            query_blob,
            session_id,
            embedding_provider,
            embedding_model,
            len(query_embedding),
        ]
        exclude_clause = ""
        if exclude_source_ids:
            placeholders = ", ".join("?" for _ in exclude_source_ids)
            exclude_clause = f"AND source_id NOT IN ({placeholders})"
            params.extend(sorted(exclude_source_ids))
        params.extend([min_score, limit])

        rows = self._query_all(
            f"""
            SELECT
              id, session_id, source_type, source_id, content, embedding_dim, embedding_model,
              embedding_provider, created_at, updated_at,
              vec_cosine_similarity(embedding, ?) AS score
            FROM memory_items
            WHERE session_id = ?
              AND embedding IS NOT NULL
              AND embedding_provider = ?
              AND embedding_model = ?
              AND embedding_dim = ?
              {exclude_clause}
              AND vec_cosine_similarity(embedding, ?) >= ?
            ORDER BY score DESC, updated_at DESC
            LIMIT ?
            """,
            tuple([*params[:5], *params[5:-2], query_blob, *params[-2:]]),
        )
        return [memory_from_row(row) for row in rows]

    def _search_memory_items_with_sqlite_vector(
        self,
        session_id: str,
        query_embedding: list[float],
        embedding_model: str,
        embedding_provider: str,
        limit: int,
        min_score: float,
        exclude_source_ids: set[str] | None = None,
    ) -> list[MemoryItemRecord]:
        exclude_source_ids = exclude_source_ids or set()
        query_blob = serialize_vector(query_embedding)
        scan_limit = max(limit * 10, 50)
        params: list[object] = [query_blob, scan_limit, session_id, embedding_provider, embedding_model, len(query_embedding)]
        exclude_clause = ""
        if exclude_source_ids:
            placeholders = ", ".join("?" for _ in exclude_source_ids)
            exclude_clause = f"AND memory_items.source_id NOT IN ({placeholders})"
            params.extend(sorted(exclude_source_ids))
        params.extend([min_score, limit])

        rows = self._query_all(
            f"""
            SELECT
              memory_items.id,
              memory_items.session_id,
              memory_items.source_type,
              memory_items.source_id,
              memory_items.content,
              memory_items.embedding_dim,
              memory_items.embedding_model,
              memory_items.embedding_provider,
              memory_items.created_at,
              memory_items.updated_at,
              (1.0 - vector_matches.distance) AS score
            FROM memory_items
            JOIN vector_quantize_scan('memory_items', 'embedding', ?, ?) AS vector_matches
              ON memory_items.rowid = vector_matches.rowid
            WHERE memory_items.session_id = ?
              AND memory_items.embedding_provider = ?
              AND memory_items.embedding_model = ?
              AND memory_items.embedding_dim = ?
              {exclude_clause}
              AND (1.0 - vector_matches.distance) >= ?
            ORDER BY vector_matches.distance ASC, memory_items.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [memory_from_row(row) for row in rows]

    def list_indexed_memory_source_ids(
        self,
        session_id: str,
        source_ids: list[str],
        embedding_model: str,
        embedding_provider: str,
    ) -> set[str]:
        self.get_session(session_id)
        if not source_ids:
            return set()

        placeholders = ", ".join("?" for _ in source_ids)
        rows = self._query_all(
            f"""
            SELECT source_id
            FROM memory_items
            WHERE session_id = ?
              AND source_id IN ({placeholders})
              AND embedding IS NOT NULL
              AND embedding_model = ?
              AND embedding_provider = ?
            """,
            tuple([session_id, *source_ids, embedding_model, embedding_provider]),
        )
        return {row["source_id"] for row in rows}

    def has_indexed_memory(
        self,
        session_id: str,
        embedding_model: str,
        embedding_provider: str,
    ) -> bool:
        self.get_session(session_id)
        row = self._query_one(
            """
            SELECT 1
            FROM memory_items
            WHERE session_id = ?
              AND embedding IS NOT NULL
              AND embedding_model = ?
              AND embedding_provider = ?
            LIMIT 1
            """,
            (session_id, embedding_model, embedding_provider),
        )
        return row is not None

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

    def _load_sqlite_vector(self) -> bool:
        if not hasattr(self._db, "enable_load_extension"):
            logger.info("sqlite-vector unavailable; Python sqlite3 was built without extension loading")
            return False

        try:
            extension_path = importlib.resources.files("sqlite_vector.binaries") / "vector"
            self._db.enable_load_extension(True)
            self._db.load_extension(str(extension_path))
            self._db.enable_load_extension(False)
            version = self._db.execute("SELECT vector_version()").fetchone()
            logger.info("sqlite-vector loaded version=%s", version[0] if version else "unknown")
            return True
        except Exception as err:
            try:
                self._db.enable_load_extension(False)
            except (AttributeError, sqlite3.Error):
                pass
            logger.info("sqlite-vector unavailable; using Python cosine fallback: %s", err)
            return False

    def _ensure_sqlite_vector(self, embedding_dim: int) -> bool:
        if not self._sqlite_vector_available:
            return False
        if embedding_dim in self._sqlite_vector_dimensions:
            return True

        try:
            self._db.execute(
                "SELECT vector_init('memory_items', 'embedding', ?)",
                (f"type=FLOAT32,dimension={embedding_dim},distance=COSINE",),
            )
            self._sqlite_vector_dimensions.add(embedding_dim)
            return True
        except sqlite3.Error:
            logger.exception("sqlite-vector initialization failed; using Python cosine fallback")
            self._sqlite_vector_available = False
            return False

    def _refresh_sqlite_vector_index(self, embedding_dim: int) -> None:
        if not self._ensure_sqlite_vector(embedding_dim):
            return

        try:
            self._db.execute("SELECT vector_quantize('memory_items', 'embedding')")
        except sqlite3.Error:
            logger.exception("sqlite-vector quantize failed; using Python cosine fallback")
            self._sqlite_vector_available = False

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


def summary_from_row(row: sqlite3.Row) -> SessionSummaryRecord:
    return SessionSummaryRecord(
        id=row["id"],
        session_id=row["session_id"],
        content=row["content"],
        covered_message_id=row["covered_message_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def memory_from_row(row: sqlite3.Row) -> MemoryItemRecord:
    return MemoryItemRecord(
        id=row["id"],
        session_id=row["session_id"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        content=row["content"],
        embedding_dim=row["embedding_dim"],
        embedding_model=row["embedding_model"],
        embedding_provider=row["embedding_provider"],
        score=row["score"] if "score" in row.keys() else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def serialize_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def deserialize_vector(blob: bytes) -> list[float]:
    if len(blob) % 4 != 0:
        return []
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def sqlite_cosine_similarity(left_blob: bytes | None, right_blob: bytes | None) -> float | None:
    if left_blob is None or right_blob is None:
        return None

    left = deserialize_vector(left_blob)
    right = deserialize_vector(right_blob)
    if len(left) != len(right) or not left:
        return None

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None

    return dot / (left_norm * right_norm)


def ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("file:"):
        return

    path = database_url.removeprefix("file:").split("?", 1)[0]
    if not path or path == ":memory:":
        return

    directory = Path(path).parent
    if str(directory) not in {"", "."}:
        directory.mkdir(parents=True, exist_ok=True)
