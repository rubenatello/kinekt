from __future__ import annotations

import subprocess
from pathlib import Path

_MAX_READ_CHARS = 50_000


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
    safe_max_chars = max(1, min(max_chars, _MAX_READ_CHARS))
    return target.read_text(encoding="utf-8", errors="ignore")[:safe_max_chars]
