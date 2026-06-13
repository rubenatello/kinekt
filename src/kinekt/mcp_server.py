from __future__ import annotations

from pathlib import Path
from typing import Any

from .query import query_knowledge_base
from .storage import connect, ensure_schema
from .tools import get_git_context, read_workspace_file

_MAX_READ_CHARS = 50_000
_DEFAULT_READ_CHARS = 4_000
_MAX_QUERY_LIMIT = 20


def tool_query_knowledge_base(query: str, workspace: str = ".", limit: int = 5) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, _MAX_QUERY_LIMIT))
    workspace_path = Path(workspace).resolve()
    conn = connect(workspace_path / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    rows = query_knowledge_base(conn, query, limit=safe_limit)
    return [
        {
            "chunk_id": row.chunk_id,
            "file_path": row.file_path,
            "score": row.score,
            "source": row.source,
            "content": row.content,
        }
        for row in rows
    ]


def tool_get_git_context(workspace: str = ".") -> str:
    return get_git_context(Path(workspace))


def tool_read_workspace_file(
    file_path: str,
    workspace: str = ".",
    max_chars: int = _DEFAULT_READ_CHARS,
) -> str:
    safe_max_chars = max(1, min(max_chars, _MAX_READ_CHARS))
    return read_workspace_file(Path(workspace), file_path, max_chars=safe_max_chars)


def create_mcp_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "FastMCP is not installed. Install with: python -m pip install 'kinekt[mcp]'"
        ) from exc

    mcp = FastMCP("kinekt")

    @mcp.tool()
    def query_knowledge_base_tool(query: str, workspace: str = ".", limit: int = 5) -> list[dict[str, Any]]:
        return tool_query_knowledge_base(query=query, workspace=workspace, limit=limit)

    @mcp.tool()
    def get_git_context_tool(workspace: str = ".") -> str:
        return tool_get_git_context(workspace=workspace)

    @mcp.tool()
    def read_workspace_file_tool(file_path: str, workspace: str = ".", max_chars: int = _DEFAULT_READ_CHARS) -> str:
        return tool_read_workspace_file(file_path=file_path, workspace=workspace, max_chars=max_chars)

    return mcp


def run_stdio_server() -> int:
    server = create_mcp_server()
    server.run(transport="stdio")
    return 0
