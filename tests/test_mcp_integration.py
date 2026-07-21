from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_server_lists_documented_tools(tmp_path: Path) -> None:
    async def run_check() -> tuple[dict[str, str], dict[str, object] | None]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "kinekt.cli",
                "mcp-serve",
                "--allow-workspace",
                str(tmp_path),
            ],
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.list_tools()
                status_response = await session.call_tool("workspace_status", {})
                return (
                    {tool.name: tool.description or "" for tool in response.tools},
                    status_response.structuredContent,
                )

    discovered, structured_status = asyncio.run(run_check())
    assert sorted(discovered) == [
        "agent_turn",
        "get_git_context",
        "query_knowledge_base",
        "read_workspace_file",
        "session_history",
        "session_start",
        "workspace_status",
    ]
    assert all(description.strip() for description in discovered.values())
    assert structured_status is not None
    status = structured_status.get("result", structured_status)
    assert isinstance(status, dict)
    assert status["root"] == str(tmp_path.resolve())
