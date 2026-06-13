from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .chunking import embed_text, file_hash, split_markdown_file, split_python_file

CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp"}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
EXCLUDED_DIR_NAMES = {".git", ".kinekt", ".pytest_cache", "__pycache__", ".venv", "venv", ".mypy_cache"}


@dataclass(frozen=True)
class IngestStats:
    scanned: int
    updated: int
    skipped: int


def _upsert_registry(conn: sqlite3.Connection, rel_path: str, file_type: str, digest: str) -> None:
    conn.execute(
        """
        INSERT INTO file_registry(file_path, file_type, last_modified_hash, last_indexed_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(file_path)
        DO UPDATE SET
            file_type = excluded.file_type,
            last_modified_hash = excluded.last_modified_hash,
            last_indexed_at = CURRENT_TIMESTAMP
        """,
        (rel_path, file_type, digest),
    )


def _lookup_hash(conn: sqlite3.Connection, rel_path: str) -> str | None:
    row = conn.execute(
        "SELECT last_modified_hash FROM file_registry WHERE file_path = ?",
        (rel_path,),
    ).fetchone()
    return None if row is None else str(row[0])


def _replace_code_chunks(conn: sqlite3.Connection, rel_path: str, chunks: list) -> None:
    conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (rel_path,))
    conn.executemany(
        """
        INSERT INTO code_chunks(chunk_id, file_path, language, construct_type, content, embedding_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                ch.chunk_id,
                ch.file_path,
                ch.language,
                ch.construct_type,
                ch.content,
                json.dumps(embed_text(ch.content)),
            )
            for ch in chunks
        ],
    )


def _replace_note_chunks(conn: sqlite3.Connection, rel_path: str, chunks: list) -> None:
    conn.execute("DELETE FROM notes_chunks WHERE file_path = ?", (rel_path,))
    conn.executemany(
        """
        INSERT INTO notes_chunks(chunk_id, file_path, tags, heading_context, content, embedding_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                ch.chunk_id,
                ch.file_path,
                ch.tags,
                ch.heading_context,
                ch.content,
                json.dumps(embed_text(ch.content)),
            )
            for ch in chunks
        ],
    )


def ingest_workspace(conn: sqlite3.Connection, workspace: Path) -> IngestStats:
    workspace = workspace.resolve()

    scanned = 0
    updated = 0
    skipped = 0

    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue

        ext = path.suffix.lower()
        file_type: str | None = None
        if ext in CODE_EXTENSIONS:
            file_type = "code"
        elif ext in MARKDOWN_EXTENSIONS:
            file_type = "markdown"

        if file_type is None:
            continue

        scanned += 1
        rel_path = str(path.relative_to(workspace))
        digest = file_hash(path)
        existing = _lookup_hash(conn, rel_path)
        if existing == digest:
            skipped += 1
            continue

        if file_type == "code":
            chunks = split_python_file(path, rel_path) if ext == ".py" else []
            if not chunks:
                # Fallback: treat non-python code as markdown-like blocks.
                chunks = split_markdown_file(path, rel_path)
                _replace_note_chunks(conn, rel_path, chunks)
            else:
                _replace_code_chunks(conn, rel_path, chunks)
        else:
            chunks = split_markdown_file(path, rel_path)
            _replace_note_chunks(conn, rel_path, chunks)

        _upsert_registry(conn, rel_path, file_type, digest)
        updated += 1

    conn.commit()
    return IngestStats(scanned=scanned, updated=updated, skipped=skipped)
