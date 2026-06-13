from __future__ import annotations

import json

from kinekt import embeddings


def test_embed_text_defaults_to_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("KINEKT_EMBEDDING_BACKEND", raising=False)
    vec = embeddings.embed_text("local first developer context")
    assert len(vec) == embeddings.EMBED_DIM


def test_embed_text_uses_ollama_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_URL", "http://127.0.0.1:11434/api/embeddings")
    monkeypatch.setenv("KINEKT_OLLAMA_MODEL", "nomic-embed-text")

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode("utf-8")

    monkeypatch.setattr(embeddings, "urlopen", lambda *_args, **_kwargs: _FakeResponse())
    vec = embeddings.embed_text("hello")
    assert vec == [0.1, 0.2, 0.3]


def test_embed_text_rejects_non_local_ollama_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_URL", "http://example.com/api/embeddings")

    vec = embeddings.embed_text("hello")
    assert len(vec) == embeddings.EMBED_DIM
