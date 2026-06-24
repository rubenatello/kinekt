from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .chunking import embed_text
from .limits import clamp_query_limit
from .vector_store import get_vector_store


@dataclass(frozen=True)
class QueryResult:
    chunk_id: str
    file_path: str
    score: float
    content: str
    source: str


def query_knowledge_base(conn: sqlite3.Connection, text: str, limit: int = 5) -> list[QueryResult]:
    safe_limit = clamp_query_limit(limit)
    query_vec = embed_text(text)
    store = get_vector_store(conn)
    rows = store.query(conn, query_vec=query_vec, query_text=text, limit=safe_limit)
    return [
        QueryResult(
            chunk_id=str(row["chunk_id"]),
            file_path=str(row["file_path"]),
            score=float(row["score"]),
            content=str(row["content"]),
            source=str(row["source"]),
        )
        for row in rows
    ]
