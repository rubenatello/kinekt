from __future__ import annotations

from pathlib import Path

import pytest

from kinekt.agent_core import run_agent_turn
from kinekt.ingest import ingest_workspace
from kinekt.limits import MAX_SESSION_ID_CHARS, MAX_USER_MESSAGE_CHARS
from kinekt.session_store import (
    append_message,
    compact_session_history,
    create_session,
    get_profile_value,
    get_session_summary,
    list_messages,
    list_recent_messages,
    upsert_profile_value,
)
from kinekt.storage import connect, ensure_schema


def test_agent_turn_persists_session_and_messages(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nKinekt keeps local-first context for engineers.")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    first = run_agent_turn(conn, workspace=workspace, user_message="where is local context?")
    second = run_agent_turn(
        conn,
        workspace=workspace,
        user_message="and how is it stored?",
        session_id=first.session_id,
    )

    assert first.session_id == second.session_id
    messages = list_messages(conn, first.session_id, limit=10)
    assert len(messages) == 4
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert "Prior turns in this session" in second.reply
    assert "Recent conversation" in second.reply
    assert "where is local context?" in second.retrieval_query
    assert "Generation backend: deterministic" in second.reply


def test_session_store_profile_and_role_validation(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    sid = create_session(conn)
    append_message(conn, sid, role="user", content="hello")

    with pytest.raises(ValueError):
        append_message(conn, sid, role="invalid", content="nope")

    upsert_profile_value(conn, "team", "platform")
    upsert_profile_value(conn, "team", "core-platform")
    assert get_profile_value(conn, "team") == "core-platform"

    with pytest.raises(ValueError, match="maximum length"):
        create_session(conn, session_id="s" * (MAX_SESSION_ID_CHARS + 1))


def test_agent_turn_rejects_oversized_user_message(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)

    with pytest.raises(ValueError, match="maximum length"):
        run_agent_turn(conn, workspace, "x" * (MAX_USER_MESSAGE_CHARS + 1))


def test_list_recent_messages_returns_latest_window_in_chronological_order(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    sid = create_session(conn)
    for index in range(6):
        append_message(conn, sid, "user", f"message-{index}")

    messages = list_recent_messages(conn, sid, limit=3)

    assert [message.content for message in messages] == ["message-3", "message-4", "message-5"]


def test_session_compaction_is_bounded_incremental_and_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    sid = create_session(conn, session_id="long-session")
    for index in range(8):
        append_message(conn, sid, "user", f"constraint-{index} " + ("detail " * 30))

    first = compact_session_history(conn, sid, keep_recent=3, max_chars=300)
    repeated = compact_session_history(conn, sid, keep_recent=3, max_chars=300)

    assert first is not None
    assert repeated == first
    assert first.message_count == 5
    assert len(first.content) <= 300
    assert "constraint-4" in first.content
    assert "constraint-5" not in first.content

    append_message(conn, sid, "assistant", "new response")
    updated = compact_session_history(conn, sid, keep_recent=3, max_chars=300)
    assert updated is not None
    assert updated.message_count == 6
    assert updated.through_message_sequence > first.through_message_sequence
    assert get_session_summary(conn, sid) == updated


def test_agent_turn_uses_compacted_history_in_retrieval_and_generation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "database.md").write_text("# Database\nPostgreSQL persistence requirement")
    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)
    sid = create_session(conn, session_id="summary-session")
    append_message(conn, sid, "user", "The database must remain PostgreSQL")
    for index in range(6):
        append_message(conn, sid, "assistant", f"intermediate response {index}")

    result = run_agent_turn(
        conn,
        workspace,
        "What persistence constraint should we keep?",
        session_id=sid,
        history_window=1,
    )

    assert result.session_summary is not None
    assert "PostgreSQL" in result.session_summary
    assert "PostgreSQL" in result.retrieval_query
    assert "Earlier conversation summary" in result.reply
