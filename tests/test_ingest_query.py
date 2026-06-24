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


def test_ingest_non_python_code_uses_code_chunks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.ts").write_text("export function greet(name: string) { return `hello ${name}`; }")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    assert stats.scanned == 1
    assert stats.updated == 1

    code_row = conn.execute(
        "SELECT file_path, language, construct_type FROM code_chunks WHERE file_path = ?",
        ("app.ts",),
    ).fetchone()
    note_row = conn.execute("SELECT file_path FROM notes_chunks WHERE file_path = ?", ("app.ts",)).fetchone()
    registry_row = conn.execute("SELECT file_type FROM file_registry WHERE file_path = ?", ("app.ts",)).fetchone()

    assert code_row is not None
    assert dict(code_row) == {"file_path": "app.ts", "language": "ts", "construct_type": "module"}
    assert note_row is None
    assert registry_row["file_type"] == "code"


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


def test_ingest_excludes_dependency_and_build_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for dirname in ("node_modules", "dist", "build", ".firebase"):
        nested = workspace / dirname
        nested.mkdir()
        (nested / "generated.ts").write_text("export const ignored = true")
    (workspace / "app.ts").write_text("export const real = true")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    assert stats.scanned == 1
    assert stats.updated == 1
    row = conn.execute("SELECT file_path FROM code_chunks").fetchone()
    assert row is not None
    assert row["file_path"] == "app.ts"


def test_ingest_respects_root_gitignore_patterns(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("ignored-docs/\n*.generated.ts\n")
    (workspace / "ignored-docs").mkdir()
    (workspace / "ignored-docs" / "notes.md").write_text("# Ignored\nshould not index")
    (workspace / "component.generated.ts").write_text("export const ignored = true")
    (workspace / "app.ts").write_text("export const real = true")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    rows = conn.execute("SELECT file_path FROM code_chunks").fetchall()
    assert stats.scanned == 1
    assert stats.updated == 1
    assert [row["file_path"] for row in rows] == ["app.ts"]


def test_ingest_skips_large_text_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "large.md").write_text("x" * 1_000_001)

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    assert stats.scanned == 1
    assert stats.updated == 0
    assert stats.skipped == 1


def test_ingest_strips_utf8_bom_from_indexed_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("\ufeff# Heading\nBOM content", encoding="utf-8")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    ingest_workspace(conn, workspace)

    row = conn.execute("SELECT content FROM notes_chunks WHERE file_path = ?", ("notes.md",)).fetchone()
    assert row is not None
    assert not row["content"].startswith("\ufeff")


def test_ingest_handles_repeated_markdown_sections(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Repeat\nsame content\n# Repeat\nsame content")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    rows = conn.execute("SELECT chunk_id, content FROM notes_chunks WHERE file_path = ?", ("notes.md",)).fetchall()
    assert stats.updated == 1
    assert len(rows) == 2
    assert len({row["chunk_id"] for row in rows}) == 2


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


def test_query_can_rank_file_path_matches(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "App.tsx").write_text("export function RootShell() { return null }")
    (workspace / "Other.tsx").write_text("export function SearchResult() { return null }")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = query_knowledge_base(conn, "App.tsx", limit=2)

    assert results
    assert results[0].file_path == "App.tsx"


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
