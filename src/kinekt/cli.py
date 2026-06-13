from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import ingest_workspace
from .mcp_server import run_stdio_server
from .query import query_knowledge_base
from .storage import connect, ensure_schema
from .tools import get_git_context, read_workspace_file


def _cmd_init(_args: argparse.Namespace) -> int:
    conn = connect()
    ensure_schema(conn)
    print(f"Initialized Kinekt database at {Path(conn.execute('PRAGMA database_list').fetchone()['file'])}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    conn = connect()
    ensure_schema(conn)
    stats = ingest_workspace(conn, Path(args.workspace))
    print(f"Scanned: {stats.scanned} | Updated: {stats.updated} | Skipped: {stats.skipped}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    conn = connect()
    ensure_schema(conn)
    results = query_knowledge_base(conn, args.query, limit=args.limit)
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
    print(read_workspace_file(Path(args.workspace), args.file_path, max_chars=args.max_chars))
    return 0


def _cmd_mcp_serve(_args: argparse.Namespace) -> int:
    return run_stdio_server()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kinekt", description="Kinekt local-first context engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize local Kinekt database")
    p_init.set_defaults(func=_cmd_init)

    p_ingest = sub.add_parser("ingest", help="Ingest workspace code and markdown")
    p_ingest.add_argument("workspace", nargs="?", default=".")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_query = sub.add_parser("query", help="Query indexed knowledge base")
    p_query.add_argument("query")
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
