from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .agent_core import run_agent_turn
from .agent_setup import SUPPORTED_AGENTS, agent_setup_instructions, agent_setup_payload, build_agent_launch
from .diagnostics import doctor_report
from .errors import format_error_json, normalize_exception
from .evaluation import evaluate_retrieval, load_evaluation_cases
from .index_state import index_counts, load_index_configuration
from .ingest import IngestStats, ingest_workspace
from .limits import (
    clamp_agent_history_window,
    clamp_agent_query_limit,
    clamp_history_limit,
    clamp_query_limit,
    clamp_read_chars,
)
from .logging_utils import get_logger, log_event
from .mcp_server import run_stdio_server
from .query import query_knowledge_base
from .session_store import create_session, list_messages
from .storage import connect, ensure_schema, validate_schema
from .tools import get_git_context, read_workspace_file
from .workspace import resolve_workspace
from .workspace_discovery import (
    WorkspaceStatus,
    attach_workspace,
    discover_workspace,
    discover_workspace_status,
    inspect_workspace,
)


def _command_workspace(workspace: str | Path | None, *, require_attached_for_auto: bool = False) -> Path:
    if workspace is None:
        status = discover_workspace_status()
        if require_attached_for_auto and not status.attached:
            raise PermissionError(f"Workspace is not attached: {status.root}. Run `kinekt attach` first.")
        return status.root
    return resolve_workspace(Path(workspace))


def _workspace_db_path(workspace: str | Path | None) -> Path:
    return _command_workspace(workspace) / ".kinekt" / "kinekt.sqlite3"


def _connect_workspace(workspace: str | Path | None, *, initialize: bool = True) -> sqlite3.Connection:
    conn = connect(_workspace_db_path(workspace), create=initialize, read_only=not initialize)
    if initialize:
        ensure_schema(conn)
    else:
        validate_schema(conn)
    return conn


def _ingest_summary(stats: IngestStats) -> str:
    return (
        f"Scanned: {stats.scanned} | Updated: {stats.updated} | Skipped: {stats.skipped} "
        f"| Pruned: {stats.pruned} | Rebuilt: {'yes' if stats.rebuilt else 'no'} "
        f"| Duration: {stats.duration_ms:.1f} ms"
    )


def _print_workspace_status(status: WorkspaceStatus) -> None:
    print("Kinekt Workspace")
    print(f"Project: {status.project_name}")
    print(f"Root: {status.root}")
    detection = status.detection_method
    if status.detection_marker:
        detection = f"{detection} ({status.detection_marker})"
    print(f"Detection: {detection}")
    print(f"Git repository: {'yes' if status.is_git_repository else 'no'}")
    print(f"Git branch: {status.git_branch or 'unavailable'}")
    print(f"Attached: {'yes' if status.attached else 'no'}")
    if status.attachment_error:
        print(f"Attachment warning: {status.attachment_error}")
    print(f"Attachment file: {status.attachment_path}")
    print(f"Database exists: {'yes' if status.database_exists else 'no'}")


def _cmd_attach(args: argparse.Namespace) -> int:
    start = Path(args.workspace) if args.workspace is not None else None
    discovery = discover_workspace(start)
    status = inspect_workspace(
        discovery.root,
        detection_method=discovery.method,
        detection_marker=discovery.marker,
    )

    if not status.attached:
        if not args.json:
            _print_workspace_status(status)
            print("\nAfter attachment, Kinekt can read supported project files and git status.")
            if args.ingest:
                print("This command will also initialize and index supported project files.")
            print(f"Kinekt writes local state only under: {status.root / '.kinekt'}")
        if not args.yes:
            if args.json:
                raise RuntimeError("New JSON attachment requires --yes so stdout remains machine-readable")
            if not sys.stdin.isatty():
                raise RuntimeError("Workspace confirmation requires an interactive terminal or --yes")
            answer = input("\nAttach this workspace? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Workspace attachment cancelled.")
                return 0
        status = attach_workspace(discovery)

    ingest_stats = None
    if args.ingest:
        with closing(_connect_workspace(status.root)) as conn:
            ingest_stats = ingest_workspace(conn, status.root)
        status = inspect_workspace(
            discovery.root,
            detection_method=discovery.method,
            detection_marker=discovery.marker,
        )

    if args.json:
        payload = status.as_dict()
        payload["ingest"] = None
        if ingest_stats is not None:
            payload["ingest"] = {
                "scanned": ingest_stats.scanned,
                "updated": ingest_stats.updated,
                "skipped": ingest_stats.skipped,
                "pruned": ingest_stats.pruned,
                "rebuilt": ingest_stats.rebuilt,
                "duration_ms": ingest_stats.duration_ms,
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"\nWorkspace attached: {status.root}")
        if ingest_stats is not None:
            print(_ingest_summary(ingest_stats))
        else:
            print("Next: run `kinekt ingest` from this repository.")
    return 0


