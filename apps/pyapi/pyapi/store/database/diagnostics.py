from __future__ import annotations

from ..models import MemoryItemRecord
from .rows import memory_from_row


class DiagnosticsStoreMixin:
    def list_memory_items(self, session_id: str) -> list[MemoryItemRecord]:
        self.get_session(session_id)
        rows = self._query_all(
            """
            SELECT
              id, session_id, source_type, source_id, content, embedding_dim, embedding_model,
              embedding_provider, created_at, updated_at
            FROM memory_items
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return [memory_from_row(row) for row in rows]
