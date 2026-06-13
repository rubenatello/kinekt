from __future__ import annotations

from pathlib import Path

import pytest

from kinekt.ingest import ingest_workspace
from kinekt.mcp_server import tool_query_knowledge_base, tool_read_workspace_file
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
