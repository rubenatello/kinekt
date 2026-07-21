from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_AGENTS = ("codex", "claude", "gemini", "generic")


@dataclass(frozen=True)
class AgentLaunch:
    workspace: Path
    mount_source: str | None
    transport: str
    command: str
    args: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "mount_source": self.mount_source,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
        }


def _is_absolute_mount_source(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or (
        len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in {"/", "\\"}
    )


def build_agent_launch(
    workspace: Path,
    *,
    docker: bool,
    image: str = "kinekt:local",
    mount_source: str | None = None,
) -> AgentLaunch:
    root = workspace.resolve()
    if not docker and mount_source is not None:
        raise ValueError("--mount-source can only be used with --docker")
    if docker:
        source_text = mount_source.strip() if mount_source is not None else str(root)
        if not _is_absolute_mount_source(source_text):
            raise ValueError("Docker mount source must be an absolute host path")
        if "," in source_text:
            raise ValueError("Docker --mount setup does not support a workspace path containing a comma")
        return AgentLaunch(
            workspace=root,
            mount_source=source_text,
            transport="docker",
            command="docker",
            args=(
                "run",
                "--rm",
                "-i",
                "--env",
                f"KINEKT_WORKSPACE_ROOT_ALIAS={source_text}",
                "--mount",
                f"type=bind,source={source_text},target=/workspace",
                image,
                "mcp-serve",
                "--allow-workspace",
                "/workspace",
            ),
        )
    return AgentLaunch(
        workspace=root,
        mount_source=None,
        transport="native",
        command="kinekt",
        args=("mcp-serve", "--allow-workspace", str(root)),
    )


def _config_payload(agent: str, launch: AgentLaunch) -> dict[str, Any]:
    server: dict[str, Any] = {"command": launch.command, "args": list(launch.args)}
    if agent == "gemini":
        server.update({"timeout": 30_000, "trust": False})
    return {"mcpServers": {"kinekt": server}}


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _codex_config(launch: AgentLaunch) -> str:
    args = ", ".join(_toml_string(arg) for arg in launch.args)
    return "\n".join(
        (
            "[mcp_servers.kinekt]",
            f"command = {_toml_string(launch.command)}",
            f"args = [{args}]",
            "startup_timeout_sec = 10",
            "tool_timeout_sec = 60",
        )
    )


def rendered_config(agent: str, launch: AgentLaunch) -> str:
    normalized = agent.strip().lower()
    if normalized not in SUPPORTED_AGENTS:
        raise ValueError(f"Unsupported agent: {agent}")
    if normalized == "codex":
        return _codex_config(launch)
    return json.dumps(_config_payload(normalized, launch), indent=2, ensure_ascii=False)


def agent_setup_payload(agent: str, launch: AgentLaunch) -> dict[str, Any]:
    normalized = agent.strip().lower()
    if normalized not in SUPPORTED_AGENTS:
        raise ValueError(f"Unsupported agent: {agent}")
    payload = launch.as_dict()
    payload.update({"agent": normalized, "config": rendered_config(normalized, launch)})
    return payload


def agent_setup_instructions(agent: str, launch: AgentLaunch) -> str:
    normalized = agent.strip().lower()
    config = rendered_config(normalized, launch)
    if normalized == "codex":
        location = "Save this in project .codex/config.toml or the global Codex config.toml:"
        verify = "Start a new Codex session, run `/mcp`, and confirm that `kinekt` is available."
    elif normalized == "claude":
        location = "Merge this into Claude Desktop's claude_desktop_config.json:"
        verify = "Restart Claude Desktop and confirm that Kinekt appears in its MCP integrations."
    elif normalized == "gemini":
        location = "Merge this into project .gemini/settings.json or the global Gemini settings.json:"
        verify = "Start a new Gemini CLI session and inspect its MCP server status."
    else:
        location = "Use this stdio MCP server definition in your client's MCP configuration:"
        verify = "Restart the client and confirm that it discovers the Kinekt tools."
    return "\n\n".join(
        (
            f"Kinekt agent setup ({normalized}, {launch.transport})",
            f"Workspace: {launch.mount_source or launch.workspace}",
            location,
            config,
            verify,
        )
    )
