from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import kinekt.workspace_discovery as workspace_discovery
from kinekt.workspace import authorize_workspace
from kinekt.workspace_discovery import (
    ATTACHMENT_RELATIVE_PATH,
    WorkspaceDiscovery,
    attach_workspace,
    discover_workspace,
    discover_workspace_status,
    inspect_workspace,
)


def _git_init(path: Path) -> None:
    result = subprocess.run(["git", "init", str(path)], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        pytest.skip(f"git init unavailable: {result.stderr}")


def test_discovers_git_root_from_nested_editor_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "src" / "package"
    nested.mkdir(parents=True)
    _git_init(workspace)

    discovery = discover_workspace(nested)

    assert discovery.root == workspace.resolve()
    assert discovery.start_path == nested.resolve()
    assert discovery.method == "git"


def test_discovers_nearest_project_marker_without_git(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "src"
    nested.mkdir(parents=True)
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")

    discovery = discover_workspace(nested)

    assert discovery.root == workspace.resolve()
    assert discovery.method == "marker"
    assert discovery.marker == "pyproject.toml"


def test_discovery_uses_environment_workspace_when_no_path_is_given(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "go.mod").write_text("module example.test/demo\n")
    monkeypatch.setenv("KINEKT_WORKSPACE", str(workspace))

    assert discover_workspace().root == workspace.resolve()


def test_discovery_fails_instead_of_guessing_unmarked_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="No Git or recognized project root"):
        discover_workspace(workspace)


def test_discovery_rejects_git_root_outside_start_path(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    monkeypatch.setattr(workspace_discovery, "_git_output", lambda _workspace, *_args: str(outside))

    with pytest.raises(ValueError, match="outside the discovery path"):
        discover_workspace(workspace)


def test_attach_persists_confirmed_workspace_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Cargo.toml").write_text("[package]\nname='demo'\n")
    discovery = discover_workspace(workspace)

    status = attach_workspace(discovery)
    payload = json.loads((workspace / ATTACHMENT_RELATIVE_PATH).read_text(encoding="utf-8"))

    assert status.attached is True
    assert payload["schema_version"] == 1
    assert payload["workspace_root"] == str(workspace.resolve())
    assert payload["confirmed"] is True


def test_inspection_rejects_attachment_for_different_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = workspace / ".kinekt"
    state_dir.mkdir()
    (state_dir / "workspace.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_root": str(tmp_path / "other"),
                "confirmed": True,
            }
        ),
        encoding="utf-8",
    )

    status = inspect_workspace(workspace)

    assert status.attached is False
    assert status.attachment_error == "attachment metadata was created for a different workspace path"


def test_inspection_accepts_explicit_container_root_alias(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = workspace / ".kinekt"
    state_dir.mkdir()
    host_root = "C:\\Projects\\demo"
    (state_dir / "workspace.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_root": host_root,
                "project_name": "demo",
                "confirmed": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KINEKT_WORKSPACE_ROOT_ALIAS", host_root)

    status = inspect_workspace(workspace)

    assert status.attached is True
    assert status.project_name == "demo"


def test_attachment_created_in_container_can_be_confirmed_on_host(tmp_path: Path, monkeypatch) -> None:
    container_workspace = tmp_path / "container-workspace"
    container_workspace.mkdir()
    (container_workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")
    host_root = "C:\\Projects\\demo"
    monkeypatch.setenv("KINEKT_WORKSPACE_ROOT_ALIAS", host_root)

    attach_workspace(discover_workspace(container_workspace))
    payload = json.loads((container_workspace / ATTACHMENT_RELATIVE_PATH).read_text(encoding="utf-8"))

    assert payload["workspace_root_aliases"] == [host_root]
    assert payload["project_name"] == "demo"


def test_attach_rejects_symlinked_state_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "package.json").write_text("{}")
    try:
        (workspace / ".kinekt").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this environment: {exc}")

    discovery = WorkspaceDiscovery(root=workspace, start_path=workspace, method="marker", marker="package.json")
    with pytest.raises(ValueError, match="cannot be a symlink"):
        attach_workspace(discovery)


def test_workspace_status_reports_database_presence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")
    attach_workspace(discover_workspace(workspace))
    (workspace / ".kinekt" / "kinekt.sqlite3").touch()

    status = discover_workspace_status(workspace)

    assert status.root == workspace.resolve()
    assert status.attached is True
    assert status.database_exists is True


def test_mcp_default_workspace_resolves_to_single_configured_root(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("KINEKT_ALLOWED_WORKSPACES", str(workspace))
    monkeypatch.setenv("KINEKT_DEFAULT_WORKSPACE", str(workspace))

    assert authorize_workspace(Path(".")) == workspace.resolve()
