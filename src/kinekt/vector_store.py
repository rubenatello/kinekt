from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .chunking import cosine_similarity, embed_text


Hit = dict[str, str | float]


class VectorStore:
    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int) -> list[Hit]:
        raise NotImplementedError


class SQLiteVectorStore(VectorStore):
    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
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

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
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

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int) -> list[Hit]:
        combined = self._query_table(conn, "code_chunks", query_vec, limit) + self._query_table(
            conn, "notes_chunks", query_vec, limit
        )
        combined.sort(key=lambda x: float(x["score"]), reverse=True)
        return combined[:limit]

    def _query_table(self, conn: sqlite3.Connection, table: str, query_vec: list[float], limit: int) -> list[Hit]:
        rows = conn.execute(f"SELECT chunk_id, file_path, content, embedding_json FROM {table}").fetchall()
        scored: list[Hit] = []
        for row in rows:
            try:
                emb = json.loads(row["embedding_json"])
            except json.JSONDecodeError:
                continue
            if not isinstance(emb, list):
                continue
            if len(emb) != len(query_vec):
                continue
            score = cosine_similarity(query_vec, emb)
            scored.append(
                {
                    "chunk_id": row["chunk_id"],
                    "file_path": row["file_path"],
                    "score": float(score),
                    "content": row["content"],
                    "source": table,
                }
            )

        scored.sort(key=lambda x: float(x["score"]), reverse=True)
        return scored[:limit]


class ChromaVectorStore(VectorStore):
    def __init__(self, workspace: Path) -> None:
        import chromadb

        chroma_root = workspace / ".kinekt" / "chroma"
        chroma_root.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_root))
        self._code = self._client.get_or_create_collection("collection_code_chunks")
        self._notes = self._client.get_or_create_collection("collection_notes_chunks")

    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        del conn
        self._code.delete(where={"file_path": rel_path})
        if not chunks:
            return

        self._code.add(
            ids=[ch.chunk_id for ch in chunks],
            documents=[ch.content for ch in chunks],
            embeddings=[embed_text(ch.content) for ch in chunks],
            metadatas=[
                {
                    "file_path": ch.file_path,
                    "language": ch.language,
                    "construct_type": ch.construct_type,
                }
                for ch in chunks
            ],
        )

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        del conn
        self._notes.delete(where={"file_path": rel_path})
        if not chunks:
            return

        self._notes.add(
            ids=[ch.chunk_id for ch in chunks],
            documents=[ch.content for ch in chunks],
            embeddings=[embed_text(ch.content) for ch in chunks],
            metadatas=[
                {
                    "file_path": ch.file_path,
                    "tags": ch.tags,
                    "heading_context": ch.heading_context,
                }
                for ch in chunks
            ],
        )

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int) -> list[Hit]:
        del conn
        code_hits = self._query_collection(self._code, query_vec, limit, "code_chunks")
        note_hits = self._query_collection(self._notes, query_vec, limit, "notes_chunks")
        combined = code_hits + note_hits
        combined.sort(key=lambda x: float(x["score"]), reverse=True)
        return combined[:limit]

    def _query_collection(self, collection: Any, query_vec: list[float], limit: int, source: str) -> list[Hit]:
        payload = collection.query(query_embeddings=[query_vec], n_results=limit)
        ids = payload.get("ids", [[]])
        docs = payload.get("documents", [[]])
        metas = payload.get("metadatas", [[]])
        distances = payload.get("distances", [[]])

        id_list = ids[0] if isinstance(ids, list) and ids else []
        doc_list = docs[0] if isinstance(docs, list) and docs else []
        meta_list = metas[0] if isinstance(metas, list) and metas else []
        distance_list = distances[0] if isinstance(distances, list) and distances else []

        results: list[Hit] = []
        for idx, chunk_id in enumerate(id_list):
            meta = meta_list[idx] if idx < len(meta_list) and isinstance(meta_list[idx], dict) else {}
            content = doc_list[idx] if idx < len(doc_list) else ""
            distance = float(distance_list[idx]) if idx < len(distance_list) else 0.0
            results.append(
                {
                    "chunk_id": str(chunk_id),
                    "file_path": str(meta.get("file_path", "")),
                    "score": -distance,
                    "content": str(content),
                    "source": source,
                }
            )
        return results


def _workspace_from_conn(conn: sqlite3.Connection) -> Path:
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        name = row["name"] if "name" in row.keys() else row[1]
        if name != "main":
            continue
        file_path = row["file"] if "file" in row.keys() else row[2]
        if not file_path:
            break
        db_path = Path(str(file_path)).resolve()
        if db_path.parent.name == ".kinekt":
            return db_path.parent.parent
        return db_path.parent
    return Path.cwd()


def _build_chromadb_store(conn: sqlite3.Connection) -> VectorStore:
    return ChromaVectorStore(_workspace_from_conn(conn))


def get_vector_store(conn: sqlite3.Connection) -> VectorStore:
    backend = os.getenv("KINEKT_VECTOR_BACKEND", "sqlite_local").strip().lower()
    if backend == "chromadb":
        try:
            return _build_chromadb_store(conn)
        except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError):
            return SQLiteVectorStore()
    return SQLiteVectorStore()
