from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from kinekt.schema import CURRENT_SCHEMA_VERSION, INDEX_METADATA_SQL, SCHEMA_SQL
from kinekt.session_store import append_message
from kinekt.storage import connect, ensure_schema, validate_schema


def test_ensure_schema_sets_current_user_version_on_fresh_db(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    ensure_schema(conn)

    version_row = conn.execute("PRAGMA user_version").fetchone()
    assert version_row is not None
    assert int(version_row[0]) == CURRENT_SCHEMA_VERSION


def test_ensure_schema_upgrades_legacy_db_with_user_version_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    conn = connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY)")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()

    ensure_schema(conn)

    version_row = conn.execute("PRAGMA user_version").fetchone()
    assert version_row is not None
    assert int(version_row[0]) == CURRENT_SCHEMA_VERSION

    table_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='thread_messages'"
    ).fetchone()
    assert table_row is not None


@pytest.mark.parametrize("starting_version", [1, 2])
def test_ensure_schema_migrates_every_released_version(tmp_path: Path, starting_version: int) -> None:
    conn = connect(tmp_path / f"version-{starting_version}.sqlite3")
    conn.executescript(SCHEMA_SQL)
    if starting_version >= 2:
        conn.executescript(INDEX_METADATA_SQL)
    conn.execute(f"PRAGMA user_version = {starting_version}")
    conn.commit()

    ensure_schema(conn)

    code_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(code_chunks)")}
    fts_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
    ).fetchone()
    summary_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'session_summaries'"
    ).fetchone()
    assert {"symbol_name", "start_line", "end_line"} <= code_columns
    assert fts_row is not None
    assert summary_row is not None
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == CURRENT_SCHEMA_VERSION


def test_connect_enables_sqlite_reliability_pragmas(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")

    assert int(conn.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
    assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) == 5_000
    assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"


def test_concurrent_session_writers_complete_without_lock_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "kinekt.sqlite3"
    initial = connect(db_path)
    ensure_schema(initial)
    initial.close()

    def write_messages(worker: int) -> None:
        conn = connect(db_path, create=False)
        try:
            for sequence in range(5):
                append_message(conn, f"session-{worker}", "user", f"message-{sequence}")
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write_messages, range(4)))

    verification = connect(db_path, create=False, read_only=True)
    try:
        count = int(verification.execute("SELECT COUNT(*) FROM thread_messages").fetchone()[0])
    finally:
        verification.close()
    assert count == 20


def test_connect_read_only_requires_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "kinekt.sqlite3"

    with pytest.raises(FileNotFoundError):
        connect(db_path, create=False, read_only=True)

    assert not db_path.parent.exists()


def test_connect_read_only_rejects_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "kinekt.sqlite3"
    writable = connect(db_path)
    ensure_schema(writable)
    writable.close()

    read_only = connect(db_path, create=False, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            read_only.execute("INSERT INTO sessions(session_id) VALUES ('forbidden')")
    finally:
        read_only.close()


def test_validate_schema_rejects_outdated_database(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kinekt.sqlite3")
    conn.execute("PRAGMA user_version = 1")

    with pytest.raises(RuntimeError, match="does not match"):
        validate_schema(conn)
