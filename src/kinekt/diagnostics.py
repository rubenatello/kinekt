from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from .storage import connect, ensure_schema

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_DEFAULT_OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
_DEFAULT_OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
_DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"
_DEFAULT_OLLAMA_GENERATE_MODEL = "llama3.1:8b"


def _is_loopback_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname is None:
        return False
    return parsed.hostname in _LOCAL_HOSTS


def _probe_http_endpoint(url: str, timeout_seconds: float = 2.0) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _workspace_db_path(workspace: Path) -> Path:
    return workspace.resolve() / ".kinekt" / "kinekt.sqlite3"


def _append_ollama_diagnostics(
    lines: list[str],
    label: str,
    endpoint: str,
    model: str,
    fallback_backend: str,
) -> None:
    local_only = _is_loopback_endpoint(endpoint)
    lines.append(f"{label} endpoint: {endpoint}")
    lines.append(f"{label} model: {model}")
    lines.append(f"{label} endpoint local-only: {'yes' if local_only else 'no'}")
    if not local_only:
        lines.append(f"{label} endpoint reachable: skipped")
        lines.append(
            f"{label} next step: use a loopback Ollama endpoint such as "
            f"{_DEFAULT_OLLAMA_EMBED_URL if label == 'Embedding' else _DEFAULT_OLLAMA_GENERATE_URL}"
        )
        return

    reachable = _probe_http_endpoint(endpoint)
    lines.append(f"{label} endpoint reachable: {'yes' if reachable else 'no'}")
    if not reachable:
        lines.append(
            f"{label} next step: install/start Ollama locally, run `ollama pull {model}`, "
            f"then retry. Kinekt will fall back to {fallback_backend} until Ollama is reachable."
        )


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
        emb_url = os.getenv("KINEKT_OLLAMA_URL", _DEFAULT_OLLAMA_EMBED_URL).strip()
        emb_model = os.getenv("KINEKT_OLLAMA_MODEL", _DEFAULT_OLLAMA_EMBED_MODEL).strip() or _DEFAULT_OLLAMA_EMBED_MODEL
        _append_ollama_diagnostics(lines, "Embedding", emb_url, emb_model, "deterministic embeddings")

    generation_backend = os.getenv("KINEKT_GENERATION_BACKEND", "deterministic").strip().lower()
    generation_backend = "ollama" if generation_backend == "ollama" else "deterministic"
    lines.append(f"Generation backend: {generation_backend}")
    if generation_backend == "ollama":
        gen_url = os.getenv("KINEKT_OLLAMA_GENERATE_URL", _DEFAULT_OLLAMA_GENERATE_URL).strip()
        gen_model = (
            os.getenv("KINEKT_OLLAMA_GENERATE_MODEL", _DEFAULT_OLLAMA_GENERATE_MODEL).strip()
            or _DEFAULT_OLLAMA_GENERATE_MODEL
        )
        _append_ollama_diagnostics(lines, "Generation", gen_url, gen_model, "deterministic generation")

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
