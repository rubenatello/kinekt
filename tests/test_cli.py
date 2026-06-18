from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from kinekt import cli


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = Path(__file__).resolve().parents[1] / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_path) if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    return subprocess.run(
        [sys.executable, "-m", "kinekt.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_help_smoke(tmp_path: Path) -> None:
    result = _run_cli(["--help"], tmp_path)
    assert result.returncode == 0
    assert "Kinekt local-first context engine" in result.stdout
    assert "mcp-serve" in result.stdout


def test_cli_doctor_smoke(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = _run_cli(["doctor", str(workspace)], tmp_path)

    assert result.returncode == 0
    assert "Kinekt Doctor" in result.stdout
    assert "Embedding backend: deterministic" in result.stdout


def test_cli_init_ingest_query_smoke(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\nKinekt keeps local developer context.")

    init_result = _run_cli(["init", str(workspace)], tmp_path)
    ingest_result = _run_cli(["ingest", str(workspace)], tmp_path)
    query_result = _run_cli(["query", "developer context", "--workspace", str(workspace)], tmp_path)

    assert init_result.returncode == 0
    assert "Initialized Kinekt database" in init_result.stdout
    assert ingest_result.returncode == 0
    assert "Scanned: 1 | Updated: 1" in ingest_result.stdout
    assert query_result.returncode == 0
    assert "notes.md" in query_result.stdout


def test_cmd_query_clamps_limit(monkeypatch) -> None:
    seen: dict[str, int] = {}
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace: object())

    def fake_query(_conn, _query, limit):
        seen["limit"] = limit
        return []

    monkeypatch.setattr(cli, "query_knowledge_base", fake_query)
    args = argparse.Namespace(workspace=".", query="context", limit=999)

    rc = cli._cmd_query(args)
    assert rc == 0
    assert seen["limit"] == 20


def test_cmd_read_file_clamps_max_chars(monkeypatch) -> None:
    seen: dict[str, int] = {}

    def fake_read(_workspace, _file_path, max_chars):
        seen["max_chars"] = max_chars
        return "ok"

    monkeypatch.setattr(cli, "read_workspace_file", fake_read)
    args = argparse.Namespace(workspace=".", file_path="a.txt", max_chars=999_999)

    rc = cli._cmd_read_file(args)
    assert rc == 0
    assert seen["max_chars"] == 50_000


def test_cmd_session_history_clamps_limit(monkeypatch) -> None:
    seen: dict[str, int] = {}
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace: object())

    def fake_list_messages(_conn, session_id, limit):
        seen["session_id"] = session_id
        seen["limit"] = limit
        return []

    monkeypatch.setattr(cli, "list_messages", fake_list_messages)
    args = argparse.Namespace(workspace=".", session_id="s1", limit=999)

    rc = cli._cmd_session_history(args)
    assert rc == 0
    assert seen["session_id"] == "s1"
    assert seen["limit"] == 100


def test_cmd_agent_turn_clamps_limits(monkeypatch) -> None:
    seen: dict[str, int] = {}
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace: object())

    def fake_agent_turn(**kwargs):
        seen["query_limit"] = kwargs["query_limit"]
        seen["history_window"] = kwargs["history_window"]
        return SimpleNamespace(reply="ok", session_id="sid")

    monkeypatch.setattr(cli, "run_agent_turn", fake_agent_turn)
    args = argparse.Namespace(
        workspace=".",
        message="hello",
        session_id=None,
        query_limit=999,
        history_window=999,
    )

    rc = cli._cmd_agent_turn(args)
    assert rc == 0
    assert seen["query_limit"] == 10
    assert seen["history_window"] == 20


def test_cmd_doctor_prints_report(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "doctor_report", lambda _workspace: "doctor ok")
    args = argparse.Namespace(workspace=".")
    rc = cli._cmd_doctor(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "doctor ok" in out


def test_main_normalizes_exceptions(monkeypatch, capsys) -> None:
    class _Parser:
        def parse_args(self):
            return argparse.Namespace(command="query", func=lambda _args: (_ for _ in ()).throw(ValueError("bad input")))

    monkeypatch.setattr(cli, "build_parser", lambda: _Parser())
    rc = cli.main()
    assert rc == 1
    err = capsys.readouterr().err
    payload = json.loads(err.splitlines()[-1])
    assert payload["code"] == "ERR_INVALID_ARGUMENT"
    assert payload["message"] == "bad input"
