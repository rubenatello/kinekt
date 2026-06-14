from __future__ import annotations

import argparse
from types import SimpleNamespace

from kinekt import cli


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
