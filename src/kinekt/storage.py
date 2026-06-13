from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import SCHEMA_SQL


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
    conn.executescript(SCHEMA_SQL)
    conn.commit()
