from __future__ import annotations

from pathlib import Path

from kinekt.tools import read_workspace_file


def test_read_workspace_file_clamps_max_chars(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    content = "a" * 60_000
    (workspace / "notes.md").write_text(content)

    clipped = read_workspace_file(workspace, "notes.md", max_chars=999_999)
    assert len(clipped) == 50_000


def test_read_workspace_file_clamps_to_minimum_one_char(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("hello")

    clipped = read_workspace_file(workspace, "notes.md", max_chars=0)
    assert clipped == "h"


def test_read_workspace_file_strips_utf8_bom(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("\ufeffhello", encoding="utf-8")

    content = read_workspace_file(workspace, "notes.md", max_chars=20)
    assert content == "hello"
