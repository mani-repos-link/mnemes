from __future__ import annotations

import logging
import re
import sqlite3

from ..ids import timestamp
from ..models import MemoryItemRecord
from .rows import memory_from_row

logger = logging.getLogger("pyapi.store")


class TextMemoryStoreMixin:
    def upsert_text_memory_item(
        self,
        session_id: str,
        source_type: str,
        source_id: str,
        content: str,
    ) -> MemoryItemRecord:
        self.get_session(session_id)
        if source_type not in {"message", "summary"}:
            raise ValueError("invalid memory source type")
        content = content.strip()
        if not content:
            raise ValueError("memory content is required")

        now = timestamp()
        memory_id = f"mem_{source_id}"

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
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 'vectorless', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  content = excluded.content,
                  embedding = NULL,
                  embedding_dim = NULL,
                  embedding_model = NULL,
                  embedding_provider = excluded.embedding_provider,
                  updated_at = excluded.updated_at
                """,
                (memory_id, session_id, source_type, source_id, content, created_at, now),
            )
            self._upsert_memory_fts_row(memory_id, session_id, source_id, content)

        return MemoryItemRecord(
            id=memory_id,
            session_id=session_id,
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding_dim=None,
            embedding_model=None,
            embedding_provider="vectorless",
            score=None,
            created_at=created_at,
            updated_at=now,
        )

    def has_text_memory(self, session_id: str) -> bool:
        self.get_session(session_id)
        row = self._query_one(
            """
            SELECT 1
            FROM memory_items
            WHERE session_id = ?
              AND embedding IS NULL
              AND embedding_provider = 'vectorless'
            LIMIT 1
            """,
            (session_id,),
        )
        return row is not None

    def list_text_memory_source_ids(self, session_id: str, source_ids: list[str]) -> set[str]:
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
              AND embedding IS NULL
              AND embedding_provider = 'vectorless'
            """,
            tuple([session_id, *source_ids]),
        )
        return {row["source_id"] for row in rows}

    def search_text_memory_items(
        self,
        session_id: str,
        query: str,
        limit: int,
        exclude_source_ids: set[str] | None = None,
    ) -> list[MemoryItemRecord]:
        self.get_session(session_id)
        query = query.strip()
        if not query:
            return []

        exclude_source_ids = exclude_source_ids or set()
        if self._memory_fts_available:
            try:
                return self._search_text_memory_items_with_fts(session_id, query, limit, exclude_source_ids)
            except sqlite3.Error:
                logger.exception("memory FTS search failed; falling back to LIKE search")
                self._memory_fts_available = False

        return self._search_text_memory_items_with_like(session_id, query, limit, exclude_source_ids)

    def _search_text_memory_items_with_fts(
        self,
        session_id: str,
        query: str,
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[MemoryItemRecord]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []

        params: list[object] = [fts_query, session_id]
        exclude_clause = ""
        if exclude_source_ids:
            placeholders = ", ".join("?" for _ in exclude_source_ids)
            exclude_clause = f"AND memory_items.source_id NOT IN ({placeholders})"
            params.extend(sorted(exclude_source_ids))
        params.append(limit)

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
              -bm25(memory_items_fts) AS score
            FROM memory_items_fts
            JOIN memory_items ON memory_items.id = memory_items_fts.id
            WHERE memory_items_fts MATCH ?
              AND memory_items.session_id = ?
              AND memory_items.embedding_provider = 'vectorless'
              {exclude_clause}
            ORDER BY bm25(memory_items_fts) ASC, memory_items.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [memory_from_row(row) for row in rows]

    def _search_text_memory_items_with_like(
        self,
        session_id: str,
        query: str,
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[MemoryItemRecord]:
        terms = tokenize_search_query(query)
        if not terms:
            return []

        like_clause = " OR ".join("content LIKE ?" for _term in terms)
        params: list[object] = [session_id, *[f"%{term}%" for term in terms]]
        exclude_clause = ""
        if exclude_source_ids:
            placeholders = ", ".join("?" for _ in exclude_source_ids)
            exclude_clause = f"AND source_id NOT IN ({placeholders})"
            params.extend(sorted(exclude_source_ids))
        params.append(limit)

        rows = self._query_all(
            f"""
            SELECT
              id, session_id, source_type, source_id, content, embedding_dim, embedding_model,
              embedding_provider, created_at, updated_at, 1.0 AS score
            FROM memory_items
            WHERE session_id = ?
              AND embedding_provider = 'vectorless'
              AND ({like_clause})
              {exclude_clause}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [memory_from_row(row) for row in rows]

    def _ensure_memory_fts_table(self) -> None:
        try:
            self._db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts
                USING fts5(id UNINDEXED, session_id UNINDEXED, source_id UNINDEXED, content, tokenize='porter')
                """
            )
            self._memory_fts_available = True
        except sqlite3.Error as err:
            self._memory_fts_available = False
            logger.info("memory FTS unavailable; using LIKE fallback: %s", err)

    def _upsert_memory_fts_row(
        self,
        memory_id: str,
        session_id: str,
        source_id: str,
        content: str,
    ) -> None:
        if not self._memory_fts_available:
            return

        try:
            self._db.execute("DELETE FROM memory_items_fts WHERE id = ?", (memory_id,))
            self._db.execute(
                """
                INSERT INTO memory_items_fts (id, session_id, source_id, content)
                VALUES (?, ?, ?, ?)
                """,
                (memory_id, session_id, source_id, content),
            )
        except sqlite3.Error as err:
            self._memory_fts_available = False
            logger.info("memory FTS indexing unavailable; using LIKE fallback: %s", err)


def tokenize_search_query(query: str, max_terms: int = 12) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in re.findall(r"[A-Za-z0-9_]+", query.lower()):
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms


def build_fts_query(query: str) -> str:
    return " OR ".join(tokenize_search_query(query))
