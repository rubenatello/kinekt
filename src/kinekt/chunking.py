from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .text_files import read_utf8_text

MAX_CHUNK_CHARS = 6_000
CODE_BLOCK_LINES = 80
CODE_OVERLAP_LINES = 10
MARKDOWN_BLOCK_LINES = 40
MARKDOWN_OVERLAP_LINES = 5

_STRUCTURED_DECLARATIONS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "js": (
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([\w$]+)")),
        (
            "function",
            re.compile(
                r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*"
                r"(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>"
            ),
        ),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([\w$]+)")),
    ),
    "jsx": (
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([\w$]+)")),
        (
            "function",
            re.compile(
                r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*"
                r"(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>"
            ),
        ),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([\w$]+)")),
    ),
    "ts": (
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([\w$]+)")),
        (
            "function",
            re.compile(
                r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*"
                r"(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>"
            ),
        ),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([\w$]+)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([\w$]+)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([\w$]+)")),
    ),
    "tsx": (
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([\w$]+)")),
        (
            "function",
            re.compile(
                r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*"
                r"(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>"
            ),
        ),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([\w$]+)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([\w$]+)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([\w$]+)")),
    ),
    "go": (
        ("function", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")),
        ("type", re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b")),
    ),
    "java": (
        (
            "type",
            re.compile(
                r"^\s*(?:(?:public|protected|private|abstract|final|static)\s+)*"
                r"(?:class|interface|enum|record)\s+([A-Za-z_]\w*)"
            ),
        ),
        (
            "method",
            re.compile(
                r"^\s*(?!(?:return|throw|new|if|for|while|switch|catch)\b)"
                r"(?:(?:public|protected|private|static|final|synchronized|abstract)\s+)*"
                r"[\w<>, ?\[\].]+\s+([A-Za-z_]\w*)\s*\("
            ),
        ),
    ),
    "rs": (
        ("function", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)")),
        ("type", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)")),
        ("impl", re.compile(r"^\s*impl(?:<[^>]+>)?\s+(?:\w+\s+for\s+)?([A-Za-z_]\w*)")),
    ),
    "sql": (
        (
            "table",
            re.compile(
                r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"
                r"(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)",
                re.IGNORECASE,
            ),
        ),
        ("view", re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w.\"]+)", re.IGNORECASE)),
        ("routine", re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([\w.\"]+)", re.IGNORECASE)),
    ),
}


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    file_path: str
    language: str
    construct_type: str
    content: str
    symbol_name: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class NoteChunk:
    chunk_id: str
    file_path: str
    tags: str
    heading_context: str
    content: str
    start_line: int
    end_line: int


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(65536), b""):
            digest.update(part)
    return digest.hexdigest()


def _stable_chunk_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"\x00")
    return h.hexdigest()


def _bounded_line_windows(
    lines: list[str],
    *,
    first_line: int,
    max_lines: int,
    overlap_lines: int,
) -> list[tuple[int, int, str]]:
    units: list[tuple[int, str]] = []
    for offset, line in enumerate(lines):
        line_number = first_line + offset
        pieces = [line[index : index + MAX_CHUNK_CHARS] for index in range(0, len(line), MAX_CHUNK_CHARS)] or [""]
        units.extend((line_number, piece) for piece in pieces)

    windows: list[tuple[int, int, str]] = []
    index = 0
    while index < len(units):
        selected: list[tuple[int, str]] = []
        content_chars = 0
        cursor = index
        while cursor < len(units) and len(selected) < max_lines:
            line_number, content = units[cursor]
            added_chars = len(content) + (1 if selected else 0)
            if selected and content_chars + added_chars > MAX_CHUNK_CHARS:
                break
            selected.append((line_number, content))
            content_chars += added_chars
            cursor += 1
        snippet = "\n".join(content for _, content in selected).strip()
        if snippet:
            windows.append((selected[0][0], selected[-1][0], snippet))
        if cursor >= len(units):
            break
        retained_overlap = min(overlap_lines, max(0, len(selected) - 1))
        index = cursor - retained_overlap
    return windows


