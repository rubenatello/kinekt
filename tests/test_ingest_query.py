from __future__ import annotations

from pathlib import Path

import pytest

from kinekt.ingest import ingest_workspace
from kinekt.limits import MAX_QUERY_CHARS
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


def test_ingest_prunes_deleted_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note = workspace / "old.md"
    note.write_text("# Old\nuniquestalecontext")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)
    note.unlink()

    stats = ingest_workspace(conn, workspace)

    assert stats.pruned == 1
    assert query_knowledge_base(conn, "uniquestalecontext", limit=5) == []
    assert conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0] == 0


def test_ingest_skips_symlinked_file_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret\nuniquesymlinksecret")
    link = workspace / "leak.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this environment: {exc}")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    assert stats.updated == 0
    assert stats.skipped == 1
    assert query_knowledge_base(conn, "uniquesymlinksecret", limit=5) == []


def test_force_reindex_rebuilds_unchanged_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nrebuild content")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    stats = ingest_workspace(conn, workspace, force_rebuild=True)

    assert stats.rebuilt is True
    assert stats.updated == 1


def test_ingest_rebuilds_when_index_configuration_changes(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nconfiguration-aware content")

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)
    monkeypatch.setattr("kinekt.index_state.CHUNKER_VERSION", "changed-for-test")

    stats = ingest_workspace(conn, workspace)

    assert stats.rebuilt is True
    assert stats.updated == 1


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
    assert dict(code_row) == {"file_path": "app.ts", "language": "ts", "construct_type": "function"}
    assert note_row is None
    assert registry_row["file_type"] == "code"


def test_ingest_indexes_configuration_and_docker_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM python:3.11-slim")
    (workspace / "compose.yaml").write_text("services:\n  app:\n    image: kinekt")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)
    paths = {str(row["file_path"]) for row in conn.execute("SELECT file_path FROM code_chunks")}
    query_paths = [hit.file_path for hit in query_knowledge_base(conn, "How is the Docker image built?", limit=2)]

    assert stats.updated == 2
    assert paths == {"Dockerfile", "compose.yaml"}
    assert "Dockerfile" in query_paths


def test_ingest_excludes_evaluation_case_payloads(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "retrieval.eval.json").write_text('{"query": "self leaking query"}')
    (workspace / "app.py").write_text("def real_code():\n    return True")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    stats = ingest_workspace(conn, workspace)

    assert stats.scanned == 1
    assert conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0] == 1


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


def test_query_rejects_empty_and_oversized_text(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    with pytest.raises(ValueError, match="cannot be empty"):
        query_knowledge_base(conn, "   ")
    with pytest.raises(ValueError, match="maximum length"):
        query_knowledge_base(conn, "x" * (MAX_QUERY_CHARS + 1))


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


def test_query_returns_hybrid_score_explanation_and_line_provenance(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "storage.py").write_text(
        "# database helpers\n\ndef connect_database():\n    return 'sqlite'\n"
    )

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    result = query_knowledge_base(conn, "connect database sqlite", limit=1)[0]

    assert result.file_path == "storage.py"
    assert result.symbol_name == "connect_database"
    assert result.start_line == 3
    assert result.end_line == 4
    assert result.vector_score > 0
    assert result.lexical_score > 0
    assert "vector" in result.ranking_reason
    assert "lexical" in result.ranking_reason


def test_query_diversifies_results_by_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "many.py").write_text(
        "def first_context():\n    return 'context'\n\n"
        "def second_context():\n    return 'context'\n"
    )
    (workspace / "other.py").write_text("def other_context():\n    return 'context'\n")

    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)

    results = query_knowledge_base(conn, "context", limit=5)

    assert [result.file_path for result in results] == ["many.py", "other.py"]


def test_query_rejects_legacy_index_without_configuration_metadata(tmp_path: Path) -> None:
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

    with pytest.raises(RuntimeError, match="Index metadata is missing"):
        query_knowledge_base(conn, "anything", limit=5)
