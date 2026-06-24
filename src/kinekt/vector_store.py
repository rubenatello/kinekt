from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from .chunking import cosine_similarity, embed_text


Hit = dict[str, str | float]
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class VectorStore:
    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int, query_text: str = "") -> list[Hit]:
        raise NotImplementedError


def _code_embedding_text(ch: Any) -> str:
    return f"path: {ch.file_path}\nlanguage: {ch.language}\nconstruct: {ch.construct_type}\n{ch.content}"


def _note_embedding_text(ch: Any) -> str:
    return f"path: {ch.file_path}\nheading: {ch.heading_context}\ntags: {ch.tags}\n{ch.content}"


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _lexical_boost(query_text: str, file_path: str, content: str) -> float:
    normalized_query = " ".join(query_text.lower().split())
    if not normalized_query:
        return 0.0

    normalized_path = file_path.replace("\\", "/").lower()
    basename = normalized_path.rsplit("/", 1)[-1]
    score = 0.0

    if normalized_query == basename:
        score += 4.0
    elif normalized_query in normalized_path:
        score += 2.0

    query_tokens = _tokens(query_text)
    if not query_tokens:
        return score

    path_tokens = _tokens(normalized_path)
    content_tokens = _tokens(content)
    score += 0.8 * len(query_tokens & path_tokens)
    score += 0.05 * len(query_tokens & content_tokens)
    return score


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
                    json.dumps(embed_text(_code_embedding_text(ch))),
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
                    json.dumps(embed_text(_note_embedding_text(ch))),
                )
                for ch in chunks
            ],
        )

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int, query_text: str = "") -> list[Hit]:
        combined = self._query_table(conn, "code_chunks", query_vec, limit, query_text) + self._query_table(
            conn, "notes_chunks", query_vec, limit, query_text
        )
        combined.sort(key=lambda x: float(x["score"]), reverse=True)
        return combined[:limit]

    def _query_table(
        self,
        conn: sqlite3.Connection,
        table: str,
        query_vec: list[float],
        limit: int,
        query_text: str,
    ) -> list[Hit]:
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
            score = cosine_similarity(query_vec, emb) + _lexical_boost(
                query_text=query_text,
                file_path=str(row["file_path"]),
                content=str(row["content"]),
            )
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
            embeddings=[embed_text(_code_embedding_text(ch)) for ch in chunks],
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
            embeddings=[embed_text(_note_embedding_text(ch)) for ch in chunks],
            metadatas=[
                {
                    "file_path": ch.file_path,
                    "tags": ch.tags,
                    "heading_context": ch.heading_context,
                }
                for ch in chunks
            ],
        )

    def query(self, conn: sqlite3.Connection, query_vec: list[float], limit: int, query_text: str = "") -> list[Hit]:
        del conn
        fetch_limit = max(limit, min(limit * 5, 50))
        code_hits = self._query_collection(self._code, query_vec, fetch_limit, "code_chunks", query_text)
        note_hits = self._query_collection(self._notes, query_vec, fetch_limit, "notes_chunks", query_text)
        combined = code_hits + note_hits
        combined.sort(key=lambda x: float(x["score"]), reverse=True)
        return combined[:limit]

    def _query_collection(
        self,
        collection: Any,
        query_vec: list[float],
        limit: int,
        source: str,
        query_text: str,
    ) -> list[Hit]:
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
            file_path = str(meta.get("file_path", ""))
            content_text = str(content)
            distance = float(distance_list[idx]) if idx < len(distance_list) else 0.0
            results.append(
                {
                    "chunk_id": str(chunk_id),
                    "file_path": file_path,
                    "score": -distance + _lexical_boost(query_text, file_path, content_text),
                    "content": content_text,
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
