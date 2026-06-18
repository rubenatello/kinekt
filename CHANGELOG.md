# Changelog

All notable changes to Kinekt will be documented in this file.

## 0.1.0 - Public Beta Preparation

- Added local-first CLI foundation for init, ingest, query, git context, safe file reads, sessions, diagnostics, and MCP serving.
- Added SQLite schema and migrations for sessions, thread messages, file registry, developer profile, and local chunk storage.
- Added deterministic local embeddings and generation fallbacks.
- Added optional Ollama embedding/generation support with local-only endpoint checks.
- Added optional ChromaDB vector backend with SQLite fallback.
- Added public beta onboarding docs and MCP client setup guidance.
- Added Python 3.11 through Python 3.14 support metadata and CI matrix.
- Added package build/install smoke validation.
