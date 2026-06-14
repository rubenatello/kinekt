from __future__ import annotations

from pathlib import Path

from kinekt.schema import CURRENT_SCHEMA_VERSION
from kinekt.storage import connect, ensure_schema


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
