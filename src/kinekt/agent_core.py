from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .limits import clamp_agent_history_window, clamp_agent_query_limit
from .query import query_knowledge_base
from .session_store import append_message, create_session, list_messages


@dataclass(frozen=True)
class AgentTurnResult:
    session_id: str
    reply: str
    hits: list[dict[str, str | float]]


def _workspace_header(workspace: Path) -> str:
    return str(workspace.resolve())


def run_agent_turn(
    conn: sqlite3.Connection,
    workspace: Path,
    user_message: str,
    session_id: str | None = None,
    query_limit: int = 4,
    history_window: int = 6,
) -> AgentTurnResult:
    clean_message = user_message.strip()
    if not clean_message:
        raise ValueError("user_message cannot be empty")

    sid = create_session(conn, session_id=session_id)
    append_message(conn, sid, "user", clean_message)

    safe_query_limit = clamp_agent_query_limit(query_limit)
    safe_history_window = clamp_agent_history_window(history_window)

    hits = query_knowledge_base(conn, clean_message, limit=safe_query_limit)
    history = list_messages(conn, sid, limit=safe_history_window * 2)
    prior_user_count = sum(1 for m in history[:-1] if m.role == "user")

    lines: list[str] = []
    lines.append(f"Session: {sid}")
    lines.append(f"Workspace: {_workspace_header(workspace)}")
    if prior_user_count > 0:
        lines.append(f"Prior turns in this session: {prior_user_count}")

    if hits:
        lines.append("Relevant indexed context:")
        for idx, hit in enumerate(hits, start=1):
            preview = " ".join(hit.content.split())[:140]
            lines.append(f"{idx}. {hit.file_path} [{hit.source}] score={hit.score:.3f} :: {preview}")
    else:
        lines.append("No indexed context found for this query. Run `kinekt ingest <workspace>`.")

    lines.append("Next: refine the query or ask for specific file-level details.")
    reply = "\n".join(lines)

    append_message(conn, sid, "assistant", reply)

    formatted_hits = [
        {
            "file_path": hit.file_path,
            "source": hit.source,
            "score": float(hit.score),
            "content": hit.content,
        }
        for hit in hits
    ]
    return AgentTurnResult(session_id=sid, reply=reply, hits=formatted_hits)
