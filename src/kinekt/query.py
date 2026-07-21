from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .embeddings import embed_text
from .index_state import current_index_configuration, validate_query_configuration
from .limits import MAX_QUERY_CHARS, clamp_query_limit, validate_text
from .vector_store import get_vector_store


@dataclass(frozen=True)
class QueryResult:
    chunk_id: str
    file_path: str
    score: float
    content: str
    source: str
    symbol_name: str = ""
    start_line: int = 1
    end_line: int = 1
    vector_score: float = 0.0
    lexical_score: float = 0.0
    path_score: float = 0.0
    symbol_score: float = 0.0
    source_score: float = 0.0
    ranking_reason: str = ""


def query_knowledge_base(conn: sqlite3.Connection, text: str, limit: int = 5) -> list[QueryResult]:
    clean_text = validate_text(text, field="query", maximum=MAX_QUERY_CHARS)
    safe_limit = clamp_query_limit(limit)
    query_vec = embed_text(clean_text)
    store = get_vector_store(conn)
    current_config = current_index_configuration(store.backend_name)
    validate_query_configuration(conn, current_config)
    rows = store.query(conn, query_vec=query_vec, query_text=clean_text, limit=safe_limit)
    return [
        QueryResult(
            chunk_id=str(row["chunk_id"]),
            file_path=str(row["file_path"]),
            score=float(row["score"]),
            content=str(row["content"]),
            source=str(row["source"]),
            symbol_name=str(row.get("symbol_name", "")),
            start_line=int(row.get("start_line", 1)),
            end_line=int(row.get("end_line", 1)),
            vector_score=float(row.get("vector_score", 0.0)),
            lexical_score=float(row.get("lexical_score", 0.0)),
            path_score=float(row.get("path_score", 0.0)),
            symbol_score=float(row.get("symbol_score", 0.0)),
            source_score=float(row.get("source_score", 0.0)),
            ranking_reason=str(row.get("ranking_reason", "")),
        )
        for row in rows
    ]
