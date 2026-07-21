from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from .embeddings import embed_text, embedding_identity

CHUNKER_VERSION = "4"
_PROBE_TEXT = "kinekt embedding dimension probe"


@dataclass(frozen=True)
class IndexConfiguration:
    fingerprint: str
    vector_backend: str
    embedding_backend: str
    embedding_model: str
    embedding_dimension: int
    chunker_version: str


def current_index_configuration(vector_backend: str) -> IndexConfiguration:
    embedding_backend, embedding_model = embedding_identity()
    embedding_dimension = len(embed_text(_PROBE_TEXT))
    payload = {
        "chunker_version": CHUNKER_VERSION,
        "embedding_backend": embedding_backend,
        "embedding_dimension": embedding_dimension,
        "embedding_model": embedding_model,
        "vector_backend": vector_backend,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return IndexConfiguration(
        fingerprint=hashlib.sha256(encoded).hexdigest(),
        vector_backend=vector_backend,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        chunker_version=CHUNKER_VERSION,
    )


def load_index_configuration(conn: sqlite3.Connection) -> IndexConfiguration | None:
    row = conn.execute(
        """
        SELECT fingerprint, vector_backend, embedding_backend, embedding_model,
               embedding_dimension, chunker_version
        FROM index_metadata
        WHERE singleton_id = 1
        """
    ).fetchone()
    if row is None:
        return None
    return IndexConfiguration(
        fingerprint=str(row["fingerprint"]),
        vector_backend=str(row["vector_backend"]),
        embedding_backend=str(row["embedding_backend"]),
        embedding_model=str(row["embedding_model"]),
        embedding_dimension=int(row["embedding_dimension"]),
        chunker_version=str(row["chunker_version"]),
    )


def save_index_configuration(conn: sqlite3.Connection, config: IndexConfiguration) -> None:
    conn.execute(
        """
        INSERT INTO index_metadata(
            singleton_id, fingerprint, vector_backend, embedding_backend, embedding_model,
            embedding_dimension, chunker_version, updated_at
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(singleton_id)
        DO UPDATE SET
            fingerprint = excluded.fingerprint,
            vector_backend = excluded.vector_backend,
            embedding_backend = excluded.embedding_backend,
            embedding_model = excluded.embedding_model,
            embedding_dimension = excluded.embedding_dimension,
            chunker_version = excluded.chunker_version,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            config.fingerprint,
            config.vector_backend,
            config.embedding_backend,
            config.embedding_model,
            config.embedding_dimension,
            config.chunker_version,
        ),
    )


def index_has_content(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS(SELECT 1 FROM file_registry)
            OR EXISTS(SELECT 1 FROM code_chunks)
            OR EXISTS(SELECT 1 FROM notes_chunks)
        """
    ).fetchone()
    return bool(row[0]) if row is not None else False


def validate_query_configuration(conn: sqlite3.Connection, current: IndexConfiguration) -> None:
    stored = load_index_configuration(conn)
    if stored is None:
        if index_has_content(conn):
            raise RuntimeError("Index metadata is missing; run `kinekt reindex <workspace>`")
        return
    if stored.fingerprint != current.fingerprint:
        raise RuntimeError(
            "Index configuration changed; run `kinekt reindex <workspace>` before querying"
        )


def index_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ("file_registry", "code_chunks", "notes_chunks")
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
    }
