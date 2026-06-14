# kinekt

Kinekt is a local-first developer context engine designed to eliminate context-switching for software engineers. Developers treat their codebases, git commit logs, and markdown knowledge bases (like Obsidian or Notion exports) as fragmented data silos.

## Current implementation (MVP foundation)

This repository now includes a working local-first core with:

- Workspace ingestion for code and markdown files
- File hash registry to skip unchanged files
- Local SQLite persistence with the design document schema (`sessions`, `thread_messages`, `file_registry`, `developer_profile`)
- Local chunk storage and deterministic embedding fallback for semantic retrieval
- CLI commands for ingestion, querying, git context, and safe file reads
- FastMCP server mode exposing `query_knowledge_base`, `get_git_context`, `read_workspace_file`, `session_start`, `session_history`, and `agent_turn`
- Stateful session persistence (`sessions`, `thread_messages`) and deterministic agent turns

## Setup

```bash
python -m pip install -e .
```

For development (tests):

```bash
python -m pip install -e .[dev]
python -m pip install pytest
```

For MCP server support:

```bash
python -m pip install -e .[mcp]
```

For optional ChromaDB vector backend support:

```bash
python -m pip install -e .[vector]
```

## Production-oriented local embedding options

Kinekt defaults to deterministic local embeddings (no external service required).

Optional local Ollama embeddings are supported by environment variables:

```bash
export KINEKT_EMBEDDING_BACKEND=ollama
export KINEKT_OLLAMA_URL=http://127.0.0.1:11434/api/embeddings
export KINEKT_OLLAMA_MODEL=nomic-embed-text
export KINEKT_OLLAMA_TIMEOUT_SECONDS=10
```

Safety behavior:

- If Ollama is unreachable or returns invalid payloads, Kinekt falls back to deterministic local embeddings.
- Non-loopback embedding endpoints are rejected to preserve local-first data boundaries.

## Vector store backend options

Kinekt defaults to local SQLite-backed vector storage (`sqlite_local`).

Optional local ChromaDB vector storage:

```bash
export KINEKT_VECTOR_BACKEND=chromadb
```

Safety behavior:

- If ChromaDB is unavailable or fails to initialize, Kinekt falls back to local SQLite-backed vector storage.

## Production-oriented local generation options

`agent-turn` defaults to deterministic local generation for offline reliability.

Optional local Ollama text generation is supported by environment variables:

```bash
export KINEKT_GENERATION_BACKEND=ollama
export KINEKT_OLLAMA_GENERATE_URL=http://127.0.0.1:11434/api/generate
export KINEKT_OLLAMA_GENERATE_MODEL=llama3.1:8b
export KINEKT_OLLAMA_GENERATE_TIMEOUT_SECONDS=20
```

Safety behavior:

- If Ollama generation is unreachable or returns invalid payloads, Kinekt falls back to deterministic local generation.
- Non-loopback generation endpoints are rejected to preserve local-first data boundaries.

## Usage

Initialize local database:

```bash
kinekt init
```

Schema migrations are applied automatically on startup using SQLite `PRAGMA user_version`.

Ingest a workspace:

```bash
kinekt ingest /path/to/workspace
```

Query the indexed context:

```bash
kinekt query "where is developer profile stored?" --limit 5
```

`--limit` is clamped to `1..20` for safety.

Show git context:

```bash
kinekt git-context /path/to/repo
```

Read a workspace file safely (path traversal protected):

```bash
kinekt read-file src/main.py --workspace /path/to/workspace --max-chars 2000
```

`--max-chars` is clamped to `1..50000` for safety.

Run FastMCP server over stdio:

```bash
kinekt mcp-serve
```

Start or reuse a session:

```bash
kinekt session-start --workspace /path/to/workspace
```

Run a stateful agent turn:

```bash
kinekt agent-turn "how is context stored?" --workspace /path/to/workspace --session-id <session-id>
```

Show local runtime diagnostics:

```bash
kinekt doctor /path/to/workspace
```

Inspect session history:

```bash
kinekt session-history <session-id> --workspace /path/to/workspace --limit 30
```

`session-history --limit` is clamped to `1..100` for safety.

`agent-turn --query-limit` is clamped to `1..10` and `--history-window` is clamped to `1..20`.

## Docker (optional)

Build image:

```bash
docker build -t kinekt:local .
```

Run commands against your local workspace via bind mount:

```bash
docker run --rm -it \
  -v /path/to/workspace:/workspace \
  kinekt:local init /workspace
```

Example ingest + query:

```bash
docker run --rm -it -v /path/to/workspace:/workspace kinekt:local ingest /workspace
docker run --rm -it -v /path/to/workspace:/workspace kinekt:local query "where is context stored?" --workspace /workspace
```

## Run tests

```bash
python -m pytest -q
```

## CI

GitHub Actions workflows are included for:

- Python test validation (`.github/workflows/ci-tests.yml`)
- Docker image build + smoke run (`.github/workflows/docker-smoke.yml`)

## Logging And Error Codes

Kinekt emits structured JSON logs on stderr for CLI and MCP command/tool events.

- Set log level with `KINEKT_LOG_LEVEL` (for example `INFO`, `WARNING`, `ERROR`).
- CLI failures are normalized to JSON error payloads: `{"code": "...", "message": "..."}`.
- MCP tool failures are normalized with prefixed error codes in tool exceptions (for example `ERR_INVALID_ARGUMENT: ...`).
