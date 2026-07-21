from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .generation import generate_agent_reply
from .limits import (
    MAX_QUERY_CHARS,
    MAX_RESULT_CONTENT_CHARS,
    MAX_USER_MESSAGE_CHARS,
    clamp_agent_history_window,
    clamp_agent_query_limit,
    validate_text,
)
from .query import query_knowledge_base
from .session_store import (
    SessionSummary,
    ThreadMessage,
    append_message,
    compact_session_history,
    create_session,
    list_recent_messages,
)


@dataclass(frozen=True)
class AgentTurnResult:
    session_id: str
    reply: str
    hits: list[dict[str, object]]
    retrieval_query: str
    session_summary: str | None


def _workspace_header(workspace: Path) -> str:
    return str(workspace.resolve())


def _build_retrieval_query(
    user_message: str,
    prior_messages: list[ThreadMessage],
    summary: SessionSummary | None = None,
) -> str:
    prior_user_messages = [message.content for message in prior_messages if message.role == "user"][-3:]
    if not prior_user_messages and summary is None:
        return user_message

    context_parts: list[str] = []
    if summary is not None and summary.content:
        context_parts.append(f"Earlier session summary ({summary.message_count} messages):\n{summary.content}")
    if prior_user_messages:
        context_parts.append(f"Recent user context:\n{chr(10).join(prior_user_messages)}")
    context = "\n".join(context_parts)
    suffix = f"\nCurrent question:\n{user_message}"
    remaining = MAX_QUERY_CHARS - len(suffix)
    if remaining <= 0:
        return user_message[:MAX_QUERY_CHARS]
    return f"{context[-remaining:]}{suffix}"


def run_agent_turn(
    conn: sqlite3.Connection,
    workspace: Path,
    user_message: str,
    session_id: str | None = None,
    query_limit: int = 4,
    history_window: int = 6,
) -> AgentTurnResult:
    clean_message = validate_text(
        user_message,
        field="user_message",
        maximum=MAX_USER_MESSAGE_CHARS,
    )

    sid = create_session(conn, session_id=session_id)
    safe_query_limit = clamp_agent_query_limit(query_limit)
    safe_history_window = clamp_agent_history_window(history_window)
    summary = compact_session_history(conn, sid, keep_recent=safe_history_window * 2)
    history = list_recent_messages(conn, sid, limit=safe_history_window * 2)
    retrieval_query = _build_retrieval_query(clean_message, history, summary)
    append_message(conn, sid, "user", clean_message)

    hits = query_knowledge_base(conn, retrieval_query, limit=safe_query_limit)
    prior_user_count = sum(1 for message in history if message.role == "user")
    prior_messages = [(message.role, message.content) for message in history]

    generation = generate_agent_reply(
        workspace=_workspace_header(workspace),
        session_id=sid,
        user_message=clean_message,
        hits=hits,
        prior_user_count=prior_user_count,
        prior_messages=prior_messages,
        conversation_summary=summary.content if summary is not None else None,
    )
    reply = f"{generation.text}\n\nGeneration backend: {generation.backend}"

    append_message(conn, sid, "assistant", reply)

    formatted_hits = [
        {
            "file_path": hit.file_path,
            "source": hit.source,
            "score": float(hit.score),
            "content": hit.content[:MAX_RESULT_CONTENT_CHARS],
            "symbol_name": hit.symbol_name,
            "start_line": hit.start_line,
            "end_line": hit.end_line,
            "ranking_reason": hit.ranking_reason,
        }
        for hit in hits
    ]
    return AgentTurnResult(
        session_id=sid,
        reply=reply,
        hits=formatted_hits,
        retrieval_query=retrieval_query,
        session_summary=summary.content if summary is not None else None,
    )
