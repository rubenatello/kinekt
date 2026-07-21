from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .workspace import resolve_workspace

ATTACHMENT_SCHEMA_VERSION = 1
ATTACHMENT_RELATIVE_PATH = Path(".kinekt") / "workspace.json"
MAX_ATTACHMENT_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 5.0
WORKSPACE_ROOT_ALIAS_ENV = "KINEKT_WORKSPACE_ROOT_ALIAS"
MAX_ROOT_ALIAS_CHARS = 4_096

_PROJECT_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    ".idea",
)


@dataclass(frozen=True)
class WorkspaceDiscovery:
    root: Path
    start_path: Path
    method: str
    marker: str | None = None


@dataclass(frozen=True)
class WorkspaceStatus:
    root: Path
    project_name: str
    detection_method: str
    detection_marker: str | None
    is_git_repository: bool
    git_branch: str | None
    attached: bool
    attachment_path: Path
    attachment_error: str | None
    database_exists: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "project_name": self.project_name,
            "detection_method": self.detection_method,
            "detection_marker": self.detection_marker,
            "is_git_repository": self.is_git_repository,
            "git_branch": self.git_branch,
            "attached": self.attached,
            "attachment_path": str(self.attachment_path),
            "attachment_error": self.attachment_error,
            "database_exists": self.database_exists,
        }


def _git_output(workspace: Path, *args: str) -> str | None:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _starting_directory(start: Path | None) -> Path:
    if start is None:
        configured = os.getenv("KINEKT_WORKSPACE", "").strip()
        candidate = Path(configured) if configured else Path.cwd()
    else:
        candidate = start
    resolved = candidate.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Workspace discovery path does not exist: {resolved}")
    return resolved.parent if resolved.is_file() else resolved


def _nearest_marker_root(start: Path) -> tuple[Path, str] | None:
    for candidate in (start, *start.parents):
        for marker in _PROJECT_MARKERS:
            if (candidate / marker).exists():
                return candidate, marker
    return None