def _cmd_workspace_status(args: argparse.Namespace) -> int:
    start = Path(args.workspace) if args.workspace is not None else None
    status = discover_workspace_status(start)
    if args.json:
        print(json.dumps(status.as_dict(), indent=2, sort_keys=True))
    else:
        _print_workspace_status(status)
    return 0


def _cmd_agent_setup(args: argparse.Namespace) -> int:
    start = Path(args.workspace) if args.workspace is not None else None
    status = discover_workspace_status(start)
    if not status.attached:
        raise PermissionError(f"Workspace is not attached: {status.root}. Run `kinekt attach` first.")
    launch = build_agent_launch(
        status.root,
        docker=args.docker,
        image=args.image,
        mount_source=args.mount_source,
    )
    if args.json:
        print(json.dumps(agent_setup_payload(args.agent, launch), indent=2, sort_keys=True))
    else:
        print(agent_setup_instructions(args.agent, launch))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace, require_attached_for_auto=True)
    with closing(_connect_workspace(workspace)) as conn:
        print(f"Initialized Kinekt database at {Path(conn.execute('PRAGMA database_list').fetchone()['file'])}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace, require_attached_for_auto=True)
    with closing(_connect_workspace(workspace)) as conn:
        stats = ingest_workspace(conn, workspace)
    print(_ingest_summary(stats))
    return 0


def _cmd_reindex(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace, require_attached_for_auto=True)
    with closing(_connect_workspace(workspace)) as conn:
        stats = ingest_workspace(conn, workspace, force_rebuild=True)
    print(_ingest_summary(stats))
    return 0


def _cmd_index_status(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace)
    with closing(_connect_workspace(workspace, initialize=False)) as conn:
        config = load_index_configuration(conn)
        counts = index_counts(conn)
    print(f"Workspace: {workspace}")
    if config is None:
        print("Index configuration: missing (run `kinekt reindex <workspace>`)")
    else:
        print(f"Index fingerprint: {config.fingerprint}")
        print(f"Vector backend: {config.vector_backend}")
        print(f"Embedding backend: {config.embedding_backend}")
        print(f"Embedding model: {config.embedding_model}")
        print(f"Embedding dimension: {config.embedding_dimension}")
        print(f"Chunker version: {config.chunker_version}")
    print(f"Indexed files: {counts['file_registry']}")
    print(f"Code chunks: {counts['code_chunks']}")
    print(f"Note chunks: {counts['notes_chunks']}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    dataset_name, cases = load_evaluation_cases(Path(args.cases))
    workspace = _command_workspace(args.workspace)
    with closing(_connect_workspace(workspace, initialize=False)) as conn:
        report = evaluate_retrieval(
            conn,
            dataset_name,
            cases,
            limit=args.limit,
        )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace)
    with closing(_connect_workspace(workspace, initialize=False)) as conn:
        safe_limit = clamp_query_limit(args.limit)
        results = query_knowledge_base(conn, args.query, limit=safe_limit)
    if not results:
        print("No results found. Run ingest first.")
        return 0

    for idx, item in enumerate(results, start=1):
        location = f"{item.file_path}:{item.start_line}-{item.end_line}"
        symbol = f" symbol={item.symbol_name}" if item.symbol_name else ""
        print(f"[{idx}] {location} ({item.source}) score={item.score:.4f}{symbol}")
        if getattr(args, "explain", False):
            print(
                f"    ranking={item.ranking_reason} vector={item.vector_score:.4f} "
                f"lexical={item.lexical_score:.4f} path={item.path_score:.4f} "
                f"symbol={item.symbol_score:.4f} source={item.source_score:.4f}"
            )
        preview = " ".join(item.content.split())[:220]
        print(f"    {preview}")
    return 0


def _cmd_git_context(args: argparse.Namespace) -> int:
    print(get_git_context(_command_workspace(args.workspace)).rstrip())
    return 0


def _cmd_read_file(args: argparse.Namespace) -> int:
    safe_max_chars = clamp_read_chars(args.max_chars)
    print(read_workspace_file(_command_workspace(args.workspace), args.file_path, max_chars=safe_max_chars))
    return 0


def _cmd_mcp_serve(args: argparse.Namespace) -> int:
    if args.attached and args.allow_workspace:
        raise ValueError("Use either --attached or --allow-workspace, not both")
    roots: list[str] = []
    if args.attached:
        status = discover_workspace_status()
        if not status.attached:
            raise PermissionError(f"Workspace is not attached: {status.root}. Run `kinekt attach` first.")
        roots = [str(status.root)]
    elif args.allow_workspace:
        roots = [str(resolve_workspace(Path(path))) for path in args.allow_workspace]
    if roots:
        os.environ["KINEKT_ALLOWED_WORKSPACES"] = os.pathsep.join(roots)
        if len(roots) == 1:
            os.environ["KINEKT_DEFAULT_WORKSPACE"] = roots[0]
    return run_stdio_server()


def _cmd_session_start(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace, require_attached_for_auto=True)
    with closing(_connect_workspace(workspace)) as conn:
        sid = create_session(conn, session_id=args.session_id)
    print(sid)
    return 0


def _cmd_session_history(args: argparse.Namespace) -> int:
    workspace = _command_workspace(args.workspace)
    with closing(_connect_workspace(workspace, initialize=False)) as conn:
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
    workspace = _command_workspace(args.workspace, require_attached_for_auto=True)
    with closing(_connect_workspace(workspace)) as conn:
        safe_query_limit = clamp_agent_query_limit(args.query_limit)
        safe_history_window = clamp_agent_history_window(args.history_window)
        result = run_agent_turn(
            conn=conn,
            workspace=workspace,
            user_message=args.message,
            session_id=args.session_id,
            query_limit=safe_query_limit,
            history_window=safe_history_window,
        )
    print(result.reply)
    print(f"\nSession ID: {result.session_id}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    print(doctor_report(_command_workspace(args.workspace)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kinekt", description="Kinekt local-first context engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_attach = sub.add_parser("attach", help="Detect and confirm the current repository")
    p_attach.add_argument("workspace", nargs="?", default=None)
    p_attach.add_argument("--yes", action="store_true", help="Confirm non-interactively")
    p_attach.add_argument("--ingest", action="store_true", help="Initialize and ingest after confirmation")
    p_attach.add_argument("--json", action="store_true", help="Emit machine-readable status")
    p_attach.set_defaults(func=_cmd_attach)

    p_workspace_status = sub.add_parser("workspace-status", help="Show the detected and attached workspace")
    p_workspace_status.add_argument("workspace", nargs="?", default=None)
    p_workspace_status.add_argument("--json", action="store_true", help="Emit machine-readable status")
    p_workspace_status.set_defaults(func=_cmd_workspace_status)

    p_agent_setup = sub.add_parser("agent-setup", help="Generate MCP configuration for a coding agent")
    p_agent_setup.add_argument("agent", choices=SUPPORTED_AGENTS)
    p_agent_setup.add_argument("workspace", nargs="?", default=None)
    p_agent_setup.add_argument("--docker", action="store_true", help="Generate a Docker-backed MCP launch")
    p_agent_setup.add_argument("--image", default="kinekt:local", help="Docker image used with --docker")
    p_agent_setup.add_argument(
        "--mount-source",
        help="Absolute host workspace path when generating Docker config from inside a container",
    )
    p_agent_setup.add_argument("--json", action="store_true", help="Emit structured launch configuration")
    p_agent_setup.set_defaults(func=_cmd_agent_setup)

    p_init = sub.add_parser("init", help="Initialize local Kinekt database")
    p_init.add_argument("workspace", nargs="?", default=None)
    p_init.set_defaults(func=_cmd_init)

    p_ingest = sub.add_parser("ingest", help="Ingest workspace code and markdown")
    p_ingest.add_argument("workspace", nargs="?", default=None)
    p_ingest.set_defaults(func=_cmd_ingest)

    p_reindex = sub.add_parser("reindex", help="Rebuild the workspace index from scratch")
    p_reindex.add_argument("workspace", nargs="?", default=None)
    p_reindex.set_defaults(func=_cmd_reindex)

    p_index_status = sub.add_parser("index-status", help="Show index configuration and row counts")
    p_index_status.add_argument("workspace", nargs="?", default=None)
    p_index_status.set_defaults(func=_cmd_index_status)

    p_eval = sub.add_parser("eval", help="Evaluate retrieval against a versioned JSON case set")
    p_eval.add_argument("cases", help="Path to the evaluation JSON file")
    p_eval.add_argument("--workspace", default=None)
    p_eval.add_argument("--limit", type=int, default=5)
    p_eval.set_defaults(func=_cmd_eval)

    p_query = sub.add_parser("query", help="Query indexed knowledge base")
    p_query.add_argument("query")
    p_query.add_argument("--workspace", default=None)
    p_query.add_argument("--limit", type=int, default=5)
    p_query.add_argument("--explain", action="store_true", help="Show ranking score components")
    p_query.set_defaults(func=_cmd_query)

    p_git = sub.add_parser("git-context", help="Show local git status context")
    p_git.add_argument("workspace", nargs="?", default=None)
    p_git.set_defaults(func=_cmd_git_context)

    p_read = sub.add_parser("read-file", help="Read a workspace file safely")
    p_read.add_argument("file_path")
    p_read.add_argument("--workspace", default=None)
    p_read.add_argument("--max-chars", type=int, default=4000)
    p_read.set_defaults(func=_cmd_read_file)

    p_mcp = sub.add_parser("mcp-serve", help="Run FastMCP server over stdio")
    p_mcp.add_argument(
        "--allow-workspace",
        action="append",
        help="Allow MCP access to this workspace root and its descendants (repeatable)",
    )
    p_mcp.add_argument(
        "--attached",
        action="store_true",
        help="Use the confirmed workspace detected from the current directory",
    )
    p_mcp.set_defaults(func=_cmd_mcp_serve)

    p_session_start = sub.add_parser("session-start", help="Create or ensure a session ID")
    p_session_start.add_argument("--workspace", default=None)
    p_session_start.add_argument("--session-id")
    p_session_start.set_defaults(func=_cmd_session_start)

    p_session_history = sub.add_parser("session-history", help="List session messages")
    p_session_history.add_argument("session_id")
    p_session_history.add_argument("--workspace", default=None)
    p_session_history.add_argument("--limit", type=int, default=30)
    p_session_history.set_defaults(func=_cmd_session_history)

    p_agent_turn = sub.add_parser("agent-turn", help="Run a stateful agent turn")
    p_agent_turn.add_argument("message")
    p_agent_turn.add_argument("--workspace", default=None)
    p_agent_turn.add_argument("--session-id")
    p_agent_turn.add_argument("--query-limit", type=int, default=4)
    p_agent_turn.add_argument("--history-window", type=int, default=6)
    p_agent_turn.set_defaults(func=_cmd_agent_turn)

    p_doctor = sub.add_parser("doctor", help="Show local runtime diagnostics")
    p_doctor.add_argument("workspace", nargs="?", default=None)
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (TypeError, ValueError, OSError):
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
