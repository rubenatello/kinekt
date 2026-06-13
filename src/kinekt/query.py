from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .chunking import cosine_similarity, embed_text


@dataclass(frozen=True)
class QueryResult:
    chunk_id: str
    file_path: str
    score: float
    content: str
    source: str


def _query_table(conn: sqlite3.Connection, table: str, query_vec: list[float], limit: int) -> list[QueryResult]:
    if table == "code_chunks":
        rows = conn.execute(
            "SELECT chunk_id, file_path, content, embedding_json FROM code_chunks"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT chunk_id, file_path, content, embedding_json FROM notes_chunks"
        ).fetchall()

    scored: list[QueryResult] = []
    for row in rows:
        emb = json.loads(row["embedding_json"])
        score = cosine_similarity(query_vec, emb)
        scored.append(
            QueryResult(
                chunk_id=row["chunk_id"],
                file_path=row["file_path"],
                score=score,
                content=row["content"],
                source=table,
            )
        )

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]


def query_knowledge_base(conn: sqlite3.Connection, text: str, limit: int = 5) -> list[QueryResult]:
    query_vec = embed_text(text)
    combined = _query_table(conn, "code_chunks", query_vec, limit) + _query_table(
        conn, "notes_chunks", query_vec, limit
    )
    combined.sort(key=lambda x: x.score, reverse=True)
    return combined[:limit]
