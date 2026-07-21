from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .limits import MAX_QUERY_CHARS, clamp_query_limit, validate_text
from .query import query_knowledge_base

MAX_EVALUATION_CASES = 500
MAX_EVALUATION_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query: str
    relevant_paths: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    query: str
    retrieved_paths: tuple[str, ...]
    relevant_paths: tuple[str, ...]
    recall: float
    reciprocal_rank: float
    ndcg: float
    latency_ms: float


@dataclass(frozen=True)
class EvaluationReport:
    dataset_name: str
    case_count: int
    limit: int
    recall_at_k: float
    mean_reciprocal_rank: float
    ndcg_at_k: float
    mean_latency_ms: float
    database_bytes: int
    cases: tuple[CaseResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_cases(path: Path) -> tuple[str, list[EvaluationCase]]:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.stat().st_size > MAX_EVALUATION_FILE_BYTES:
        raise ValueError("Evaluation file exceeds the maximum size")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evaluation file must contain a JSON object")

    dataset_name = validate_text(
        str(payload.get("name", "evaluation")),
        field="evaluation name",
        maximum=200,
    )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Evaluation file must contain a non-empty cases list")
    if len(raw_cases) > MAX_EVALUATION_CASES:
        raise ValueError(f"Evaluation file exceeds {MAX_EVALUATION_CASES} cases")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Evaluation case {index} must be an object")
        case_id = validate_text(
            str(raw_case.get("id", f"case-{index}")),
            field="case id",
            maximum=200,
        )
        if case_id in seen_ids:
            raise ValueError(f"Duplicate evaluation case id: {case_id}")
        seen_ids.add(case_id)
        query = validate_text(
            str(raw_case.get("query", "")),
            field=f"query for {case_id}",
            maximum=MAX_QUERY_CHARS,
        )
        raw_paths = raw_case.get("relevant_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError(f"Evaluation case {case_id} requires relevant_paths")
        relevant_paths = tuple(dict.fromkeys(str(item).replace("\\", "/") for item in raw_paths if str(item)))
        if not relevant_paths:
            raise ValueError(f"Evaluation case {case_id} requires non-empty relevant_paths")
        cases.append(EvaluationCase(case_id=case_id, query=query, relevant_paths=relevant_paths))
    return dataset_name, cases


def _ndcg(relevance: list[int], relevant_count: int, limit: int) -> float:
    dcg = sum(value / math.log2(rank + 2) for rank, value in enumerate(relevance[:limit]))
    ideal_hits = min(relevant_count, limit)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
    return dcg / idcg


def _database_size(conn: sqlite3.Connection) -> int:
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        if str(row["name"]) != "main" or not row["file"]:
            continue
        path = Path(str(row["file"]))
        # WAL is the default write mode, so the main file alone can remain one
        # SQLite page until the connection checkpoints. Report the complete
        # on-disk footprint that a user actually pays for during evaluation.
        database_files = (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
        return sum(candidate.stat().st_size for candidate in database_files if candidate.is_file())
    return 0


def evaluate_retrieval(
    conn: sqlite3.Connection,
    dataset_name: str,
    cases: list[EvaluationCase],
    *,
    limit: int = 5,
) -> EvaluationReport:
    if not cases:
        raise ValueError("At least one evaluation case is required")
    safe_limit = clamp_query_limit(limit)
    case_results: list[CaseResult] = []
    for case in cases:
        started = time.perf_counter()
        results = query_knowledge_base(conn, case.query, limit=safe_limit)
        latency_ms = (time.perf_counter() - started) * 1000.0
        retrieved_paths = tuple(
            dict.fromkeys(result.file_path.replace("\\", "/") for result in results)
        )[:safe_limit]
        relevant = set(case.relevant_paths)
        relevance = [1 if path in relevant else 0 for path in retrieved_paths]
        matched = len(relevant & set(retrieved_paths))
        first_rank = next((rank for rank, value in enumerate(relevance, start=1) if value), None)
        case_results.append(
            CaseResult(
                case_id=case.case_id,
                query=case.query,
                retrieved_paths=retrieved_paths,
                relevant_paths=case.relevant_paths,
                recall=matched / len(relevant),
                reciprocal_rank=0.0 if first_rank is None else 1.0 / first_rank,
                ndcg=_ndcg(relevance, len(relevant), safe_limit),
                latency_ms=latency_ms,
            )
        )

    count = len(case_results)
    return EvaluationReport(
        dataset_name=dataset_name,
        case_count=count,
        limit=safe_limit,
        recall_at_k=sum(result.recall for result in case_results) / count,
        mean_reciprocal_rank=sum(result.reciprocal_rank for result in case_results) / count,
        ndcg_at_k=sum(result.ndcg for result in case_results) / count,
        mean_latency_ms=sum(result.latency_ms for result in case_results) / count,
        database_bytes=_database_size(conn),
        cases=tuple(case_results),
    )
