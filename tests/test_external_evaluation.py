from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_external_retrieval_eval import (
    _evaluation_cases,
    _grouped_metrics,
    _load_manifest,
)


def _repository_manifest(**overrides: object) -> dict[str, object]:
    repository: dict[str, object] = {
        "id": "example",
        "url": "https://github.com/example/project.git",
        "revision": "a" * 40,
        "cases": [
            {
                "id": "entrypoint",
                "question_type": "execution-path",
                "query": "Where is the entrypoint?",
                "relevant_paths": ["main.py"],
            }
        ],
    }
    repository.update(overrides)
    return {"name": "test", "repositories": [repository]}


def test_external_manifest_requires_pinned_https_github_repository(tmp_path: Path) -> None:
    manifest = tmp_path / "external.json"
    manifest.write_text(json.dumps(_repository_manifest()))

    name, repositories = _load_manifest(manifest)

    assert name == "test"
    assert repositories[0]["revision"] == "a" * 40

    manifest.write_text(json.dumps(_repository_manifest(revision="main")))
    with pytest.raises(ValueError, match="full commit SHA"):
        _load_manifest(manifest)

    manifest.write_text(json.dumps(_repository_manifest(url="https://example.com/project.git")))
    with pytest.raises(ValueError, match="HTTPS GitHub"):
        _load_manifest(manifest)

    duplicate = _repository_manifest()
    repositories = duplicate["repositories"]
    assert isinstance(repositories, list)
    duplicate["repositories"] = [repositories[0], repositories[0]]
    manifest.write_text(json.dumps(duplicate))
    with pytest.raises(ValueError, match="Duplicate repository id"):
        _load_manifest(manifest)


def test_external_cases_require_question_types_and_group_metrics() -> None:
    cases, question_types = _evaluation_cases(
        "example",
        [
            {
                "id": "entrypoint",
                "question_type": "execution-path",
                "query": "Where is the entrypoint?",
                "relevant_paths": ["main.py"],
            }
        ],
    )

    assert cases[0].case_id == "example:entrypoint"
    assert question_types == {"example:entrypoint": "execution-path"}

    records = [
        {
            "language": "python",
            "question_type": "execution-path",
            "recall_at_k": 1.0,
            "mrr": 0.5,
            "ndcg_at_k": 0.75,
            "mean_latency_ms": 10.0,
        },
        {
            "language": "python",
            "question_type": "data-model",
            "recall_at_k": 0.5,
            "mrr": 1.0,
            "ndcg_at_k": 0.5,
            "mean_latency_ms": 20.0,
        },
    ]
    assert _grouped_metrics(records, "language")["python"] == {
        "case_count": 2,
        "mean_latency_ms": 15.0,
        "mrr": 0.75,
        "ndcg_at_k": 0.625,
        "recall_at_k": 0.75,
    }

    with pytest.raises(ValueError, match="question_type"):
        _evaluation_cases(
            "example",
            [{"id": "entrypoint", "query": "Where?", "relevant_paths": ["main.py"]}],
        )
