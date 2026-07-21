from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from .chunking import cosine_similarity
from .embeddings import embed_text

Hit = dict[str, str | float | int]
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _candidate_limit(result_limit: int) -> int:
    """Return a broad, bounded pool for hybrid reranking."""
    return max(200, min(result_limit * 20, 500))


class VectorStore:
    backend_name = "unknown"

    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        raise NotImplementedError

    def query(
        self,
        conn: sqlite3.Connection,
        query_vec: list[float],
        limit: int,
        query_text: str = "",
    ) -> list[Hit]:
        raise NotImplementedError

    def delete_paths(self, conn: sqlite3.Connection, rel_paths: list[str]) -> None:
        raise NotImplementedError

    def clear(self, conn: sqlite3.Connection) -> None:
        raise NotImplementedError


def _code_embedding_text(chunk: Any) -> str:
    return (
        f"path: {chunk.file_path}\nlanguage: {chunk.language}\n"
        f"construct: {chunk.construct_type}\nsymbol: {chunk.symbol_name}\n{chunk.content}"
    )


def _note_embedding_text(chunk: Any) -> str:
    return (
        f"path: {chunk.file_path}\nheading: {chunk.heading_context}\n"
        f"tags: {chunk.tags}\n{chunk.content}"
    )


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _path_score(query_text: str, file_path: str) -> float:
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
    path_tokens = _tokens(normalized_path)
    exact_matches = query_tokens & path_tokens
    score += 2.0 * len(exact_matches)

    # Extensionless compound filenames such as Dockerfile should still match
    # natural-language queries containing "docker". Keep this deterministic
    # and conservative by requiring a four-character prefix in either direction.
    for query_token in query_tokens - exact_matches:
        if len(query_token) < 4:
            continue
        if any(
            len(path_token) >= 4
            and (path_token.startswith(query_token) or query_token.startswith(path_token))
            for path_token in path_tokens - exact_matches
        ):
            score += 2.0
    return score


