from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .embeddings import embed_text


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    file_path: str
    language: str
    construct_type: str
    content: str


@dataclass(frozen=True)
class NoteChunk:
    chunk_id: str
    file_path: str
    tags: str
    heading_context: str
    content: str


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


def split_python_file(path: Path, rel_path: str) -> list[CodeChunk]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    chunks: list[CodeChunk] = []

    try:
        tree = ast.parse(text)
        lines = text.splitlines()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                snippet = "\n".join(lines[start : end + 1]).strip()
                if snippet:
                    chunks.append(
                        CodeChunk(
                            chunk_id=_stable_chunk_id(rel_path, "function", node.name, str(start)),
                            file_path=rel_path,
                            language="python",
                            construct_type="function",
                            content=snippet,
                        )
                    )
            elif isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                snippet = "\n".join(lines[start : end + 1]).strip()
                if snippet:
                    chunks.append(
                        CodeChunk(
                            chunk_id=_stable_chunk_id(rel_path, "class", node.name, str(start)),
                            file_path=rel_path,
                            language="python",
                            construct_type="class",
                            content=snippet,
                        )
                    )
    except SyntaxError:
        pass

    if not chunks:
        lines = text.splitlines()
        block = 80
        for i in range(0, len(lines), block):
            snippet = "\n".join(lines[i : i + block]).strip()
            if snippet:
                chunks.append(
                    CodeChunk(
                        chunk_id=_stable_chunk_id(rel_path, "module", str(i)),
                        file_path=rel_path,
                        language=path.suffix.lstrip(".") or "text",
                        construct_type="module",
                        content=snippet,
                    )
                )

    return chunks


def split_markdown_file(path: Path, rel_path: str) -> list[NoteChunk]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    heading = "root"
    buf: list[str] = []
    chunks: list[NoteChunk] = []

    def flush() -> None:
        nonlocal buf
        content = "\n".join(buf).strip()
        if not content:
            buf = []
            return
        tags = sorted(set(re.findall(r"#[A-Za-z0-9_-]+", content)))
        chunks.append(
            NoteChunk(
                chunk_id=_stable_chunk_id(rel_path, heading, content[:120]),
                file_path=rel_path,
                tags=",".join(tags),
                heading_context=heading,
                content=content,
            )
        )
        buf = []

    for line in lines:
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip() or "root"
            continue
        buf.append(line)
        if len(buf) >= 40:
            flush()
    flush()
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Vector dimensions do not match")
    return sum(x * y for x, y in zip(a, b))
