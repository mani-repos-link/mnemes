from __future__ import annotations

from ..ids import new_id, timestamp
from ..models import SessionSummaryRecord
from .rows import summary_from_row


class SummaryStoreMixin:
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
