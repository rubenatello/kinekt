# Changelog

All notable changes to Kinekt will be documented in this file.

## 0.1.0 - Public Beta Preparation

- Added local-first CLI foundation for init, ingest, query, git context, safe file reads, sessions, diagnostics, and MCP serving.
- Added SQLite schema v4 and migrations for sessions, bounded deterministic session summaries, thread messages,
  file registry, developer profile, FTS5 retrieval, and local chunk storage.
- Added deterministic local embeddings and generation fallbacks.
- Added optional Ollama embedding/generation support with local-only endpoint checks and HTTP contract tests.
- Added an optional embedded ChromaDB vector backend with explicit failure instead of silent backend fallback.
- Added canonical workspace authorization, symlink/traversal protection, true read-only query paths, stale-file
  pruning, bounded inputs, and persisted index-configuration fingerprints.
- Added explainable hybrid vector/FTS5 retrieval, structural bounded chunking for Python, JavaScript, TypeScript,
  Go, Java, Rust, SQL, and Markdown, and a deterministic `--explain` score breakdown.
- Added versioned Kinekt and pinned multi-repository retrieval evaluations with CI quality gates.
- Added a multi-stage non-root Docker image, Compose workflow, clean installed-package test target, and a
  cross-platform `uv.lock` consumed by Docker and CI.
- Added MCP SDK and Inspector discovery checks, a named-client validation matrix, and explicit MCP tool schemas and
  descriptions.
- Added a disposable sample workspace and two-minute terminal demo runner.
- Added lint, typing, coverage, package, dependency audit/review, scheduled integration, SBOM, and tagged artifact
  provenance workflows.
- Added public beta onboarding docs and MCP client setup guidance.
- Added editor-neutral Git/project-root detection, explicit workspace attachment, portable Docker root aliases,
  optional attach-and-ingest, workspace diagnostics, and generated Codex/Claude/Gemini MCP configurations.
- Added an MCP `workspace_status` tool so clients can confirm the exact authorized project and index state.
- Added Python 3.11 through Python 3.14 support metadata and CI matrix.
- Added package build/install smoke validation.