def _identifier_tokens(text: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ")
    return _tokens(expanded)


def _symbol_score(query_text: str, symbol_name: str) -> float:
    if not symbol_name:
        return 0.0
    query_tokens = _tokens(query_text)
    symbol_tokens = _identifier_tokens(symbol_name)
    if not symbol_tokens:
        return 0.0
    return len(query_tokens & symbol_tokens) / len(symbol_tokens)


def _source_score(file_path: str, source: str) -> float:
    normalized = file_path.replace("\\", "/").lower()
    first_part = normalized.split("/", 1)[0]
    if first_part in {"tests", "test", "docs", "evals", "examples"}:
        return 0.0
    if first_part in {"src", "app", "lib", "packages"}:
        return 1.0
    if "/" not in normalized and source == "code_chunks":
        return 0.8
    return 0.5 if source == "code_chunks" else 0.2


def _replace_fts_chunks(
    conn: sqlite3.Connection,
    rel_path: str,
    source: str,
    chunks: list[Any],
) -> None:
    conn.execute("DELETE FROM chunks_fts WHERE file_path = ? AND source = ?", (rel_path, source))
    rows: list[tuple[str, str, str, str, str, int, int]] = []
    for chunk in chunks:
        symbol_name = str(getattr(chunk, "symbol_name", getattr(chunk, "heading_context", "")))
        rows.append(
            (
                str(chunk.chunk_id),
                str(chunk.file_path),
                str(chunk.content),
                source,
                symbol_name,
                int(chunk.start_line),
                int(chunk.end_line),
            )
        )
    conn.executemany(
        """
        INSERT INTO chunks_fts(
            chunk_id, file_path, content, source, symbol_name, start_line, end_line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _query_fts(conn: sqlite3.Connection, query_text: str, limit: int) -> list[Hit]:
    tokens = sorted(_tokens(query_text))
    if not tokens:
        return []
    expression = " OR ".join(f'"{token}"' for token in tokens)
    rows = conn.execute(
        """
        SELECT chunk_id, file_path, content, source, symbol_name, start_line, end_line,
               bm25(chunks_fts) AS bm25_score
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY bm25_score ASC, file_path ASC, chunk_id ASC
        LIMIT ?
        """,
        (expression, limit),
    ).fetchall()
    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "file_path": str(row["file_path"]),
            "content": str(row["content"]),
            "source": str(row["source"]),
            "symbol_name": str(row["symbol_name"]),
            "start_line": int(row["start_line"]),
            "end_line": int(row["end_line"]),
            "lexical_score": 1.0 / rank,
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _combine_hybrid_hits(
    vector_hits: list[Hit],
    lexical_hits: list[Hit],
    query_text: str,
    limit: int,
) -> list[Hit]:
    combined: dict[str, Hit] = {}
    for hit in vector_hits:
        item = dict(hit)
        item.setdefault("lexical_score", 0.0)
        combined[str(item["chunk_id"])] = item

    for hit in lexical_hits:
        chunk_id = str(hit["chunk_id"])
        if chunk_id not in combined:
            item = dict(hit)
            item["vector_score"] = 0.0
            combined[chunk_id] = item
        else:
            combined[chunk_id]["lexical_score"] = float(hit["lexical_score"])

    for item in combined.values():
        vector_score = float(item.get("vector_score", 0.0))
        lexical_score = float(item.get("lexical_score", 0.0))
        path_score = _path_score(query_text, str(item["file_path"]))
        symbol_score = _symbol_score(query_text, str(item.get("symbol_name", "")))
        source_score = _source_score(str(item["file_path"]), str(item["source"]))
        normalized_vector = max(0.0, min(1.0, (vector_score + 1.0) / 2.0))
        normalized_path = max(0.0, min(1.0, path_score / 4.0))
        score = (
            (0.35 * normalized_vector)
            + (0.30 * lexical_score)
            + (0.15 * normalized_path)
            + (0.10 * symbol_score)
            + (0.10 * source_score)
        )
        reasons: list[str] = []
        if vector_score:
            reasons.append("vector")
        if lexical_score:
            reasons.append("lexical")
        if path_score:
            reasons.append("path")
        if symbol_score:
            reasons.append("symbol")
        if source_score:
            reasons.append("source")
        item["vector_score"] = vector_score
        item["lexical_score"] = lexical_score
        item["path_score"] = path_score
        item["symbol_score"] = symbol_score
        item["source_score"] = source_score
        item["score"] = score
        item["ranking_reason"] = "+".join(reasons) or "fallback"

    results = list(combined.values())
    results.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["file_path"]),
            str(item["chunk_id"]),
        )
    )
    diversified: list[Hit] = []
    seen_paths: set[str] = set()
    for item in results:
        file_path = str(item["file_path"])
        if file_path in seen_paths:
            continue
        seen_paths.add(file_path)
        diversified.append(item)
        if len(diversified) >= limit:
            break
    return diversified


class SQLiteVectorStore(VectorStore):
    backend_name = "sqlite_local"

    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (rel_path,))
        conn.executemany(
            """
            INSERT INTO code_chunks(
                chunk_id, file_path, language, construct_type, content, embedding_json,
                symbol_name, start_line, end_line
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.file_path,
                    chunk.language,
                    chunk.construct_type,
                    chunk.content,
                    json.dumps(embed_text(_code_embedding_text(chunk))),
                    chunk.symbol_name,
                    chunk.start_line,
                    chunk.end_line,
                )
                for chunk in chunks
            ],
        )
        _replace_fts_chunks(conn, rel_path, "code_chunks", chunks)

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        conn.execute("DELETE FROM notes_chunks WHERE file_path = ?", (rel_path,))
        conn.executemany(
            """
            INSERT INTO notes_chunks(
                chunk_id, file_path, tags, heading_context, content, embedding_json,
                start_line, end_line
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.file_path,
                    chunk.tags,
                    chunk.heading_context,
                    chunk.content,
                    json.dumps(embed_text(_note_embedding_text(chunk))),
                    chunk.start_line,
                    chunk.end_line,
                )
                for chunk in chunks
            ],
        )
        _replace_fts_chunks(conn, rel_path, "notes_chunks", chunks)

    def query(
        self,
        conn: sqlite3.Connection,
        query_vec: list[float],
        limit: int,
        query_text: str = "",
    ) -> list[Hit]:
        candidate_limit = _candidate_limit(limit)
        vector_hits = self._query_table(conn, "code_chunks", query_vec, candidate_limit)
        vector_hits += self._query_table(conn, "notes_chunks", query_vec, candidate_limit)
        vector_hits.sort(key=lambda item: float(item["vector_score"]), reverse=True)
        lexical_hits = _query_fts(conn, query_text, candidate_limit)
        return _combine_hybrid_hits(vector_hits, lexical_hits, query_text, limit)

    def delete_paths(self, conn: sqlite3.Connection, rel_paths: list[str]) -> None:
        if not rel_paths:
            return
        parameters = [(path,) for path in rel_paths]
        conn.executemany("DELETE FROM code_chunks WHERE file_path = ?", parameters)
        conn.executemany("DELETE FROM notes_chunks WHERE file_path = ?", parameters)
        conn.executemany("DELETE FROM chunks_fts WHERE file_path = ?", parameters)

    def clear(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM code_chunks")
        conn.execute("DELETE FROM notes_chunks")
        conn.execute("DELETE FROM chunks_fts")

    def _query_table(
        self,
        conn: sqlite3.Connection,
        table: str,
        query_vec: list[float],
        limit: int,
    ) -> list[Hit]:
        if table == "code_chunks":
            metadata_sql = "symbol_name, start_line, end_line"
        else:
            metadata_sql = "heading_context AS symbol_name, start_line, end_line"
        rows = conn.execute(
            f"SELECT chunk_id, file_path, content, embedding_json, {metadata_sql} FROM {table}"
        ).fetchall()
        scored: list[Hit] = []
        for row in rows:
            try:
                embedding = json.loads(row["embedding_json"])
            except json.JSONDecodeError:
                continue
            if not isinstance(embedding, list) or len(embedding) != len(query_vec):
                continue
            scored.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "file_path": str(row["file_path"]),
                    "vector_score": float(cosine_similarity(query_vec, embedding)),
                    "content": str(row["content"]),
                    "source": table,
                    "symbol_name": str(row["symbol_name"]),
                    "start_line": int(row["start_line"]),
                    "end_line": int(row["end_line"]),
                }
            )
        scored.sort(key=lambda item: float(item["vector_score"]), reverse=True)
        return scored[:limit]


class ChromaVectorStore(VectorStore):
    backend_name = "chromadb"

    def __init__(self, workspace: Path) -> None:
        import chromadb

        chroma_root = workspace / ".kinekt" / "chroma"
        chroma_root.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_root))
        self._code = self._client.get_or_create_collection("collection_code_chunks")
        self._notes = self._client.get_or_create_collection("collection_notes_chunks")

    def replace_code_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        self._code.delete(where={"file_path": rel_path})
        if chunks:
            self._code.add(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                embeddings=[embed_text(_code_embedding_text(chunk)) for chunk in chunks],
                metadatas=[
                    {
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "construct_type": chunk.construct_type,
                        "symbol_name": chunk.symbol_name,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                    }
                    for chunk in chunks
                ],
            )
        _replace_fts_chunks(conn, rel_path, "code_chunks", chunks)

    def replace_note_chunks(self, conn: sqlite3.Connection, rel_path: str, chunks: list[Any]) -> None:
        self._notes.delete(where={"file_path": rel_path})
        if chunks:
            self._notes.add(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                embeddings=[embed_text(_note_embedding_text(chunk)) for chunk in chunks],
                metadatas=[
                    {
                        "file_path": chunk.file_path,
                        "tags": chunk.tags,
                        "heading_context": chunk.heading_context,
                        "symbol_name": chunk.heading_context,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                    }
                    for chunk in chunks
                ],
            )
        _replace_fts_chunks(conn, rel_path, "notes_chunks", chunks)

    def query(
        self,
        conn: sqlite3.Connection,
        query_vec: list[float],
        limit: int,
        query_text: str = "",
    ) -> list[Hit]:
        candidate_limit = _candidate_limit(limit)
        vector_hits = self._query_collection(self._code, query_vec, candidate_limit, "code_chunks")
        vector_hits += self._query_collection(self._notes, query_vec, candidate_limit, "notes_chunks")
        lexical_hits = _query_fts(conn, query_text, candidate_limit)
        return _combine_hybrid_hits(vector_hits, lexical_hits, query_text, limit)

    def delete_paths(self, conn: sqlite3.Connection, rel_paths: list[str]) -> None:
        for rel_path in rel_paths:
            self._code.delete(where={"file_path": rel_path})
            self._notes.delete(where={"file_path": rel_path})
        if rel_paths:
            conn.executemany("DELETE FROM chunks_fts WHERE file_path = ?", [(path,) for path in rel_paths])

    def clear(self, conn: sqlite3.Connection) -> None:
        for collection in (self._code, self._notes):
            payload = collection.get(include=[])
            ids = payload.get("ids", [])
            if ids:
                collection.delete(ids=ids)
        conn.execute("DELETE FROM chunks_fts")

    def _query_collection(
        self,
        collection: Any,
        query_vec: list[float],
        limit: int,
        source: str,
    ) -> list[Hit]:
        collection_size = int(collection.count())
        if collection_size <= 0:
            return []
        payload = collection.query(query_embeddings=[query_vec], n_results=min(limit, collection_size))
        ids = payload.get("ids", [[]])
        docs = payload.get("documents", [[]])
        metas = payload.get("metadatas", [[]])
        distances = payload.get("distances", [[]])
        id_list = ids[0] if isinstance(ids, list) and ids else []
        doc_list = docs[0] if isinstance(docs, list) and docs else []
        meta_list = metas[0] if isinstance(metas, list) and metas else []
        distance_list = distances[0] if isinstance(distances, list) and distances else []

        results: list[Hit] = []
        for index, chunk_id in enumerate(id_list):
            meta = meta_list[index] if index < len(meta_list) and isinstance(meta_list[index], dict) else {}
            content = str(doc_list[index]) if index < len(doc_list) else ""
            distance = float(distance_list[index]) if index < len(distance_list) else 1.0
            results.append(
                {
                    "chunk_id": str(chunk_id),
                    "file_path": str(meta.get("file_path", "")),
                    "vector_score": 1.0 - distance,
                    "content": content,
                    "source": source,
                    "symbol_name": str(meta.get("symbol_name", meta.get("heading_context", ""))),
                    "start_line": int(meta.get("start_line", 1)),
                    "end_line": int(meta.get("end_line", 1)),
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
    if backend == "sqlite_local":
        return SQLiteVectorStore()
    if backend == "chromadb":
        try:
            return _build_chromadb_store(conn)
        except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(
                "ChromaDB was requested but could not be initialized; install `kinekt[vector]` "
                "or use KINEKT_VECTOR_BACKEND=sqlite_local"
            ) from exc
    raise ValueError(f"Unsupported vector backend: {backend}")
