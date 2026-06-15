from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import CURRENT_SCHEMA_VERSION, SCHEMA_SQL


def default_data_dir() -> Path:
    return Path.cwd() / ".kinekt"


def default_db_path() -> Path:
    return default_data_dir() / "kinekt.sqlite3"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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


def _apply_migration(conn: sqlite3.Connection, target_version: int) -> None:
    if target_version == 1:
        conn.executescript(SCHEMA_SQL)
        return
    raise ValueError(f"No migration path for schema version {target_version}")


def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")
