# Engineering Case Study: Making Local Context Trustworthy

## The Challenge

Kinekt began as a useful local prototype: scan a repository, create deterministic embeddings, and expose the
results to coding agents. That was enough to demonstrate the idea, but not enough to demonstrate production
engineering judgment. The risky parts were the seams: stale files could survive in the index, backend changes
could silently invalidate vectors, workspace access was not centrally authorized, and retrieval quality was a
claim rather than a measured property.

The hardening goal was therefore not "add more AI." It was to make the context supplied to an AI system safe,
inspectable, reproducible, and measurable.

## Constraints

- Source code must remain local by default.
- Workspace and git access must remain read-only unless the user explicitly invokes an indexing or session
  write workflow.
- The base runtime must use the Python standard library and SQLite without requiring a hosted service.
- Local fallback behavior must be deterministic enough for repeatable evaluation.
- Optional Ollama and Chroma integrations must fail explicitly instead of silently changing persisted index
  semantics.

## Engineering Decisions

### Make the persisted index a contract

Kinekt now stores a fingerprint of its vector backend, embedding backend and model, embedding dimension, and
chunker version. Queries validate that contract; ingestion rebuilds when it changes. Deleted, renamed, ignored,
unreadable, and out-of-bound symlink targets are pruned or rejected. This trades a potentially expensive rebuild
for protection against mixed vector spaces and convincing-but-invalid results.

### Prefer explainable hybrid retrieval

The deterministic embedding remains useful for reproducibility, but it is not a strong semantic model. Kinekt
adds SQLite FTS5 retrieval and reranks a broad bounded candidate pool using vector, lexical, path, symbol, and
source signals. Every result carries component scores, a ranking reason, symbol or heading context, and line
ranges. The approach is deliberately simple enough to inspect and benchmark before introducing a retrieval
framework.

### Put authorization before MCP tools

Every MCP operation resolves a canonical workspace and checks it against configured allowed roots. File reads
also resolve the final target, which blocks both `..` traversal and symlinks escaping the workspace. Query and
history commands open SQLite in true read-only mode and do not create a database as a side effect.

### Separate workspace discovery from workspace authorization

Editor terminals can start several directories below the project root, while Docker sees a mounted repository at
a different path than the host. Kinekt now detects the nearest Git or recognized project root, presents that
identity for explicit confirmation, and stores inspectable attachment metadata under `.kinekt/`. Portable root
aliases make the confirmation recognizable across a host/container bind mount. This metadata improves onboarding
but never grants MCP access: canonical server allowlists remain the authorization boundary, and the model receives
only a read-only `workspace_status` tool.

The related `agent-setup` command renders Codex, Claude Desktop, Gemini CLI, or generic stdio configuration for
review without modifying another application's settings. That trades one manual copy step for a safer and more
portable trust model.

### Treat Docker as the reproducible product path

The production image installs a built wheel, contains the MCP runtime and git, and runs as a non-root user. A
separate Docker target runs the installed-package test suite. Compose and CI use the same targets, which makes
the container a portable verification environment rather than an afterthought. A committed universal `uv.lock`
resolves supported Python and operating-system markers once; CI and Docker reject lock drift.

## Measured Result

The first ten-question repository evaluation scored 0.55 Recall@5, 0.252 MRR, and 0.351 nDCG@5. The hardened
hybrid implementation currently scores at least 0.80 Recall@5, 0.55 MRR, and 0.60 nDCG@5—the enforced CI
floors—with the exact recorded run published in [retrieval-evaluation.md](retrieval-evaluation.md). The gate
indexes a fresh database and excludes its own case payload to prevent evaluation leakage.

A second gate clones exact revisions of Requests, chi, and serde_json and evaluates twelve Python, Go, and Rust
questions. The recorded deterministic Docker run scored 0.958 Recall@5, 0.917 MRR, and 0.918 nDCG@5. This is useful
cross-repository evidence, but the sample remains intentionally described as small and curated.

The quality suite also enforces linting, static typing, at least 75% line coverage, package build/install checks,
schema migrations, concurrent SQLite writes, workspace-boundary attacks, and an actual MCP stdio handshake.

## Reproduce It

```bash
docker build --target test -t kinekt:test .
docker run --rm kinekt:test
python scripts/check_retrieval_eval.py
python scripts/check_external_retrieval_eval.py
python scripts/check_package.py
```

For the real runtime path, build the final image and follow the mounted-workspace commands in the
[README](../README.md#docker).

## What I Would Build Next

The next retrieval decision should be driven by expanding the external corpus and measuring downstream agent task
success, not more tuning against Kinekt itself. The current corpus can now show broad regressions, structural
chunking covers the prioritized languages, long sessions compact deterministically, and release automation emits
an SBOM plus tagged artifact provenance. A larger study should determine which languages merit full parser
dependencies and whether stronger local embeddings justify their operational cost.

This sequence is intentional: trustworthy context and credible evidence create more value for an AI-forward
engineering portfolio than adding orchestration complexity before the data layer is reliable.
