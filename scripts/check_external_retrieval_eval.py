from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from kinekt.evaluation import EvaluationCase, evaluate_retrieval
from kinekt.ingest import ingest_workspace
from kinekt.storage import connect, ensure_schema

_GITHUB_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git")
_REVISION = re.compile(r"[0-9a-f]{40}")
_REPOSITORY_ID = re.compile(r"[A-Za-z0-9_-]+")
_CASE_ID = re.compile(r"[A-Za-z0-9_-]+")
_QUESTION_TYPE = re.compile(r"[a-z][a-z0-9-]*")
_MAX_REPOSITORIES = 10
_MAX_CASES_PER_REPOSITORY = 100
_MAX_MANIFEST_BYTES = 2_000_000


def _load_manifest(path: Path) -> tuple[str, list[dict[str, Any]]]:
    resolved = path.resolve(strict=True)
    if resolved.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("External evaluation manifest exceeds the maximum size")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("repositories"), list):
        raise ValueError("External evaluation manifest requires a repositories list")
    repositories = payload["repositories"]
    if not repositories or len(repositories) > _MAX_REPOSITORIES:
        raise ValueError(f"External evaluation requires 1..{_MAX_REPOSITORIES} repositories")
    seen_repository_ids: set[str] = set()
    for repository in repositories:
        if not isinstance(repository, dict):
            raise ValueError("Each repository entry must be an object")
        repository_id = str(repository.get("id", ""))
        url = str(repository.get("url", ""))
        revision = str(repository.get("revision", ""))
        if _REPOSITORY_ID.fullmatch(repository_id) is None:
            raise ValueError(f"Invalid repository id: {repository_id}")
        if repository_id in seen_repository_ids:
            raise ValueError(f"Duplicate repository id: {repository_id}")
        seen_repository_ids.add(repository_id)
        if _GITHUB_URL.fullmatch(url) is None:
            raise ValueError(f"Only explicit HTTPS GitHub clone URLs are accepted: {url}")
        if _REVISION.fullmatch(revision) is None:
            raise ValueError(f"Repository {repository_id} must pin a full commit SHA")
        if not isinstance(repository.get("cases"), list) or not repository["cases"]:
            raise ValueError(f"Repository {repository_id} requires evaluation cases")
        if len(repository["cases"]) > _MAX_CASES_PER_REPOSITORY:
            raise ValueError(
                f"Repository {repository_id} exceeds {_MAX_CASES_PER_REPOSITORY} evaluation cases"
            )
    return str(payload.get("name", "external-evaluation")), repositories


def _clone_pinned_repository(url: str, revision: str, destination: Path) -> None:
    commands = (
        ["git", "init", "--quiet", str(destination)],
        ["git", "-C", str(destination), "remote", "add", "origin", url],
        ["git", "-C", str(destination), "fetch", "--quiet", "--depth", "1", "origin", revision],
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", "FETCH_HEAD"],
    )
    for command in commands:
        subprocess.run(command, check=True, timeout=120)


def _evaluation_cases(
    repository_id: str,
    raw_cases: list[dict[str, Any]],
) -> tuple[list[EvaluationCase], dict[str, str]]:
    cases: list[EvaluationCase] = []
    question_types: dict[str, str] = {}
    for raw_case in raw_cases:
        raw_case_id = str(raw_case.get("id", ""))
        if _CASE_ID.fullmatch(raw_case_id) is None:
            raise ValueError(f"Invalid external case id in {repository_id}: {raw_case_id}")
        case_id = f"{repository_id}:{raw_case_id}"
        if case_id in question_types:
            raise ValueError(f"Duplicate external case id: {case_id}")
        question_type = str(raw_case.get("question_type", ""))
        if _QUESTION_TYPE.fullmatch(question_type) is None:
            raise ValueError(f"Invalid question_type for {case_id}: {question_type}")
        query = str(raw_case.get("query", "")).strip()
        if not query:
            raise ValueError(f"External case {case_id} requires a query")
        paths = raw_case.get("relevant_paths")
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"External case in {repository_id} requires relevant_paths")
        cases.append(
            EvaluationCase(
                case_id=case_id,
                query=query,
                relevant_paths=tuple(str(path).replace("\\", "/") for path in paths),
            )
        )
        question_types[case_id] = question_type
    return cases, question_types


