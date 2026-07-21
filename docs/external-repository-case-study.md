# External Repository Case Study

## Question

Can Kinekt retrieve implementation context from unfamiliar, real repositories without tuning its ranking logic to
those projects or sending their source to a hosted service?

The evaluation targets retrieval rather than answer generation. That isolates the context engine: each case asks a
natural coding question and identifies the file or files a useful context layer should return in its first five
unique-file results.

## Reproducible Corpus

The manifest pins exact commits and records upstream licenses:

| Repository | Language | Revision | License | Cases |
| --- | --- | --- | --- | ---: |
| `psf/requests` | Python | `69f84847045bef7a849cc994a26fe7ba8a169e95` | Apache-2.0 | 4 |
| `go-chi/chi` | Go | `8b258c7bb28f97a5f2a856ff7ef962578fec9215` | MIT | 4 |
| `serde-rs/json` | Rust | `de8500740cdcabffb9734f503e4889def823cf10` | MIT OR Apache-2.0 | 4 |

The runner accepts only explicit HTTPS GitHub URLs and full commit SHAs. Each repository is checked out detached,
indexed into temporary local storage, evaluated, and deleted. The evaluation payload itself never enters the
repository index.

## Result

The deterministic Python 3.11 Docker run on 2026-07-21 produced:

| Repository | Recall@5 | MRR | nDCG@5 | Mean latency | Initial ingest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Requests | 1.000 | 0.875 | 0.908 | 38.8 ms | 230.1 ms |
| chi | 0.875 | 0.875 | 0.847 | 45.4 ms | 183.7 ms |
| serde_json | 1.000 | 1.000 | 1.000 | 109.3 ms | 458.2 ms |
| **Weighted aggregate** | **0.958** | **0.917** | **0.918** | **64.5 ms** | — |

Grouped by the manifest's coarse question taxonomy, boundary-handling and data-model cases scored 1.000 on all
three ranking metrics. Execution-path cases were the weakest slice at 0.833 Recall@5, 0.833 MRR, and 0.796 nDCG@5;
supporting-concern cases scored 1.000, 0.833, and 0.877. Reporting the weak slice makes the next evaluation work
clearer than a single aggregate score.

The default external gate leaves margin below that run at 0.85 Recall@5, 0.80 MRR, and 0.80 nDCG@5. This avoids
turning normal cross-platform timing or harmless tie changes into false confidence while still rejecting material
quality regressions.

## Engineering Findings

- Python AST boundaries produced useful function and class metadata without a third-party parser.
- Declaration-aware Go and Rust windows were sufficient for this small corpus, so adding tree-sitter as a base
  dependency is not yet justified.
- File diversity matters: returning five chunks from one strong file is less useful to an agent than returning a
  bounded set of distinct implementation files.
- Exact path, symbol, and FTS5 evidence complements deterministic embeddings, especially for identifiers such as
  `HTTPAdapter`, `ServeHTTP`, `Serializer`, and `Deserializer`.
- The larger serde_json index had the highest mean latency, reinforcing the need to track operational cost alongside
  ranking quality.

## Limits Of The Claim

Twelve hand-labeled questions do not establish general coding-agent effectiveness. The corpus currently omits
JavaScript, TypeScript, Java, SQL, monorepos, generated-code-heavy projects, and tasks that require editing or test
execution. It also does not compare task completion with and without Kinekt. Those are the next studies; tuning the
current twelve cases more aggressively would risk benchmark overfitting.

## Reproduce

The command requires network access for the three pinned clones and uses temporary directories for all external
source and indexes:

```bash
uv run --locked python scripts/check_external_retrieval_eval.py
```

The manifest is `evals/external-repositories.eval.json`, and the implementation is
`scripts/check_external_retrieval_eval.py`.
