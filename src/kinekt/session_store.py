from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from .limits import MAX_SESSION_ID_CHARS, MAX_STORED_MESSAGE_CHARS, validate_text

_VALID_ROLES = {"user", "assistant", "tool"}
MAX_SESSION_SUMMARY_CHARS = 4_000
MAX_SUMMARY_MESSAGE_CHARS = 240


@dataclass(frozen=True)
class ThreadMessage:
    message_id: str
    session_id: str
    role: str
    content: str
    timestamp: str


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    through_message_sequence: int
    message_count: int
    content: str
    updated_at: str


def create_session(conn: sqlite3.Connection, session_id: str | None = None) -> str:
    sid = (
        validate_text(session_id, field="session_id", maximum=MAX_SESSION_ID_CHARS)
        if session_id is not None
        else str(uuid.uuid4())
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions(session_id, created_at, updated_at)
        VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (sid,),
    )
    conn.commit()
    return sid


def touch_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
        (session_id,),
    )


def append_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    message_id: str | None = None,
) -> str:
    if role not in _VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    clean_content = validate_text(
        content,
        field="content",
        maximum=MAX_STORED_MESSAGE_CHARS,
    )

    mid = message_id or str(uuid.uuid4())
    create_session(conn, session_id=session_id)
    conn.execute(
        """
        INSERT INTO thread_messages(message_id, session_id, role, content, timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (mid, session_id, role, clean_content),
    )
    touch_session(conn, session_id)
    conn.commit()
    return mid


def list_messages(conn: sqlite3.Connection, session_id: str, limit: int = 50) -> list[ThreadMessage]:
    safe_limit = max(1, min(limit, 200))
    rows = conn.execute(
        """
        SELECT message_id, session_id, role, content, timestamp
        FROM thread_messages
        WHERE session_id = ?
        ORDER BY timestamp ASC, rowid ASC
        LIMIT ?
        """,
        (session_id, safe_limit),
    ).fetchall()
    return [
        ThreadMessage(
            message_id=row["message_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
        )
        for row in rows
    ]


def list_recent_messages(
    conn: sqlite3.Connection,
    session_id: str,
    limit: int = 50,
) -> list[ThreadMessage]:
    safe_limit = max(1, min(limit, 200))
    rows = conn.execute(
        """
        SELECT message_id, session_id, role, content, timestamp
        FROM (
            SELECT rowid AS message_sequence, message_id, session_id, role, content, timestamp
            FROM thread_messages
            WHERE session_id = ?
            ORDER BY timestamp DESC, rowid DESC
            LIMIT ?
        )
        ORDER BY timestamp ASC, message_sequence ASC
        """,
        (session_id, safe_limit),
    ).fetchall()
    return [
        ThreadMessage(
            message_id=row["message_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
        )
        for row in rows
    ]


def get_session_summary(conn: sqlite3.Connection, session_id: str) -> SessionSummary | None:
    row = conn.execute(
        """
        SELECT session_id, through_message_sequence, message_count, content, updated_at
        FROM session_summaries
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return SessionSummary(
        session_id=str(row["session_id"]),
        through_message_sequence=int(row["through_message_sequence"]),
        message_count=int(row["message_count"]),
        content=str(row["content"]),
        updated_at=str(row["updated_at"]),
    )


def compact_session_history(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    keep_recent: int = 20,
    max_chars: int = MAX_SESSION_SUMMARY_CHARS,
) -> SessionSummary | None:
    """Incrementally summarize messages older than the retained recent window."""
    safe_keep_recent = max(1, min(keep_recent, 200))
    safe_max_chars = max(256, min(max_chars, MAX_SESSION_SUMMARY_CHARS))
    cutoff = conn.execute(
        """
        SELECT rowid AS message_sequence
        FROM thread_messages
        WHERE session_id = ?
        ORDER BY rowid DESC
        LIMIT 1 OFFSET ?
        """,
        (session_id, safe_keep_recent),
    ).fetchone()
    existing = get_session_summary(conn, session_id)
    if cutoff is None:
        return existing

    cutoff_sequence = int(cutoff["message_sequence"])
    previous_sequence = existing.through_message_sequence if existing is not None else 0
    if cutoff_sequence <= previous_sequence:
        return existing

    rows = conn.execute(
        """
        SELECT rowid AS message_sequence, role, content
        FROM thread_messages
        WHERE session_id = ? AND rowid > ? AND rowid <= ?
        ORDER BY rowid ASC
        """,
        (session_id, previous_sequence, cutoff_sequence),
    ).fetchall()
    if not rows:
        return existing

    summary_lines = existing.content.splitlines() if existing is not None else []
    for row in rows:
        normalized = " ".join(str(row["content"]).split())[:MAX_SUMMARY_MESSAGE_CHARS]
        summary_lines.append(f"[{row['role']}] {normalized}")
    while summary_lines and len("\n".join(summary_lines)) > safe_max_chars:
        summary_lines.pop(0)
    content = "\n".join(summary_lines)
    message_count = (existing.message_count if existing is not None else 0) + len(rows)
    conn.execute(
        """
        INSERT INTO session_summaries(
            session_id, through_message_sequence, message_count, content, updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id)
        DO UPDATE SET
            through_message_sequence = excluded.through_message_sequence,
            message_count = excluded.message_count,
            content = excluded.content,
            updated_at = CURRENT_TIMESTAMP
        """,
        (session_id, cutoff_sequence, message_count, content),
    )
    conn.commit()
    return get_session_summary(conn, session_id)


def upsert_profile_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO developer_profile(key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )
    conn.commit()


def get_profile_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM developer_profile WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])
