from __future__ import annotations

import subprocess
from pathlib import Path

from .limits import clamp_read_chars
from .text_files import read_utf8_text
from .workspace import resolve_workspace, resolve_workspace_file


def get_git_context(repo_path: Path) -> str:
    repo_path = resolve_workspace(repo_path)
    cmd = [
        "git",
        "--no-optional-locks",
        "-C",
        str(repo_path),
        "--no-pager",
        "status",
        "--short",
        "--branch",
    ]
    return subprocess.check_output(cmd, text=True, timeout=15)


def read_workspace_file(workspace: Path, file_path: str, max_chars: int = 4000) -> str:
    workspace = resolve_workspace(workspace)
    target = resolve_workspace_file(workspace, workspace / file_path)
    safe_max_chars = clamp_read_chars(max_chars)
    return read_utf8_text(target)[:safe_max_chars]
