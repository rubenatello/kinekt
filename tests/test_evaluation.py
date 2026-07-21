from __future__ import annotations

import json
from pathlib import Path

import pytest

from kinekt.evaluation import evaluate_retrieval, load_evaluation_cases
from kinekt.ingest import ingest_workspace
from kinekt.storage import connect, ensure_schema


def test_evaluation_reports_retrieval_metrics(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "storage.py").write_text("def connect_database():\n    return 'sqlite'\n")
    (workspace / "unrelated.py").write_text("def render_widget():\n    return 'ui'\n")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            {
                "name": "test-dataset",
                "cases": [
                    {
                        "id": "storage",
                        "query": "connect sqlite database",
                        "relevant_paths": ["storage.py"],
                    }
                ],
            }
        )
    )

    conn = connect(workspace / ".kinekt" / "kinekt.sqlite3")
    ensure_schema(conn)
    ingest_workspace(conn, workspace)
    dataset_name, cases = load_evaluation_cases(cases_path)

    report = evaluate_retrieval(conn, dataset_name, cases, limit=2)

    assert report.dataset_name == "test-dataset"
    assert report.case_count == 1
    assert report.recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0
    assert report.ndcg_at_k == 1.0
    assert report.database_bytes > 0


def test_evaluation_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            {
                "name": "duplicate-test",
                "cases": [
                    {"id": "same", "query": "one", "relevant_paths": ["one.py"]},
                    {"id": "same", "query": "two", "relevant_paths": ["two.py"]},
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="Duplicate"):
        load_evaluation_cases(cases_path)
