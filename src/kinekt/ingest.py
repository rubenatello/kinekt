from __future__ import annotations

import fnmatch
import os
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .chunking import file_hash, split_code_file, split_markdown_file
from .index_state import (
    current_index_configuration,
    index_has_content,
    load_index_configuration,
    save_index_configuration,
)
from .vector_store import VectorStore, get_vector_store
from .workspace import is_within_workspace, resolve_workspace

CODE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".ps1",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
CODE_FILENAMES = {"dockerfile", "makefile"}
EXCLUDED_FILE_PATTERNS = {"*.eval.json"}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
EXCLUDED_DIR_NAMES = {
    ".cache",
    ".firebase",
    ".git",
    ".gradle",
    ".kinekt",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".tox",
    ".turbo",
    ".venv",
    ".vite",
    "__pycache__",
    "bower_components",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "playwright-report",
    "target",
    "venv",
}
MAX_INDEXED_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class IngestStats:
    scanned: int
    updated: int
    skipped: int
    pruned: int = 0
    rebuilt: bool = False
    duration_ms: float = 0.0


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool


def _load_gitignore_rules(workspace: Path) -> list[IgnoreRule]:
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        return []

    rules: list[IgnoreRule] = []
    for raw_line in gitignore.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        if not line:
            continue
        directory_only = line.endswith("/")
        anchored = line.startswith("/")
        pattern = line.strip("/")
        if pattern.endswith("/**"):
            pattern = pattern[:-3].rstrip("/")
            directory_only = True
        if pattern:
            rules.append(
                IgnoreRule(
                    pattern=pattern.replace("\\", "/"),
                    negated=negated,
                    directory_only=directory_only,
                    anchored=anchored,
                )
            )
    return rules


def _rule_matches(rule: IgnoreRule, rel_path: str, is_dir: bool) -> bool:
    if rule.directory_only and not is_dir:
        path_parts = rel_path.split("/")
        if rule.anchored:
            return rel_path == rule.pattern or rel_path.startswith(f"{rule.pattern}/")
        return rule.pattern in path_parts

    if "/" in rule.pattern or rule.anchored:
        return fnmatch.fnmatch(rel_path, rule.pattern)

    return fnmatch.fnmatch(rel_path.rsplit("/", 1)[-1], rule.pattern)


def _is_gitignored(rel_path: str, is_dir: bool, rules: list[IgnoreRule]) -> bool:
    ignored = False
    for rule in rules:
        if _rule_matches(rule, rel_path, is_dir=is_dir):
            ignored = not rule.negated
    return ignored


def _iter_candidate_files(workspace: Path, rules: list[IgnoreRule]) -> Iterator[Path]:
    workspace = resolve_workspace(workspace)
    for root, dirnames, filenames in os.walk(workspace):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for dirname in dirnames:
            dir_path = root_path / dirname
            rel_dir = dir_path.relative_to(workspace).as_posix()
            if dir_path.is_symlink():
                continue
            if dirname.lower() in EXCLUDED_DIR_NAMES:
                continue
            if _is_gitignored(rel_dir, is_dir=True, rules=rules):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            path = root_path / filename
            rel_file = path.relative_to(workspace).as_posix()
            if any(fnmatch.fnmatch(filename.lower(), pattern) for pattern in EXCLUDED_FILE_PATTERNS):
                continue
            if _is_gitignored(rel_file, is_dir=False, rules=rules):
                continue
            yield path


def _upsert_registry(conn: sqlite3.Connection, rel_path: str, file_type: str, digest: str) -> None:
    conn.execute(
        """
        INSERT INTO file_registry(file_path, file_type, last_modified_hash, last_indexed_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(file_path)
        DO UPDATE SET
            file_type = excluded.file_type,
            last_modified_hash = excluded.last_modified_hash,
            last_indexed_at = CURRENT_TIMESTAMP
        """,
        (rel_path, file_type, digest),
    )


def _lookup_hash(conn: sqlite3.Connection, rel_path: str) -> str | None:
    row = conn.execute(
        "SELECT last_modified_hash FROM file_registry WHERE file_path = ?",
        (rel_path,),
    ).fetchone()
    return None if row is None else str(row[0])


def _registry_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT file_path FROM file_registry").fetchall()
    return {str(row["file_path"]) for row in rows}


def _prepare_index(conn: sqlite3.Connection, vector_store: VectorStore, force_rebuild: bool) -> bool:
    current = current_index_configuration(vector_store.backend_name)
    stored = load_index_configuration(conn)
    rebuild = force_rebuild or (stored is not None and stored.fingerprint != current.fingerprint)
    if stored is None and index_has_content(conn):
        rebuild = True

    if rebuild:
        vector_store.clear(conn)
        conn.execute("DELETE FROM file_registry")

    save_index_configuration(conn, current)
    return rebuild


def ingest_workspace(
    conn: sqlite3.Connection,
    workspace: Path,
    *,
    force_rebuild: bool = False,
) -> IngestStats:
    started = time.perf_counter()
    workspace = resolve_workspace(workspace)
    vector_store = get_vector_store(conn)
    rebuilt = _prepare_index(conn, vector_store, force_rebuild=force_rebuild)
    gitignore_rules = _load_gitignore_rules(workspace)

    scanned = 0
    updated = 0
    skipped = 0
    active_paths: set[str] = set()

    for path in _iter_candidate_files(workspace, gitignore_rules):
        ext = path.suffix.lower()
        file_type: str | None = None
        if ext in CODE_EXTENSIONS or path.name.lower() in CODE_FILENAMES:
            file_type = "code"
        elif ext in MARKDOWN_EXTENSIONS:
            file_type = "markdown"

        if file_type is None:
            continue

        scanned += 1
        if path.is_symlink():
            skipped += 1
            continue
        try:
            resolved_path = path.resolve(strict=True)
            if not is_within_workspace(workspace, resolved_path) or not resolved_path.is_file():
                skipped += 1
                continue
            file_size = resolved_path.stat().st_size
        except OSError:
            skipped += 1
            continue
        if file_size > MAX_INDEXED_FILE_BYTES:
            skipped += 1
            continue

        rel_path = path.relative_to(workspace).as_posix()
        try:
            digest = file_hash(resolved_path)
        except OSError:
            skipped += 1
            continue
        active_paths.add(rel_path)
        existing = _lookup_hash(conn, rel_path)
        if existing == digest:
            skipped += 1
            continue

        if file_type == "code":
            code_chunks = split_code_file(resolved_path, rel_path)
            vector_store.replace_code_chunks(conn, rel_path, code_chunks)
        else:
            note_chunks = split_markdown_file(resolved_path, rel_path)
            vector_store.replace_note_chunks(conn, rel_path, note_chunks)

        _upsert_registry(conn, rel_path, file_type, digest)
        updated += 1

    stale_paths = sorted(_registry_paths(conn) - active_paths)
    vector_store.delete_paths(conn, stale_paths)
    if stale_paths:
        conn.executemany("DELETE FROM file_registry WHERE file_path = ?", [(path,) for path in stale_paths])

    conn.commit()
    return IngestStats(
        scanned=scanned,
        updated=updated,
        skipped=skipped,
        pruned=len(stale_paths),
        rebuilt=rebuilt,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )
