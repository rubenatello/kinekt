from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kinekt.ingest import ingest_workspace
from kinekt.mcp_server import (
    tool_agent_turn,
    tool_query_knowledge_base,
    tool_read_workspace_file,
    tool_session_history,
    tool_session_start,
)
from kinekt.storage import connect, ensure_schema


def test_tool_query_knowledge_base_returns_ranked_rows(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nKinekt keeps local developer context.")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = tool_query_knowledge_base("developer context", workspace=str(workspace), limit=5)
    assert results
    assert results[0]["file_path"] == "notes.md"


def test_tool_query_knowledge_base_clamps_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for i in range(40):
        (workspace / f"n{i}.md").write_text(f"# N{i}\ncontent {i}")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = tool_query_knowledge_base("content", workspace=str(workspace), limit=500)
    assert len(results) <= 20


def test_tool_read_workspace_file_blocks_path_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    with pytest.raises(ValueError):
        tool_read_workspace_file(file_path="../outside.txt", workspace=str(workspace))


def test_tool_agent_turn_and_session_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nsession based memory")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    sid = tool_session_start(workspace=str(workspace))
    turn = tool_agent_turn(message="where is session memory?", workspace=str(workspace), session_id=sid)
    history = tool_session_history(session_id=sid, workspace=str(workspace), limit=10)

    assert turn["session_id"] == sid
    assert history
    assert history[0]["role"] == "user"


def test_tool_agent_turn_clamps_limits_before_agent_core(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)

    captured: dict[str, int] = {}

    def fake_run_agent_turn(**kwargs):
        captured["query_limit"] = kwargs["query_limit"]
        captured["history_window"] = kwargs["history_window"]
        return SimpleNamespace(session_id="sid", reply="ok", hits=[])

    monkeypatch.setattr("kinekt.mcp_server.run_agent_turn", fake_run_agent_turn)

    result = tool_agent_turn(
        message="hello",
        workspace=str(workspace),
        query_limit=999,
        history_window=999,
    )

    assert result["session_id"] == "sid"
    assert captured["query_limit"] == 10
    assert captured["history_window"] == 20
