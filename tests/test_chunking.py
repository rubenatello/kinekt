from __future__ import annotations

from pathlib import Path

import pytest

from kinekt.chunking import MAX_CHUNK_CHARS, split_code_file, split_markdown_file


@pytest.mark.parametrize(
    ("filename", "content", "expected_symbols"),
    [
        (
            "app.ts",
            "export interface Config {}\n"
            "export function loadConfig() {}\n"
            "export const saveConfig = async (value: Config) => value;",
            {"Config", "loadConfig", "saveConfig"},
        ),
        ("main.go", "type Server struct {}\nfunc (s *Server) Start() {}", {"Server", "Start"}),
        (
            "App.java",
            "public class App {\n  public void run() {}\n  String name() { return \"app\"; }\n}",
            {"App", "run", "name"},
        ),
        ("lib.rs", "pub struct Store {}\npub fn open_store() {}", {"Store", "open_store"}),
        ("schema.sql", "CREATE TABLE accounts (id int);\nCREATE VIEW active AS SELECT 1;", {"accounts", "active"}),
    ],
)
def test_structured_languages_preserve_symbol_metadata(
    tmp_path: Path,
    filename: str,
    content: str,
    expected_symbols: set[str],
) -> None:
    path = tmp_path / filename
    path.write_text(content)

    chunks = split_code_file(path, filename)

    assert expected_symbols <= {chunk.symbol_name for chunk in chunks}
    assert all(1 <= chunk.start_line <= chunk.end_line for chunk in chunks)


def test_code_chunking_bounds_minified_lines_without_dropping_tail(tmp_path: Path) -> None:
    marker = "TAIL_MARKER"
    path = tmp_path / "bundle.js"
    path.write_text("const payload = '" + ("x" * (MAX_CHUNK_CHARS * 2)) + marker + "';")

    chunks = split_code_file(path, path.name)

    assert len(chunks) >= 3
    assert all(len(chunk.content) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert any(marker in chunk.content for chunk in chunks)


def test_markdown_chunking_applies_character_bound_and_overlap(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    lines = [f"line {index} " + ("detail " * 30) for index in range(90)]
    path.write_text("# Long section\n" + "\n".join(lines))

    chunks = split_markdown_file(path, path.name)

    assert len(chunks) >= 3
    assert all(len(chunk.content) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert chunks[1].start_line <= chunks[0].end_line
