# ADR 0002: Persist And Enforce The Index Configuration

- Status: Accepted
- Date: 2026-07-21

## Context

Content hashes alone cannot determine whether persisted chunks are compatible. Changing vector backend,
embedding provider, model, vector dimension, or chunking behavior can otherwise leave an empty, partial, or
mixed index while unchanged files are skipped.

## Decision

Persist a deterministic fingerprint of vector backend, embedding backend/model/dimension, and chunker version.
Ingestion rebuilds incompatible state; querying rejects it with an explicit `reindex` recovery command.
Persisted embedding backends do not silently fall back.

## Consequences

- Index behavior is inspectable and backend transitions are deterministic.
- Explicit Ollama or Chroma failures require user action instead of producing misleading results.
- Changing the chunk format requires incrementing the chunker version.
