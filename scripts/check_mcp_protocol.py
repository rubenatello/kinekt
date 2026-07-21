from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "agent_turn",
    "get_git_context",
    "query_knowledge_base",
    "read_workspace_file",
    "session_history",
    "session_start",
    "workspace_status",
}


async def _discover_tools(workspace: Path) -> tuple[dict[str, str], dict[str, object] | None]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "kinekt.cli", "mcp-serve", "--allow-workspace", str(workspace)],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            status_response = await session.call_tool("workspace_status", {})
            return (
                {
                    tool.name: tool.description or ""
                    for tool in sorted(response.tools, key=lambda discovered_tool: discovered_tool.name)
                },
                status_response.structuredContent,
            )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kinekt-mcp-check-") as temp_dir:
        workspace = Path(temp_dir).resolve()
        discovered, structured_status = asyncio.run(_discover_tools(workspace))
    payload = {
        "discovered_tools": discovered,
        "expected_tools": sorted(EXPECTED_TOOLS),
        "protocol": "stdio",
        "workspace_status": structured_status,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if set(discovered) != EXPECTED_TOOLS:
        print("MCP protocol check failed")
        return 1
    missing_descriptions = sorted(name for name, description in discovered.items() if not description.strip())
    if missing_descriptions:
        print(f"MCP protocol check failed: missing descriptions for {', '.join(missing_descriptions)}")
        return 1
    status_payload = structured_status.get("result", structured_status) if structured_status is not None else None
    if not isinstance(status_payload, dict) or status_payload.get("root") != str(workspace):
        print("MCP protocol check failed: workspace_status did not resolve the configured default root")
        return 1
    print("MCP protocol check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
