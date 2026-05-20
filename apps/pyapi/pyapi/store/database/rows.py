from __future__ import annotations

import sqlite3

from ..models import MemoryItemRecord, MessageRecord, SessionRecord, SessionSummaryRecord


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
