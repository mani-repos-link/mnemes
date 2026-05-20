from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from pyapi.config import ToolConfig

from .args import int_arg, string_arg

BLOCKED_SQL = re.compile(r"\b(attach|alter|analyze|create|delete|detach|drop|insert|pragma|reindex|replace|update|vacuum)\b", re.I)


def run_sqlite_query(config: ToolConfig, arguments: dict[str, Any]) -> str:
    query = string_arg(arguments, "query", "").strip()
    max_rows = int_arg(arguments, "max_rows", 50, minimum=1, maximum=200)
    validate_readonly_query(query)

    with connect_readonly(config.database_url) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchmany(max_rows + 1)

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    payload = {
        "rows": [dict(row) for row in rows],
        "rowCount": len(rows),
        "truncated": truncated,
    }
    return json.dumps(payload, indent=2)


def run_list_memory(config: ToolConfig, arguments: dict[str, Any], current_session_id: str | None = None) -> str:
    session_id = session_id_arg(arguments, current_session_id)
    limit = int_arg(arguments, "limit", 20, minimum=1, maximum=100)
    with connect_readonly(config.database_url) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT source_type, source_id, embedding_provider, updated_at, substr(content, 1, 500) AS content
            FROM memory_items
            WHERE session_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return json.dumps([dict(row) for row in rows], indent=2)


def run_search_memory(config: ToolConfig, arguments: dict[str, Any], current_session_id: str | None = None) -> str:
    session_id = session_id_arg(arguments, current_session_id)
    query = string_arg(arguments, "query", "").strip()
    limit = int_arg(arguments, "limit", 10, minimum=1, maximum=50)
    if not query:
        raise ValueError("search_memory requires a query")

    terms = [term for term in re.findall(r"[A-Za-z0-9_]+", query.lower()) if len(term) >= 3][:8]
    if not terms:
        return "[]"
    clause = " OR ".join("lower(content) LIKE ?" for _term in terms)
    params: list[object] = [session_id, *[f"%{term}%" for term in terms], limit]

    with connect_readonly(config.database_url) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT source_type, source_id, embedding_provider, updated_at, substr(content, 1, 800) AS content
            FROM memory_items
            WHERE session_id = ?
              AND ({clause})
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return json.dumps([dict(row) for row in rows], indent=2)


def run_explain_context(config: ToolConfig, arguments: dict[str, Any], current_session_id: str | None = None) -> str:
    session_id = session_id_arg(arguments, current_session_id)
    with connect_readonly(config.database_url) as connection:
        connection.row_factory = sqlite3.Row
        messages = connection.execute(
            """
            SELECT id, role, content, parent_message_id, active_response_id, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        memory_source_ids = {
            row["source_id"]
            for row in connection.execute(
                """
                SELECT source_id
                FROM memory_items
                WHERE session_id = ? AND source_type = 'message'
                """,
                (session_id,),
            ).fetchall()
        }
        summary = connection.execute(
            """
            SELECT covered_message_id, updated_at, substr(content, 1, 800) AS content
            FROM session_summaries
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        memory_count = connection.execute(
            "SELECT count(*) AS count FROM memory_items WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"]

    context_messages = active_context_messages(messages)
    raw_messages = messages_after_indexed_prefix(context_messages, memory_source_ids)
    payload = {
        "sessionId": session_id,
        "memoryMode": config.memory_mode,
        "rawLimit": config.context_memory_trigger_message_limit,
        "bufferLimit": config.context_memory_buffer_message_limit,
        "retrievalTopK": config.retrieval_top_k,
        "messageCount": len(messages),
        "activeContextMessageCount": len(context_messages),
        "indexedMessageMemoryCount": len(memory_source_ids),
        "memoryItemCount": memory_count,
        "summary": dict(summary) if summary else None,
        "rawMessagesSent": [
            {
                "id": row["id"],
                "role": row["role"],
                "createdAt": row["created_at"],
                "preview": row["content"][:240],
            }
            for row in raw_messages
        ],
    }
    return json.dumps(payload, indent=2)


def validate_readonly_query(query: str) -> None:
    if not query:
        raise ValueError("sqlite_query requires a query")
    stripped = query.rstrip(";").strip()
    if ";" in stripped:
        raise ValueError("sqlite_query accepts one statement only")
    if not re.match(r"^(select|with)\b", stripped, re.I):
        raise ValueError("sqlite_query only allows SELECT queries")
    if BLOCKED_SQL.search(stripped):
        raise ValueError("sqlite_query only allows read-only SELECT queries")


def connect_readonly(database_url: str) -> sqlite3.Connection:
    if database_url.startswith("file:"):
        separator = "&" if "?" in database_url else "?"
        return sqlite3.connect(f"{database_url}{separator}mode=ro", uri=True)
    return sqlite3.connect(f"file:{database_url}?mode=ro", uri=True)


def session_id_arg(arguments: dict[str, Any], current_session_id: str | None) -> str:
    session_id = string_arg(arguments, "session_id", current_session_id or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    return session_id


def active_context_messages(messages: list[sqlite3.Row]) -> list[sqlite3.Row]:
    by_id = {message["id"]: message for message in messages}
    context: list[sqlite3.Row] = []
    for message in messages:
        if message["role"] == "assistant" and message["parent_message_id"]:
            continue
        if message["role"] == "user":
            context.append(message)
            active_response_id = message["active_response_id"]
            if active_response_id and active_response_id in by_id:
                context.append(by_id[active_response_id])
            continue
        if message["role"] in {"assistant", "system"}:
            context.append(message)
    return context


def messages_after_indexed_prefix(messages: list[sqlite3.Row], indexed_source_ids: set[str]) -> list[sqlite3.Row]:
    prefix_end = -1
    for index, message in enumerate(messages):
        if message["role"] in {"user", "assistant"} and message["id"] not in indexed_source_ids:
            break
        prefix_end = index
    return messages[prefix_end + 1 :]