def _metric_summary(records: list[dict[str, Any]]) -> dict[str, float | int]:
    count = len(records)
    if count == 0:
        raise ValueError("Cannot summarize an empty evaluation group")
    return {
        "case_count": count,
        "mean_latency_ms": round(sum(float(record["mean_latency_ms"]) for record in records) / count, 6),
        "mrr": round(sum(float(record["mrr"]) for record in records) / count, 6),
        "ndcg_at_k": round(sum(float(record["ndcg_at_k"]) for record in records) / count, 6),
        "recall_at_k": round(sum(float(record["recall_at_k"]) for record in records) / count, 6),
    }


def _grouped_metrics(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, float | int]]:
    values = sorted({str(record[field]) for record in records})
    return {
        value: _metric_summary([record for record in records if str(record[field]) == value])
        for value in values
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Kinekt on pinned public repositories.")
    parser.add_argument("--manifest", default="evals/external-repositories.eval.json")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.85)
    parser.add_argument("--min-mrr", type=float, default=0.80)
    parser.add_argument("--min-ndcg", type=float, default=0.80)
    args = parser.parse_args()

    dataset_name, repositories = _load_manifest(Path(args.manifest))
    results: list[dict[str, Any]] = []
    case_records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="kinekt-external-eval-") as temp_dir:
        root = Path(temp_dir)
        for repository in repositories:
            repository_id = str(repository["id"])
            workspace = root / repository_id
            _clone_pinned_repository(str(repository["url"]), str(repository["revision"]), workspace)
            cases, question_types = _evaluation_cases(repository_id, repository["cases"])
            with closing(connect(root / f"{repository_id}.sqlite3")) as conn:
                ensure_schema(conn)
                ingest_stats = ingest_workspace(conn, workspace)
                report = evaluate_retrieval(conn, f"{dataset_name}:{repository_id}", cases, limit=args.limit)
            language = str(repository.get("language", "unknown"))
            case_records.extend(
                {
                    "language": language,
                    "mean_latency_ms": case.latency_ms,
                    "mrr": case.reciprocal_rank,
                    "ndcg_at_k": case.ndcg,
                    "question_type": question_types[case.case_id],
                    "recall_at_k": case.recall,
                }
                for case in report.cases
            )
            results.append(
                {
                    "case_count": report.case_count,
                    "database_bytes": report.database_bytes,
                    "index_duration_ms": round(ingest_stats.duration_ms, 3),
                    "indexed_files": ingest_stats.updated,
                    "language": language,
                    "mean_latency_ms": round(report.mean_latency_ms, 3),
                    "mrr": round(report.mean_reciprocal_rank, 6),
                    "ndcg_at_k": round(report.ndcg_at_k, 6),
                    "recall_at_k": round(report.recall_at_k, 6),
                    "repository": repository_id,
                    "revision": repository["revision"],
                }
            )

    aggregate = _metric_summary(case_records)
    output = {
        "aggregate": aggregate,
        "by_language": _grouped_metrics(case_records, "language"),
        "by_question_type": _grouped_metrics(case_records, "question_type"),
        "case_count": len(case_records),
        "dataset": dataset_name,
        "repositories": results,
    }
    print(json.dumps(output, indent=2, sort_keys=True))

    failures: list[str] = []
    for metric, minimum in (
        ("recall_at_k", args.min_recall),
        ("mrr", args.min_mrr),
        ("ndcg_at_k", args.min_ndcg),
    ):
        aggregate_value = float(aggregate[metric])
        if aggregate_value < minimum:
            failures.append(f"{metric} {aggregate_value:.4f} < {minimum:.4f}")
    if failures:
        print("External retrieval quality gate failed: " + "; ".join(failures))
        return 1
    print("External retrieval quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
