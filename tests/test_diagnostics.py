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
    assert "Generation endpoint local-only: no" in report
