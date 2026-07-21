from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from kinekt.ingest import ingest_workspace
from kinekt.mcp_server import (
    _mcp_error_payload,
    _run_tool_with_error_contract,
    create_mcp_server,
    tool_agent_turn,
    tool_query_knowledge_base,
    tool_read_workspace_file,
    tool_session_history,
    tool_session_start,
    tool_workspace_status,
)
from kinekt.storage import connect, ensure_schema


@pytest.fixture(autouse=True)
def _allow_test_workspace_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_ALLOWED_WORKSPACES", str(tmp_path))


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


def test_tool_workspace_status_confirms_authorized_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    status = tool_workspace_status(workspace=str(workspace))

    assert status["root"] == str(workspace.resolve())
    assert status["detection_method"] == "authorized"
    assert status["attached"] is False


def test_tool_rejects_workspace_outside_allowed_roots_without_creating_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("KINEKT_ALLOWED_WORKSPACES", str(allowed))

    with pytest.raises(PermissionError, match="allowed root"):
        tool_session_start(workspace=str(outside))

    assert not (outside / ".kinekt").exists()


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
        return SimpleNamespace(session_id="sid", reply="ok", retrieval_query="hello", session_summary=None, hits=[])

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


def test_mcp_error_payload_shape() -> None:
    payload = _mcp_error_payload("read_workspace_file", ValueError("bad path"))
    assert payload == {"code": "ERR_INVALID_ARGUMENT", "message": "bad path"}


def test_run_tool_with_error_contract_raises_json_runtime_error() -> None:
    def boom():
        raise ValueError("bad input")

    with pytest.raises(RuntimeError) as exc_info:
        _run_tool_with_error_contract("query_knowledge_base", boom)

    payload = json.loads(str(exc_info.value))
    assert payload == {"code": "ERR_INVALID_ARGUMENT", "message": "bad input"}


def test_create_mcp_server_registers_documented_tool_names(monkeypatch) -> None:
    registered: list[tuple[str, str]] = []

    class FakeFastMCP:
        def __init__(self, _name: str) -> None:
            pass

        def tool(self, *, description: str):
            def decorator(fn):
                registered.append((fn.__name__, description))
                return fn

            return decorator

    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FakeFastMCP
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)

    create_mcp_server()

    assert [name for name, _ in registered] == [
        "query_knowledge_base",
        "get_git_context",
        "workspace_status",
        "read_workspace_file",
        "session_start",
        "session_history",
        "agent_turn",
    ]
    assert all(description.strip() for _, description in registered)
