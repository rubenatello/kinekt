from __future__ import annotations

from pathlib import Path


def read_utf8_text(path: Path) -> str:
    """Read a UTF-8 text file while stripping a leading BOM when present."""
    return path.read_text(encoding="utf-8-sig", errors="ignore")
