from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import (
    CURRENT_SCHEMA_VERSION,
    HYBRID_SEARCH_SQL,
    INDEX_METADATA_SQL,
    SCHEMA_SQL,
    SESSION_SUMMARY_SQL,
)


def default_data_dir() -> Path:
    return Path.cwd() / ".kinekt"


def default_db_path() -> Path:
    return default_data_dir() / "kinekt.sqlite3"


def connect(
    db_path: Path | None = None,
    *,
    create: bool = True,
    read_only: bool = False,
) -> sqlite3.Connection:
    if db_path is None:
        db_path = default_db_path()
    db_path = db_path.resolve()
    if read_only:
        if not db_path.is_file():
            raise FileNotFoundError(f"Kinekt database does not exist: {db_path}")
        conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    else:
        if create:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        elif not db_path.is_file():
            raise FileNotFoundError(f"Kinekt database does not exist: {db_path}")
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    current_version = _get_user_version(conn)
    if current_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"Database schema version {current_version} is newer than supported {CURRENT_SCHEMA_VERSION}"
        )

    for target_version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        _apply_migration(conn, target_version)
        _set_user_version(conn, target_version)

    conn.commit()


def validate_schema(conn: sqlite3.Connection) -> None:
    current_version = _get_user_version(conn)
    if current_version != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} does not match supported version "
            f"{CURRENT_SCHEMA_VERSION}; run `kinekt init <workspace>`"
        )


def _apply_migration(conn: sqlite3.Connection, target_version: int) -> None:
    if target_version == 1:
        conn.executescript(SCHEMA_SQL)
        return
    if target_version == 2:
        conn.executescript(INDEX_METADATA_SQL)
        return
    if target_version == 3:
        _ensure_column(conn, "code_chunks", "symbol_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "code_chunks", "start_line", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "code_chunks", "end_line", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "notes_chunks", "start_line", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "notes_chunks", "end_line", "INTEGER NOT NULL DEFAULT 1")
        conn.executescript(HYBRID_SEARCH_SQL)
        return
    if target_version == 4:
        conn.executescript(SESSION_SUMMARY_SQL)
        return
    raise ValueError(f"No migration path for schema version {target_version}")


def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
