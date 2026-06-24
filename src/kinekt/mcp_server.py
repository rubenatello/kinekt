from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_core import run_agent_turn
from .errors import normalize_exception
from .limits import (
    clamp_agent_history_window,
    clamp_agent_query_limit,
    clamp_history_limit,
    clamp_query_limit,
    clamp_read_chars,
)
from .query import query_knowledge_base as run_query_knowledge_base
from .session_store import create_session, list_messages
from .storage import connect, ensure_schema
from .tools import get_git_context, read_workspace_file
from .logging_utils import get_logger, log_event

_DEFAULT_READ_CHARS = 4_000
_LOGGER = get_logger("kinekt.mcp")


def _workspace_db_path(workspace: str) -> Path:
    return Path(workspace).resolve() / ".kinekt" / "kinekt.sqlite3"


def _workspace_conn(workspace: str):
    conn = connect(_workspace_db_path(workspace))
    ensure_schema(conn)
    return conn


def tool_query_knowledge_base(query: str, workspace: str = ".", limit: int = 5) -> list[dict[str, Any]]:
    safe_limit = clamp_query_limit(limit)
    conn = _workspace_conn(workspace)
    rows = run_query_knowledge_base(conn, query, limit=safe_limit)
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
    safe_max_chars = clamp_read_chars(max_chars)
    return read_workspace_file(Path(workspace), file_path, max_chars=safe_max_chars)


def tool_session_start(workspace: str = ".", session_id: str | None = None) -> str:
    conn = _workspace_conn(workspace)
    return create_session(conn, session_id=session_id)


def tool_session_history(session_id: str, workspace: str = ".", limit: int = 30) -> list[dict[str, str]]:
    conn = _workspace_conn(workspace)
    safe_limit = clamp_history_limit(limit)
    rows = list_messages(conn, session_id=session_id, limit=safe_limit)
    return [
        {
            "message_id": row.message_id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "timestamp": row.timestamp,
        }
        for row in rows
    ]


def tool_agent_turn(
    message: str,
    workspace: str = ".",
    session_id: str | None = None,
    query_limit: int = 4,
    history_window: int = 6,
) -> dict[str, Any]:
    conn = _workspace_conn(workspace)
    safe_query_limit = clamp_agent_query_limit(query_limit)
    safe_history_window = clamp_agent_history_window(history_window)
    result = run_agent_turn(
        conn=conn,
        workspace=Path(workspace),
        user_message=message,
        session_id=session_id,
        query_limit=safe_query_limit,
        history_window=safe_history_window,
    )
    return {"session_id": result.session_id, "reply": result.reply, "hits": result.hits}


def _mcp_error_payload(_tool_name: str, exc: Exception) -> dict[str, str]:
    err = normalize_exception(exc)
    return {"code": err.code, "message": err.message}


def _run_tool_with_error_contract(tool_name: str, fn, **kwargs):
    try:
        result = fn(**kwargs)
        log_event(_LOGGER, "mcp_tool_success", tool=tool_name)
        return result
    except Exception as exc:
        payload = _mcp_error_payload(tool_name, exc)
        log_event(
            _LOGGER,
            "mcp_tool_error",
            tool=tool_name,
            code=payload["code"],
            message=payload["message"],
            details=exc.__class__.__name__,
        )
        raise RuntimeError(json.dumps(payload, sort_keys=True)) from exc


def create_mcp_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "FastMCP is not installed. Install with: python -m pip install 'kinekt[mcp]'"
        ) from exc

    mcp = FastMCP("kinekt")

    @mcp.tool()
    def query_knowledge_base(query: str, workspace: str = ".", limit: int = 5) -> list[dict[str, Any]]:
        return _run_tool_with_error_contract(
            "query_knowledge_base",
            tool_query_knowledge_base,
            query=query,
            workspace=workspace,
            limit=limit,
        )

    @mcp.tool()
    def get_git_context(workspace: str = ".") -> str:
        return _run_tool_with_error_contract("get_git_context", tool_get_git_context, workspace=workspace)

    @mcp.tool()
    def read_workspace_file(file_path: str, workspace: str = ".", max_chars: int = _DEFAULT_READ_CHARS) -> str:
        return _run_tool_with_error_contract(
            "read_workspace_file",
            tool_read_workspace_file,
            file_path=file_path,
            workspace=workspace,
            max_chars=max_chars,
        )

    @mcp.tool()
    def session_start(workspace: str = ".", session_id: str | None = None) -> str:
        return _run_tool_with_error_contract("session_start", tool_session_start, workspace=workspace, session_id=session_id)

    @mcp.tool()
    def session_history(session_id: str, workspace: str = ".", limit: int = 30) -> list[dict[str, str]]:
        return _run_tool_with_error_contract(
            "session_history",
            tool_session_history,
            session_id=session_id,
            workspace=workspace,
            limit=limit,
        )

    @mcp.tool()
    def agent_turn(
        message: str,
        workspace: str = ".",
        session_id: str | None = None,
        query_limit: int = 4,
        history_window: int = 6,
    ) -> dict[str, Any]:
        return _run_tool_with_error_contract(
            "agent_turn",
            tool_agent_turn,
            message=message,
            workspace=workspace,
            session_id=session_id,
            query_limit=query_limit,
            history_window=history_window,
        )

    return mcp


def run_stdio_server() -> int:
    server = create_mcp_server()
    server.run(transport="stdio")
    return 0
