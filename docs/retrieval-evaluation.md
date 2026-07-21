# Retrieval Evaluation

Kinekt measures retrieval quality with versioned, repository-specific coding questions. The initial dataset
contains ten questions about Kinekt's implementation and identifies the implementation files expected in the
top five unique-file results.

## Reproduce The Evaluation

From an initialized development environment:

```bash
python scripts/check_retrieval_eval.py
```

The script creates a temporary SQLite index outside the workspace, ingests the repository, runs
`evals/kinekt-retrieval.eval.json`, prints aggregate metrics, and removes the temporary database.

To inspect every case and retrieved path through the CLI:

```bash
kinekt init .
kinekt ingest .
kinekt eval evals/kinekt-retrieval.eval.json --workspace . --limit 5
```

The evaluation payload uses the `.eval.json` suffix, which ingestion excludes by default to prevent the test
questions from leaking into their own retrieval results.

## Metrics

- **Recall@5**: fraction of labeled relevant files returned within the first five unique-file results.
- **MRR**: mean reciprocal rank of the first relevant file.
- **nDCG@5**: position-sensitive ranking quality when a question has multiple relevant files.
- **Mean latency**: in-process query time using deterministic local embeddings and SQLite.
- **Index duration and size**: operational cost for the evaluated workspace.

## Recorded Deterministic Baselines

| Iteration | Recall@5 | MRR | nDCG@5 | Mean query latency |
| --- | ---: | ---: | ---: | ---: |
| Initial vector + lexical boost | 0.55 | 0.252 | 0.351 | 45.2 ms |
| FTS5 hybrid + leakage prevention + broad-pool reranking + file diversity | 0.90 | 0.600 | 0.691 | 94.4 ms |

The recorded run used Python 3.11 in the non-root Docker test image with the repository copied into a Linux Docker
volume, avoiding host bind-mount timing effects. It indexed 87 files; initial ingest completed in approximately
471 ms and produced a 3,089,816-byte (approximately 2.95 MiB) SQLite database. Latency values are
environment-dependent; ranking metrics are deterministic for the local fallback backend.

## Pinned External Corpus

The external v1 corpus uses exact public commit SHAs so upstream changes cannot silently move the benchmark:

| Repository | Language | Cases | Recall@5 | MRR | nDCG@5 | Mean latency | Indexed files |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| psf/requests `69f8484704` | Python | 4 | 1.000 | 0.875 | 0.908 | 38.8 ms | 71 |
| go-chi/chi `8b258c7bb2` | Go | 4 | 0.875 | 0.875 | 0.847 | 45.4 ms | 88 |
| serde-rs/json `de8500740c` | Rust | 4 | 1.000 | 1.000 | 1.000 | 109.3 ms | 77 |
| **Weighted aggregate** | 3 languages | **12** | **0.958** | **0.917** | **0.918** | **64.5 ms** | **236** |

This Docker run completed initial ingestion in approximately 230 ms, 184 ms, and 458 ms respectively. The
resulting local databases were approximately 3.25 MB, 3.52 MB, and 15.29 MB. Repository source and license metadata
are recorded in `evals/external-repositories.eval.json`.

The same cases are grouped by coarse question intent to make the weaker slice visible:

| Question type | Cases | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| Boundary handling | 3 | 1.000 | 1.000 | 1.000 |
| Data model | 3 | 1.000 | 1.000 | 1.000 |
| Execution path | 3 | 0.833 | 0.833 | 0.796 |
| Supporting concern | 3 | 1.000 | 0.833 | 0.877 |

`execution-path` is the weakest slice and is a better target for future corpus growth than tuning against already
perfect slices.

Reproduce the networked gate with:

```bash
python scripts/check_external_retrieval_eval.py
```

The runner accepts only explicit HTTPS GitHub clone URLs, validates full 40-character revisions, checks out each
commit detached into temporary storage, and deletes that storage after the run. Its default aggregate floors are
Recall@5 >= 0.85, MRR >= 0.80, and nDCG@5 >= 0.80.

## CI Quality Gate

CI currently requires:

- Recall@5 >= 0.80
- MRR >= 0.55
- nDCG@5 >= 0.60

Thresholds intentionally leave a small platform-independent margin below the recorded run. Raising a threshold
requires a repeatable improvement rather than changing or removing a difficult case without justification.

## Known Gaps

- Docker/runtime questions still favor documentation over `Dockerfile` and `compose.yaml`.
- Schema questions often retrieve `storage.py` but miss `schema.py` within five results.
- The external corpus is still small and curated, covers only Python, Go, and Rust, and does not measure JavaScript,
  TypeScript, Java, SQL, or cross-file change tasks.
- Both datasets measure retrieval labels, not downstream coding-agent task success or time saved.
- The deterministic embedding backend is a reproducible baseline, not a semantic-quality ceiling.
