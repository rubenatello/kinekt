from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from kinekt import cli


class _FakeConnection:
    def close(self) -> None:
        pass


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
    assert "attach" in result.stdout
    assert "agent-setup" in result.stdout


def test_build_parser_exposes_workspace_onboarding_commands() -> None:
    parser = cli.build_parser()

    attach_args = parser.parse_args(["attach", "--yes", "--ingest"])
    setup_args = parser.parse_args(["agent-setup", "codex", "--docker"])
    mcp_args = parser.parse_args(["mcp-serve", "--attached"])

    assert attach_args.func is cli._cmd_attach
    assert attach_args.yes is True
    assert attach_args.ingest is True
    assert setup_args.func is cli._cmd_agent_setup
    assert setup_args.agent == "codex"
    assert setup_args.docker is True
    assert mcp_args.func is cli._cmd_mcp_serve
    assert mcp_args.attached is True


def test_cli_attach_ingest_and_status_from_nested_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "src"
    nested.mkdir(parents=True)
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (workspace / "notes.md").write_text("# Demo\nworkspace discovery")

    attach_result = _run_cli(["attach", "--yes", "--ingest", "--json"], nested)
    status_result = _run_cli(["workspace-status", "--json"], nested)

    assert attach_result.returncode == 0, attach_result.stderr
    attached = json.loads(attach_result.stdout)
    assert attached["root"] == str(workspace.resolve())
    assert attached["attached"] is True
    assert attached["database_exists"] is True
    assert attached["ingest"]["scanned"] >= 2
    assert status_result.returncode == 0, status_result.stderr
    status = json.loads(status_result.stdout)
    assert status["attached"] is True
    assert status["database_exists"] is True


def test_cli_attach_requires_explicit_confirmation_when_noninteractive(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "go.mod").write_text("module example.test/demo\n")

    result = _run_cli(["attach"], workspace)

    assert result.returncode == 1
    assert "interactive terminal or --yes" in result.stderr
    assert not (workspace / ".kinekt").exists()


def test_cli_auto_ingest_requires_attached_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")

    result = _run_cli(["ingest"], workspace)

    assert result.returncode == 1
    assert "Run `kinekt attach` first" in result.stderr
    assert not (workspace / ".kinekt").exists()


def test_cli_agent_setup_generates_docker_codex_config(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text("{}")
    attach_result = _run_cli(["attach", "--yes"], workspace)

    result = _run_cli(["agent-setup", "codex", "--docker", "--json"], workspace)

    assert attach_result.returncode == 0, attach_result.stderr
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["agent"] == "codex"
    assert payload["transport"] == "docker"
    assert payload["command"] == "docker"
    assert "[mcp_servers.kinekt]" in payload["config"]


def test_cli_agent_setup_requires_attached_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Cargo.toml").write_text("[package]\nname='demo'\n")

    result = _run_cli(["agent-setup", "codex"], workspace)

    assert result.returncode == 1
    assert "Workspace is not attached" in result.stderr


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
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace, **_kwargs: _FakeConnection())

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
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace, **_kwargs: _FakeConnection())

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
    monkeypatch.setattr(cli, "_connect_workspace", lambda _workspace: _FakeConnection())

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
            def raise_invalid_argument(_args):
                raise ValueError("bad input")

            return argparse.Namespace(command="query", func=raise_invalid_argument)

    monkeypatch.setattr(cli, "build_parser", lambda: _Parser())
    rc = cli.main()
    assert rc == 1
    err = capsys.readouterr().err
    payload = json.loads(err.splitlines()[-1])
    assert payload["code"] == "ERR_INVALID_ARGUMENT"
    assert payload["message"] == "bad input"
