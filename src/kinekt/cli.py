from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent_core import run_agent_turn
from .diagnostics import doctor_report
from .errors import format_error_json, normalize_exception
from .ingest import ingest_workspace
from .limits import (
    clamp_agent_history_window,
    clamp_agent_query_limit,
    clamp_history_limit,
    clamp_query_limit,
    clamp_read_chars,
)
from .mcp_server import run_stdio_server
from .logging_utils import get_logger, log_event
from .query import query_knowledge_base
from .session_store import create_session, list_messages
from .storage import connect, ensure_schema
from .tools import get_git_context, read_workspace_file


def _workspace_db_path(workspace: str) -> Path:
    return Path(workspace).resolve() / ".kinekt" / "kinekt.sqlite3"


def _connect_workspace(workspace: str):
    conn = connect(_workspace_db_path(workspace))
    ensure_schema(conn)
    return conn


def _cmd_init(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    ensure_schema(conn)
    print(f"Initialized Kinekt database at {Path(conn.execute('PRAGMA database_list').fetchone()['file'])}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    stats = ingest_workspace(conn, Path(args.workspace))
    print(f"Scanned: {stats.scanned} | Updated: {stats.updated} | Skipped: {stats.skipped}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    safe_limit = clamp_query_limit(args.limit)
    results = query_knowledge_base(conn, args.query, limit=safe_limit)
    if not results:
        print("No results found. Run ingest first.")
        return 0

    for idx, item in enumerate(results, start=1):
        print(f"[{idx}] {item.file_path} ({item.source}) score={item.score:.4f}")
        preview = " ".join(item.content.split())[:220]
        print(f"    {preview}")
    return 0


def _cmd_git_context(args: argparse.Namespace) -> int:
    print(get_git_context(Path(args.workspace)).rstrip())
    return 0


def _cmd_read_file(args: argparse.Namespace) -> int:
    safe_max_chars = clamp_read_chars(args.max_chars)
    print(read_workspace_file(Path(args.workspace), args.file_path, max_chars=safe_max_chars))
    return 0


def _cmd_mcp_serve(_args: argparse.Namespace) -> int:
    return run_stdio_server()


def _cmd_session_start(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    sid = create_session(conn, session_id=args.session_id)
    print(sid)
    return 0


def _cmd_session_history(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    safe_limit = clamp_history_limit(args.limit)
    rows = list_messages(conn, session_id=args.session_id, limit=safe_limit)
    if not rows:
        print("No messages for this session.")
        return 0
    for row in rows:
        preview = " ".join(row.content.split())[:220]
        print(f"{row.timestamp} [{row.role}] {preview}")
    return 0


def _cmd_agent_turn(args: argparse.Namespace) -> int:
    conn = _connect_workspace(args.workspace)
    safe_query_limit = clamp_agent_query_limit(args.query_limit)
    safe_history_window = clamp_agent_history_window(args.history_window)
    result = run_agent_turn(
        conn=conn,
        workspace=Path(args.workspace),
        user_message=args.message,
        session_id=args.session_id,
        query_limit=safe_query_limit,
        history_window=safe_history_window,
    )
    print(result.reply)
    print(f"\nSession ID: {result.session_id}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    print(doctor_report(Path(args.workspace)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kinekt", description="Kinekt local-first context engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize local Kinekt database")
    p_init.add_argument("workspace", nargs="?", default=".")
    p_init.set_defaults(func=_cmd_init)

    p_ingest = sub.add_parser("ingest", help="Ingest workspace code and markdown")
    p_ingest.add_argument("workspace", nargs="?", default=".")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_query = sub.add_parser("query", help="Query indexed knowledge base")
    p_query.add_argument("query")
    p_query.add_argument("--workspace", default=".")
    p_query.add_argument("--limit", type=int, default=5)
    p_query.set_defaults(func=_cmd_query)

    p_git = sub.add_parser("git-context", help="Show local git status context")
    p_git.add_argument("workspace", nargs="?", default=".")
    p_git.set_defaults(func=_cmd_git_context)

    p_read = sub.add_parser("read-file", help="Read a workspace file safely")
    p_read.add_argument("file_path")
    p_read.add_argument("--workspace", default=".")
    p_read.add_argument("--max-chars", type=int, default=4000)
    p_read.set_defaults(func=_cmd_read_file)

    p_mcp = sub.add_parser("mcp-serve", help="Run FastMCP server over stdio")
    p_mcp.set_defaults(func=_cmd_mcp_serve)

    p_session_start = sub.add_parser("session-start", help="Create or ensure a session ID")
    p_session_start.add_argument("--workspace", default=".")
    p_session_start.add_argument("--session-id")
    p_session_start.set_defaults(func=_cmd_session_start)

    p_session_history = sub.add_parser("session-history", help="List session messages")
    p_session_history.add_argument("session_id")
    p_session_history.add_argument("--workspace", default=".")
    p_session_history.add_argument("--limit", type=int, default=30)
    p_session_history.set_defaults(func=_cmd_session_history)

    p_agent_turn = sub.add_parser("agent-turn", help="Run a stateful agent turn")
    p_agent_turn.add_argument("message")
    p_agent_turn.add_argument("--workspace", default=".")
    p_agent_turn.add_argument("--session-id")
    p_agent_turn.add_argument("--query-limit", type=int, default=4)
    p_agent_turn.add_argument("--history-window", type=int, default=6)
    p_agent_turn.set_defaults(func=_cmd_agent_turn)

    p_doctor = sub.add_parser("doctor", help="Show local runtime diagnostics")
    p_doctor.add_argument("workspace", nargs="?", default=".")
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main() -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args()
    logger = get_logger("kinekt.cli")
    command = getattr(args, "command", "unknown")
    log_event(logger, "cli_command_start", command=command)
    try:
        rc = args.func(args)
        log_event(logger, "cli_command_success", command=command, rc=rc)
        return rc
    except Exception as exc:
        err = normalize_exception(exc)
        log_event(logger, "cli_command_error", command=command, code=err.code, message=err.message)
        print(format_error_json(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
