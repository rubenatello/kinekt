# ADR 0003: Use Measured, Explainable Hybrid Retrieval

- Status: Accepted
- Date: 2026-07-21

## Context

Deterministic token-hash embeddings provide a reproducible offline baseline but are not sufficient for all coding
questions. File paths, symbols, and exact implementation terms are often stronger signals than vector similarity.

## Decision

Combine deterministic vector similarity, SQLite FTS5 lexical rank, path matches, symbol matches, and an explicit
source prior. Return component scores and line provenance. Gate ranking changes using versioned Recall@k, MRR,
and nDCG evaluation cases.

## Consequences

- Ranking remains local, deterministic, and explainable.
- Heuristic weights are visible technical debt and must be justified by evaluation results.
- The first pinned external corpus reduces repository-specific overfitting risk, but it must grow beyond twelve
  Python, Go, and Rust cases before broad quality claims are made.