def discover_workspace(start: Path | None = None) -> WorkspaceDiscovery:
    """Detect the nearest repository/project root without writing to it."""
    start_path = _starting_directory(start)
    git_root_raw = _git_output(start_path, "rev-parse", "--show-toplevel")
    if git_root_raw:
        git_root = resolve_workspace(Path(git_root_raw))
        if start_path != git_root and git_root not in start_path.parents:
            raise ValueError(f"Git reported a root outside the discovery path: {git_root}")
        return WorkspaceDiscovery(root=git_root, start_path=start_path, method="git")

    marker_result = _nearest_marker_root(start_path)
    if marker_result is not None:
        root, marker = marker_result
        return WorkspaceDiscovery(root=resolve_workspace(root), start_path=start_path, method="marker", marker=marker)

    raise ValueError(
        f"No Git or recognized project root found from {start_path}. "
        "Run the command from a repository or set KINEKT_WORKSPACE to an explicit project root."
    )


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _is_absolute_path_text(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or (
        len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in {"/", "\\"}
    )


def _read_attachment(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    attachment_path = root / ATTACHMENT_RELATIVE_PATH
    if not attachment_path.exists():
        return None, None
    if attachment_path.is_symlink() or not attachment_path.is_file():
        return None, "attachment metadata is not a regular file"
    if attachment_path.stat().st_size > MAX_ATTACHMENT_BYTES:
        return None, "attachment metadata exceeds the safe size limit"
    try:
        payload = json.loads(attachment_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"attachment metadata is unreadable: {exc}"
    if not isinstance(payload, dict):
        return None, "attachment metadata must be a JSON object"
    if payload.get("schema_version") != ATTACHMENT_SCHEMA_VERSION:
        return None, "attachment metadata uses an unsupported schema version"
    stored_root = payload.get("workspace_root")
    if not isinstance(stored_root, str) or not stored_root.strip():
        return None, "attachment metadata is missing workspace_root"
    stored_aliases = payload.get("workspace_root_aliases", [])
    if not isinstance(stored_aliases, list) or not all(isinstance(alias, str) for alias in stored_aliases):
        return None, "attachment metadata has invalid workspace_root_aliases"
    if len(stored_aliases) > 8:
        return None, "attachment metadata contains too many workspace root aliases"
    recorded_roots = [stored_root, *stored_aliases]
    if any(
        not recorded
        or len(recorded) > MAX_ROOT_ALIAS_CHARS
        or "\x00" in recorded
        or not _is_absolute_path_text(recorded)
        for recorded in recorded_roots
    ):
        return None, "attachment metadata contains an invalid workspace root"
    try:
        root_matches = any(_normalized_path(Path(recorded)) == _normalized_path(root) for recorded in recorded_roots)
    except (OSError, ValueError):
        return None, "attachment metadata contains an invalid workspace root"
    root_alias = os.getenv(WORKSPACE_ROOT_ALIAS_ENV, "").strip()
    alias_matches = bool(root_alias) and root_alias in recorded_roots
    if not root_matches and not alias_matches:
        return None, "attachment metadata was created for a different workspace path"
    if payload.get("confirmed") is not True:
        return None, "attachment metadata is not confirmed"
    return payload, None


def inspect_workspace(
    root: Path,
    *,
    detection_method: str = "explicit",
    detection_marker: str | None = None,
) -> WorkspaceStatus:
    resolved = resolve_workspace(root)
    attachment, attachment_error = _read_attachment(resolved)
    branch = _git_output(resolved, "branch", "--show-current")
    is_git = _git_output(resolved, "rev-parse", "--is-inside-work-tree") == "true"
    if not is_git and (resolved / ".git").exists():
        is_git = True
    attached_project_name = attachment.get("project_name") if attachment is not None else None
    return WorkspaceStatus(
        root=resolved,
        project_name=(
            attached_project_name
            if isinstance(attached_project_name, str) and attached_project_name.strip()
            else resolved.name or str(resolved)
        ),
        detection_method=detection_method,
        detection_marker=detection_marker,
        is_git_repository=is_git,
        git_branch=branch,
        attached=attachment is not None,
        attachment_path=resolved / ATTACHMENT_RELATIVE_PATH,
        attachment_error=attachment_error,
        database_exists=(resolved / ".kinekt" / "kinekt.sqlite3").is_file(),
    )


def discover_workspace_status(start: Path | None = None) -> WorkspaceStatus:
    discovery = discover_workspace(start)
    return inspect_workspace(
        discovery.root,
        detection_method=discovery.method,
        detection_marker=discovery.marker,
    )


def attach_workspace(discovery: WorkspaceDiscovery) -> WorkspaceStatus:
    """Persist explicit local confirmation under the detected workspace state directory."""
    root = resolve_workspace(discovery.root)
    state_dir = root / ".kinekt"
    if state_dir.is_symlink():
        raise ValueError(f"Kinekt state directory cannot be a symlink: {state_dir}")
    if state_dir.exists() and not state_dir.is_dir():
        raise ValueError(f"Kinekt state path is not a directory: {state_dir}")
    state_dir.mkdir(parents=False, exist_ok=True)
    if not state_dir.is_dir():
        raise ValueError(f"Kinekt state path is not a directory: {state_dir}")

    attachment_path = root / ATTACHMENT_RELATIVE_PATH
    if attachment_path.is_symlink():
        raise ValueError(f"Kinekt attachment file cannot be a symlink: {attachment_path}")

    root_alias = os.getenv(WORKSPACE_ROOT_ALIAS_ENV, "").strip()
    if root_alias and (
        len(root_alias) > MAX_ROOT_ALIAS_CHARS or "\x00" in root_alias or not _is_absolute_path_text(root_alias)
    ):
        raise ValueError(f"{WORKSPACE_ROOT_ALIAS_ENV} must be an absolute host path")
    project_name = root.name or str(root)
    if root_alias:
        alias_name = root_alias.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        project_name = alias_name or project_name
    payload = {
        "schema_version": ATTACHMENT_SCHEMA_VERSION,
        "workspace_root": str(root),
        "workspace_root_aliases": [root_alias] if root_alias and root_alias != str(root) else [],
        "project_name": project_name,
        "detection_method": discovery.method,
        "detection_marker": discovery.marker,
        "confirmed": True,
        "confirmed_at": datetime.now(UTC).isoformat(),
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_dir,
            prefix="workspace-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = Path(temp_file.name)
        os.replace(temp_path, attachment_path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return inspect_workspace(
        root,
        detection_method=discovery.method,
        detection_marker=discovery.marker,
    )
