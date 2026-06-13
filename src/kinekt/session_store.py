from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import uuid

_VALID_ROLES = {"user", "assistant", "tool"}


@dataclass(frozen=True)
class ThreadMessage:
    message_id: str
    session_id: str
    role: str
    content: str
    timestamp: str


def create_session(conn: sqlite3.Connection, session_id: str | None = None) -> str:
    sid = session_id or str(uuid.uuid4())
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

    mid = message_id or str(uuid.uuid4())
    create_session(conn, session_id=session_id)
    conn.execute(
        """
        INSERT INTO thread_messages(message_id, session_id, role, content, timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (mid, session_id, role, content),
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
