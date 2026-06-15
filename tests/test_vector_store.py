from __future__ import annotations

from pathlib import Path

from kinekt.ingest import ingest_workspace
from kinekt.query import query_knowledge_base
from kinekt.storage import connect, ensure_schema


def test_chromadb_backend_falls_back_to_sqlite_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nlocal context")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    monkeypatch.setenv("KINEKT_VECTOR_BACKEND", "chromadb")

    def _boom(_conn):
        raise ImportError("chromadb unavailable")

    monkeypatch.setattr("kinekt.vector_store._build_chromadb_store", _boom)
    results = query_knowledge_base(conn, "local context", limit=5)
    assert results
    assert results[0].source == "notes_chunks"
