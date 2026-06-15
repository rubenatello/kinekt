from __future__ import annotations

from pathlib import Path

from kinekt.ingest import ingest_workspace
from kinekt.query import query_knowledge_base
from kinekt.storage import connect, ensure_schema


def test_ingest_and_query(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "app.py").write_text(
        """
def greet(name: str) -> str:
    return f\"hello {name}\"
""".strip()
    )
    (workspace / "notes.md").write_text("# Planning\nKinekt stores local context for developers.")

    db_path = tmp_path / "kinekt.sqlite3"
    conn = connect(db_path)
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)
    assert stats.scanned == 2
    assert stats.updated == 2

    results = query_knowledge_base(conn, "local context for developers", limit=3)
    assert results
    assert any("notes.md" in r.file_path for r in results)


def test_ingest_skips_unchanged_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Heading\nStable content")

    db_path = tmp_path / "kinekt.sqlite3"
    conn = connect(db_path)
    ensure_schema(conn)

    first = ingest_workspace(conn, workspace)
    second = ingest_workspace(conn, workspace)

    assert first.updated == 1
    assert second.skipped == 1


def test_ingest_excludes_cache_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".pytest_cache").mkdir()
    (workspace / ".pytest_cache" / "README.md").write_text("cache content should not be indexed")
    (workspace / "notes.md").write_text("# Heading\nreal content")

    db_path = tmp_path / "kinekt.sqlite3"
    conn = connect(db_path)
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)
    assert stats.scanned == 1
    assert stats.updated == 1


def test_query_limit_is_clamped(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for i in range(30):
        (workspace / f"n{i}.md").write_text(f"# Note {i}\nlocal context {i}")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = query_knowledge_base(conn, "local context", limit=500)
    assert len(results) <= 20


def test_query_skips_mismatched_embedding_dimensions(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO notes_chunks(chunk_id, file_path, tags, heading_context, content, embedding_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("bad-dim", "notes.md", "", "root", "bad embedding shape", "[0.1, 0.2, 0.3]"),
    )
    conn.commit()

    results = query_knowledge_base(conn, "anything", limit=5)
    assert results == []
