from __future__ import annotations

import os
from pathlib import Path


def resolve_workspace(workspace: Path) -> Path:
    resolved = workspace.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Workspace does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Workspace is not a directory: {resolved}")
    return resolved


def is_within_workspace(workspace: Path, target: Path) -> bool:
    return target == workspace or workspace in target.parents


def resolve_workspace_file(workspace: Path, path: Path) -> Path:
    resolved_workspace = resolve_workspace(workspace)
    resolved_target = path.resolve(strict=True)
    if not is_within_workspace(resolved_workspace, resolved_target):
        raise ValueError(f"Resolved path is outside workspace: {path}")
    if not resolved_target.is_file():
        raise ValueError(f"Workspace path is not a regular file: {path}")
    return resolved_target


def configured_workspace_roots() -> tuple[Path, ...]:
    raw = os.getenv("KINEKT_ALLOWED_WORKSPACES", "").strip()
    candidates = [Path(part) for part in raw.split(os.pathsep) if part.strip()] if raw else [Path.cwd()]
    roots: list[Path] = []
    for candidate in candidates:
        resolved = resolve_workspace(candidate)
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def requested_workspace(workspace: Path) -> Path:
    default_workspace = os.getenv("KINEKT_DEFAULT_WORKSPACE", "").strip()
    if str(workspace).strip() in {"", "."} and default_workspace:
        return Path(default_workspace)
    return workspace


def authorize_workspace(workspace: Path) -> Path:
    resolved = resolve_workspace(requested_workspace(workspace))
    allowed_roots = configured_workspace_roots()
    if not any(is_within_workspace(root, resolved) for root in allowed_roots):
        allowed = ", ".join(str(root) for root in allowed_roots)
        raise PermissionError(f"Workspace is not under an allowed root: {resolved}. Allowed roots: {allowed}")
    return resolved
