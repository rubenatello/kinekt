from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from .storage import connect, ensure_schema

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_loopback_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname is None:
        return False
    return parsed.hostname in _LOCAL_HOSTS


def _workspace_db_path(workspace: Path) -> Path:
    return workspace.resolve() / ".kinekt" / "kinekt.sqlite3"


def doctor_report(workspace: Path) -> str:
    resolved_workspace = workspace.resolve()
    db_path = _workspace_db_path(resolved_workspace)

    conn = connect(db_path)
    ensure_schema(conn)

    lines: list[str] = []
    lines.append("Kinekt Doctor")
    lines.append(f"Workspace: {resolved_workspace}")
    lines.append(f"Database: {db_path}")

    embedding_backend = os.getenv("KINEKT_EMBEDDING_BACKEND", "deterministic").strip().lower()
    embedding_backend = "ollama" if embedding_backend == "ollama" else "deterministic"
    lines.append(f"Embedding backend: {embedding_backend}")
    if embedding_backend == "ollama":
        emb_url = os.getenv("KINEKT_OLLAMA_URL", "http://127.0.0.1:11434/api/embeddings").strip()
        lines.append(f"Embedding endpoint: {emb_url}")
        lines.append(f"Embedding endpoint local-only: {'yes' if _is_loopback_endpoint(emb_url) else 'no'}")

    generation_backend = os.getenv("KINEKT_GENERATION_BACKEND", "deterministic").strip().lower()
    generation_backend = "ollama" if generation_backend == "ollama" else "deterministic"
    lines.append(f"Generation backend: {generation_backend}")
    if generation_backend == "ollama":
        gen_url = os.getenv("KINEKT_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate").strip()
        lines.append(f"Generation endpoint: {gen_url}")
        lines.append(f"Generation endpoint local-only: {'yes' if _is_loopback_endpoint(gen_url) else 'no'}")

    vector_backend = os.getenv("KINEKT_VECTOR_BACKEND", "sqlite_local").strip().lower()
    if vector_backend not in {"sqlite_local", "chromadb"}:
        vector_backend = "sqlite_local"
    lines.append(f"Vector backend requested: {vector_backend}")
    if vector_backend == "chromadb":
        try:
            import chromadb  # noqa: F401

            lines.append("Vector backend availability: chromadb import ok")
        except Exception:
            lines.append("Vector backend availability: chromadb unavailable, sqlite_local fallback")
    else:
        lines.append("Vector backend availability: sqlite_local")

    return "\n".join(lines)
