from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .generation import generate_agent_reply
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

    generation = generate_agent_reply(
        workspace=_workspace_header(workspace),
        session_id=sid,
        user_message=clean_message,
        hits=hits,
        prior_user_count=prior_user_count,
    )
    reply = f"{generation.text}\n\nGeneration backend: {generation.backend}"

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
