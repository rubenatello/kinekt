from __future__ import annotations

from pathlib import Path

import pytest

from kinekt.agent_core import run_agent_turn
from kinekt.ingest import ingest_workspace
from kinekt.session_store import append_message, create_session, get_profile_value, list_messages, upsert_profile_value
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