def _code_chunks_for_span(
    lines: list[str],
    *,
    rel_path: str,
    language: str,
    construct_type: str,
    symbol_name: str,
    first_line: int,
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for part, (start_line, end_line, snippet) in enumerate(
        _bounded_line_windows(
            lines,
            first_line=first_line,
            max_lines=CODE_BLOCK_LINES,
            overlap_lines=CODE_OVERLAP_LINES,
        )
    ):
        chunks.append(
            CodeChunk(
                chunk_id=_stable_chunk_id(
                    rel_path,
                    construct_type,
                    symbol_name,
                    str(start_line),
                    str(part),
                ),
                file_path=rel_path,
                language=language,
                construct_type=construct_type,
                content=snippet,
                symbol_name=symbol_name,
                start_line=start_line,
                end_line=end_line,
            )
        )
    return chunks


def _split_code_blocks(path: Path, rel_path: str, language: str) -> list[CodeChunk]:
    text = read_utf8_text(path)
    lines = text.splitlines()
    return _code_chunks_for_span(
        lines,
        rel_path=rel_path,
        language=language,
        construct_type="module",
        symbol_name="",
        first_line=1,
    )


def _split_structured_file(path: Path, rel_path: str, language: str) -> list[CodeChunk]:
    lines = read_utf8_text(path).splitlines()
    declarations: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        for construct_type, pattern in _STRUCTURED_DECLARATIONS[language]:
            match = pattern.match(line)
            if match:
                declarations.append((index, construct_type, match.group(1).strip('"')))
                break
    if not declarations:
        return _split_code_blocks(path, rel_path, language)

    chunks: list[CodeChunk] = []
    if declarations[0][0] > 0:
        chunks.extend(
            _code_chunks_for_span(
                lines[: declarations[0][0]],
                rel_path=rel_path,
                language=language,
                construct_type="module",
                symbol_name="",
                first_line=1,
            )
        )
    for position, (start, construct_type, symbol_name) in enumerate(declarations):
        end = declarations[position + 1][0] if position + 1 < len(declarations) else len(lines)
        chunks.extend(
            _code_chunks_for_span(
                lines[start:end],
                rel_path=rel_path,
                language=language,
                construct_type=construct_type,
                symbol_name=symbol_name,
                first_line=start + 1,
            )
        )
    return chunks


def split_code_file(path: Path, rel_path: str) -> list[CodeChunk]:
    if path.suffix.lower() == ".py":
        return split_python_file(path, rel_path)
    language = path.suffix.lstrip(".").lower() or "text"
    if language in _STRUCTURED_DECLARATIONS:
        return _split_structured_file(path, rel_path, language)
    return _split_code_blocks(path, rel_path, language)


def split_python_file(path: Path, rel_path: str) -> list[CodeChunk]:
    text = read_utf8_text(path)
    chunks: list[CodeChunk] = []

    try:
        tree = ast.parse(text)
        lines = text.splitlines()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                chunks.extend(
                    _code_chunks_for_span(
                        lines[start : end + 1],
                        rel_path=rel_path,
                        language="python",
                        construct_type="function",
                        symbol_name=node.name,
                        first_line=start + 1,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                chunks.extend(
                    _code_chunks_for_span(
                        lines[start : end + 1],
                        rel_path=rel_path,
                        language="python",
                        construct_type="class",
                        symbol_name=node.name,
                        first_line=start + 1,
                    )
                )
    except SyntaxError:
        pass

    return chunks or _split_code_blocks(path, rel_path, path.suffix.lstrip(".").lower() or "text")


def split_markdown_file(path: Path, rel_path: str) -> list[NoteChunk]:
    text = read_utf8_text(path)
    lines = text.splitlines()

    heading = "root"
    buf: list[str] = []
    chunks: list[NoteChunk] = []
    chunk_index = 0
    buffer_start_line = 1

    def flush() -> None:
        nonlocal buf, chunk_index, buffer_start_line
        for start_line, end_line, content in _bounded_line_windows(
            buf,
            first_line=buffer_start_line,
            max_lines=MARKDOWN_BLOCK_LINES,
            overlap_lines=MARKDOWN_OVERLAP_LINES,
        ):
            tags = sorted(set(re.findall(r"#[A-Za-z0-9_-]+", content)))
            chunks.append(
                NoteChunk(
                    chunk_id=_stable_chunk_id(rel_path, heading, str(chunk_index), content[:120]),
                    file_path=rel_path,
                    tags=",".join(tags),
                    heading_context=heading,
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            chunk_index += 1
        buf = []

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip() or "root"
            buffer_start_line = line_number + 1
            continue
        if not buf:
            buffer_start_line = line_number
        buf.append(line)
    flush()
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Vector dimensions do not match")
    return sum(x * y for x, y in zip(a, b, strict=True))
