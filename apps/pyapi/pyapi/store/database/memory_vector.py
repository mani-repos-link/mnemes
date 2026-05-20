from __future__ import annotations

import importlib.resources
import logging
import math
import sqlite3
import struct

from ..ids import timestamp
from ..models import MemoryItemRecord
from .rows import memory_from_row

logger = logging.getLogger("pyapi.store")


class VectorMemoryStoreMixin:
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
