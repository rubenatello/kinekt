from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("chromadb")

from kinekt.ingest import ingest_workspace
from kinekt.query import query_knowledge_base
from kinekt.storage import connect, ensure_schema


def test_chromadb_ingest_query_and_prune(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note = workspace / "architecture.md"
    note.write_text("# Storage\nChroma stores the optional local vector index.")
    monkeypatch.setenv("KINEKT_VECTOR_BACKEND", "chromadb")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = query_knowledge_base(conn, "optional local vector index", limit=5)
    assert results
    assert results[0].file_path == "architecture.md"

    note.unlink()
    stats = ingest_workspace(conn, workspace)
    assert stats.pruned == 1
    assert query_knowledge_base(conn, "optional local vector index", limit=5) == []
