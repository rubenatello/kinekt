from __future__ import annotations

import json

from kinekt.generation import generate_agent_reply
from kinekt.query import QueryResult


def _sample_hits() -> list[QueryResult]:
    return [
        QueryResult(
            chunk_id="c1",
            file_path="notes.md",
            score=0.9,
            content="Kinekt stores local context.",
            source="notes_chunks",
        )
    ]


def test_generate_agent_reply_defaults_to_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("KINEKT_GENERATION_BACKEND", raising=False)
    result = generate_agent_reply(
        workspace="/workspace",
        session_id="s1",
        user_message="where is context?",
        hits=_sample_hits(),
        prior_user_count=1,
    )
    assert result.backend == "deterministic"
    assert "Prior turns in this session: 1" in result.text


def test_generate_agent_reply_uses_ollama_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_GENERATION_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_MODEL", "llama3.1:8b")

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"response": "Use kinekt ingest then query."}).encode("utf-8")

    import kinekt.generation as generation

    monkeypatch.setattr(generation, "urlopen", lambda *_args, **_kwargs: _FakeResponse())
    result = generate_agent_reply(
        workspace="/workspace",
        session_id="s1",
        user_message="what next?",
        hits=_sample_hits(),
        prior_user_count=0,
    )
    assert result.backend == "ollama"
    assert result.text == "Use kinekt ingest then query."


def test_generate_agent_reply_rejects_non_local_ollama_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_GENERATION_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_URL", "http://example.com/api/generate")
    result = generate_agent_reply(
        workspace="/workspace",
        session_id="s1",
        user_message="what next?",
        hits=[],
        prior_user_count=0,
    )
    assert result.backend == "deterministic"
