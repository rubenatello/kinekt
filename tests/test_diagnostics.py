from __future__ import annotations

from pathlib import Path

from kinekt.diagnostics import doctor_report


def test_doctor_report_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KINEKT_EMBEDDING_BACKEND", raising=False)
    monkeypatch.delenv("KINEKT_GENERATION_BACKEND", raising=False)
    monkeypatch.delenv("KINEKT_VECTOR_BACKEND", raising=False)

    report = doctor_report(tmp_path)
    assert "Embedding backend: deterministic" in report
    assert "Generation backend: deterministic" in report
    assert "Vector backend requested: sqlite_local" in report


def test_doctor_report_flags_non_local_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_URL", "http://example.com/api/embeddings")
    monkeypatch.setenv("KINEKT_GENERATION_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_URL", "http://example.com/api/generate")

    report = doctor_report(tmp_path)
    assert "Embedding endpoint local-only: no" in report
    assert "Embedding endpoint reachable: skipped" in report
    assert "Embedding next step: use a loopback Ollama endpoint" in report
    assert "Generation endpoint local-only: no" in report
    assert "Generation endpoint reachable: skipped" in report
    assert "Generation next step: use a loopback Ollama endpoint" in report


def test_doctor_report_flags_reachable_ollama_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_URL", "http://127.0.0.1:11434/api/embeddings")
    monkeypatch.setenv("KINEKT_OLLAMA_MODEL", "nomic-embed-text")
    monkeypatch.setenv("KINEKT_GENERATION_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_URL", "http://localhost:11434/api/generate")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_MODEL", "llama3.1:8b")
    monkeypatch.setattr("kinekt.diagnostics._probe_http_endpoint", lambda _url: True)

    report = doctor_report(tmp_path)
    assert "Embedding endpoint local-only: yes" in report
    assert "Embedding endpoint reachable: yes" in report
    assert "Embedding model: nomic-embed-text" in report
    assert "Generation endpoint local-only: yes" in report
    assert "Generation endpoint reachable: yes" in report
    assert "Generation model: llama3.1:8b" in report


def test_doctor_report_guides_unreachable_ollama_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KINEKT_EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_MODEL", "nomic-embed-text")
    monkeypatch.setenv("KINEKT_GENERATION_BACKEND", "ollama")
    monkeypatch.setenv("KINEKT_OLLAMA_GENERATE_MODEL", "llama3.1:8b")
    monkeypatch.setattr("kinekt.diagnostics._probe_http_endpoint", lambda _url: False)

    report = doctor_report(tmp_path)
    assert "Embedding endpoint reachable: no" in report
    assert "Embedding next step: install/start Ollama locally, run `ollama pull nomic-embed-text`" in report
    assert "Kinekt will fall back to deterministic embeddings until Ollama is reachable." in report
    assert "Generation endpoint reachable: no" in report
    assert "Generation next step: install/start Ollama locally, run `ollama pull llama3.1:8b`" in report
    assert "Kinekt will fall back to deterministic generation until Ollama is reachable." in report
