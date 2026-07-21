from __future__ import annotations

import argparse
import json
import tempfile
from contextlib import closing
from pathlib import Path

from kinekt.evaluation import evaluate_retrieval, load_evaluation_cases
from kinekt.ingest import ingest_workspace
from kinekt.storage import connect, ensure_schema
from kinekt.workspace import resolve_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation and enforce quality thresholds.")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--cases", default="evals/kinekt-retrieval.eval.json")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.80)
    parser.add_argument("--min-mrr", type=float, default=0.55)
    parser.add_argument("--min-ndcg", type=float, default=0.60)
    args = parser.parse_args()

    workspace = resolve_workspace(Path(args.workspace))
    dataset_name, cases = load_evaluation_cases(Path(args.cases))
    with tempfile.TemporaryDirectory(prefix="kinekt-eval-") as temp_dir:
        db_path = Path(temp_dir) / "kinekt.sqlite3"
        with closing(connect(db_path)) as conn:
            ensure_schema(conn)
            ingest_stats = ingest_workspace(conn, workspace)
            report = evaluate_retrieval(conn, dataset_name, cases, limit=args.limit)

    summary = {
        "case_count": report.case_count,
        "database_bytes": report.database_bytes,
        "dataset": report.dataset_name,
        "index_duration_ms": round(ingest_stats.duration_ms, 3),
        "indexed_files": ingest_stats.updated,
        "mean_latency_ms": round(report.mean_latency_ms, 3),
        "mrr": round(report.mean_reciprocal_rank, 6),
        "ndcg_at_k": round(report.ndcg_at_k, 6),
        "recall_at_k": round(report.recall_at_k, 6),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    failures: list[str] = []
    if report.recall_at_k < args.min_recall:
        failures.append(f"recall {report.recall_at_k:.4f} < {args.min_recall:.4f}")
    if report.mean_reciprocal_rank < args.min_mrr:
        failures.append(f"MRR {report.mean_reciprocal_rank:.4f} < {args.min_mrr:.4f}")
    if report.ndcg_at_k < args.min_ndcg:
        failures.append(f"nDCG {report.ndcg_at_k:.4f} < {args.min_ndcg:.4f}")
    if failures:
        print("Retrieval quality gate failed: " + "; ".join(failures))
        return 1
    print("Retrieval quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
