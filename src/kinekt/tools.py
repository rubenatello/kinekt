from __future__ import annotations

import subprocess
from pathlib import Path

from .limits import clamp_read_chars


def get_git_context(repo_path: Path) -> str:
    repo_path = repo_path.resolve()
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "--no-pager",
        "status",
        "--short",
        "--branch",
    ]
    return subprocess.check_output(cmd, text=True)


def read_workspace_file(workspace: Path, file_path: str, max_chars: int = 4000) -> str:
    workspace = workspace.resolve()
    target = (workspace / file_path).resolve()
    if workspace not in target.parents and target != workspace:
        raise ValueError("Requested path is outside workspace")
    safe_max_chars = clamp_read_chars(max_chars)
    return target.read_text(encoding="utf-8", errors="ignore")[:safe_max_chars]
