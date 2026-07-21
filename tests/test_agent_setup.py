from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from kinekt.agent_setup import agent_setup_instructions, agent_setup_payload, build_agent_launch, rendered_config


def test_native_codex_setup_uses_explicit_workspace(tmp_path: Path) -> None:
    launch = build_agent_launch(tmp_path, docker=False)
    config = rendered_config("codex", launch)

    assert launch.command == "kinekt"
    assert launch.mount_source is None
    assert launch.args == ("mcp-serve", "--allow-workspace", str(tmp_path.resolve()))
    assert "[mcp_servers.kinekt]" in config
    assert str(tmp_path.resolve()).replace("\\", "\\\\") in config
    parsed = tomllib.loads(config)
    assert parsed["mcp_servers"]["kinekt"]["command"] == "kinekt"


def test_docker_setup_mounts_only_confirmed_workspace(tmp_path: Path) -> None:
    launch = build_agent_launch(tmp_path, docker=True, image="kinekt:test-image")

    assert launch.command == "docker"
    assert launch.mount_source == str(tmp_path.resolve())
    assert launch.args[:4] == ("run", "--rm", "-i", "--env")
    assert launch.args[4] == f"KINEKT_WORKSPACE_ROOT_ALIAS={tmp_path.resolve()}"
    assert launch.args[5] == "--mount"
    assert launch.args[6] == f"type=bind,source={tmp_path.resolve()},target=/workspace"
    assert launch.args[7] == "kinekt:test-image"
    assert launch.args[-2:] == ("--allow-workspace", "/workspace")


def test_gemini_setup_is_valid_json(tmp_path: Path) -> None:
    launch = build_agent_launch(tmp_path, docker=False)

    config = json.loads(rendered_config("gemini", launch))

    server = config["mcpServers"]["kinekt"]
    assert server["command"] == "kinekt"
    assert server["timeout"] == 30_000
    assert server["trust"] is False


def test_docker_setup_rejects_comma_in_mount_path(tmp_path: Path) -> None:
    workspace = tmp_path / "repo,unsafe"
    workspace.mkdir()

    with pytest.raises(ValueError, match="containing a comma"):
        build_agent_launch(workspace, docker=True)


def test_docker_setup_accepts_explicit_cross_platform_mount_source(tmp_path: Path) -> None:
    launch = build_agent_launch(tmp_path, docker=True, mount_source="C:\\Projects\\demo")

    assert launch.mount_source == "C:\\Projects\\demo"
    assert "type=bind,source=C:\\Projects\\demo,target=/workspace" in launch.args


def test_native_setup_rejects_docker_mount_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only be used with --docker"):
        build_agent_launch(tmp_path, docker=False, mount_source="C:\\Projects\\demo")


@pytest.mark.parametrize("agent", ["codex", "claude", "gemini", "generic"])
def test_agent_setup_instructions_include_reviewable_config(tmp_path: Path, agent: str) -> None:
    launch = build_agent_launch(tmp_path, docker=False)

    instructions = agent_setup_instructions(agent, launch)
    payload = agent_setup_payload(agent, launch)

    assert f"Kinekt agent setup ({agent}, native)" in instructions
    assert str(tmp_path.resolve()) in instructions
    assert payload["agent"] == agent
    assert payload["config"] in instructions


def test_agent_setup_rejects_unknown_client(tmp_path: Path) -> None:
    launch = build_agent_launch(tmp_path, docker=False)

    with pytest.raises(ValueError, match="Unsupported agent"):
        rendered_config("unknown", launch)
