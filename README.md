# Kinekt

Kinekt is a local-first context engine for agentic coding.

It helps coding agents understand your project without sending your source code to a required cloud service. You point Kinekt at a workspace, it indexes local code and markdown notes, then exposes that context through a CLI and a Model Context Protocol (MCP) server.

Kinekt is not the agent. It is the context layer that agents use.

Works with MCP-capable clients such as Claude Desktop, Codex, Gemini CLI, and local Ollama-wrapper clients. Ollama itself is a local model runtime, so direct Ollama MCP usage requires an MCP-aware client or wrapper.

## The Problem

Developers keep important context in too many places:

- Source files and architecture modules
- Local markdown notes, Obsidian vaults, and exported docs
- Git branch state and uncommitted changes
- Previous agent or chat sessions

Coding agents are useful, but they often lose project context between turns or only see the files pasted into the prompt. That leads to repeated explanations, missed constraints, and weaker code suggestions.

## How Kinekt Helps

Kinekt turns local project context into a queryable developer memory layer:

1. `kinekt init` creates a workspace-local SQLite database under `.kinekt/kinekt.sqlite3`.
2. `kinekt ingest <workspace>` scans code and markdown, chunks files, hashes content, and skips unchanged files.
3. Kinekt stores searchable chunks in local SQLite by default, with optional local ChromaDB support.
4. `kinekt query "<question>"` retrieves relevant indexed context.
5. `kinekt mcp-serve` exposes safe tools to MCP clients:
   - `query_knowledge_base`
   - `get_git_context`
   - `read_workspace_file`
   - `session_start`
   - `session_history`
   - `agent_turn`

The default path has no mandatory cloud dependency. Optional Ollama support can provide local embeddings and local generation when the user installs and starts Ollama separately.

## Status

Kinekt is preparing for public beta. It is useful for local testing and agent integration experiments, but it is not yet an enterprise-stable product.

Current beta priorities:

- Local-first behavior by default
- Read-only workspace and git safety boundaries unless a user explicitly acts outside Kinekt
- Python 3.11 through Python 3.14 support
- Cross-platform CLI and test coverage on Windows, macOS, and Linux
- Stdio MCP server support for agent integrations

## Install

Kinekt supports Python 3.11 through Python 3.14.

For local development from a clone:

```bash
python -m pip install -e ".[dev,mcp]"
```

For a direct GitHub install during beta:

```bash
python -m pip install "kinekt[mcp] @ git+https://github.com/rubenatello/kinekt.git"
```

Optional ChromaDB vector backend:

```bash
python -m pip install -e ".[vector]"
```

Optional local Ollama support is user-managed. Kinekt does not install Ollama or pull models automatically.

## Quickstart

Initialize a workspace database:

```bash
kinekt init /path/to/workspace
```

Index code and markdown:

```bash
kinekt ingest /path/to/workspace
```

Ask a local context question:

```bash
kinekt query "where is session history stored?" --workspace /path/to/workspace --limit 5
```

Show local runtime diagnostics:

```bash
kinekt doctor /path/to/workspace
```

Run the MCP server over stdio:

```bash
kinekt mcp-serve
```

Connect your MCP client to that command. See [MCP client setup](docs/mcp-clients.md) for Claude Desktop, Codex, Gemini CLI, and Ollama-wrapper guidance.

For more detail on agent integration and where data is stored, see:

- [Agent connections](docs/agent-connections.md)
- [Storage, hosting, and sync](docs/storage-and-sync.md)

## CLI Usage

Read git status context:

```bash
kinekt git-context /path/to/repo
```

Read a workspace file safely:

```bash
kinekt read-file src/main.py --workspace /path/to/workspace --max-chars 2000
```

`read-file` blocks path traversal outside the declared workspace. `--max-chars` is clamped to `1..50000`.

Start or reuse a session:

```bash
kinekt session-start --workspace /path/to/workspace
```

Run a stateful local agent turn:

```bash
kinekt agent-turn "how does ingestion work?" --workspace /path/to/workspace --session-id <session-id>
```

Inspect session history:

```bash
kinekt session-history <session-id> --workspace /path/to/workspace --limit 30
```

Limits are clamped for safety:

- `query --limit`: `1..20`
- `session-history --limit`: `1..100`
- `agent-turn --query-limit`: `1..10`
- `agent-turn --history-window`: `1..20`

## Optional Local AI

Kinekt defaults to deterministic local fallbacks, so it works without Ollama.

To use Ollama for local embeddings:

```bash
export KINEKT_EMBEDDING_BACKEND=ollama
export KINEKT_OLLAMA_URL=http://127.0.0.1:11434/api/embeddings
export KINEKT_OLLAMA_MODEL=nomic-embed-text
export KINEKT_OLLAMA_TIMEOUT_SECONDS=10
```

To use Ollama for local generation in `agent-turn`:

```bash
export KINEKT_GENERATION_BACKEND=ollama
export KINEKT_OLLAMA_GENERATE_URL=http://127.0.0.1:11434/api/generate
export KINEKT_OLLAMA_GENERATE_MODEL=llama3.1:8b
export KINEKT_OLLAMA_GENERATE_TIMEOUT_SECONDS=20
```

Then validate your setup:

```bash
kinekt doctor /path/to/workspace
```

Safety behavior:

- Non-loopback Ollama endpoints are rejected.
- If Ollama is unreachable or returns invalid payloads, Kinekt falls back to deterministic local behavior.
- Kinekt reports setup guidance but does not install Ollama, start services, or pull models automatically.

## Optional Vector Backend

Kinekt defaults to SQLite-backed local vector search.

To request local ChromaDB storage:

```bash
export KINEKT_VECTOR_BACKEND=chromadb
```

If ChromaDB is unavailable or fails to initialize, Kinekt falls back to SQLite-backed local storage.

## Docker

Build the image:

```bash
docker build -t kinekt:local .
```

Run commands against a mounted workspace:

```bash
docker run --rm -it -v /path/to/workspace:/workspace kinekt:local init /workspace
docker run --rm -it -v /path/to/workspace:/workspace kinekt:local ingest /workspace
docker run --rm -it -v /path/to/workspace:/workspace kinekt:local query "where is context stored?" --workspace /workspace
```

To smoke test another supported Python line:

```bash
docker build --build-arg PYTHON_VERSION=3.14 -t kinekt:py314 .
docker run --rm kinekt:py314 --help
```

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev,mcp]"
```

Run tests:

```bash
python -m pytest -q
```

Validate packaging from a clean wheel install:

```bash
python scripts/check_package.py
```

Validate every supported Python version installed locally:

```bash
python scripts/test_python_versions.py
```

The version script tests Python 3.11, 3.12, 3.13, and 3.14 when those interpreters are available, and skips versions that are not installed locally.

## CI

GitHub Actions workflows are included for:

- Python tests on Ubuntu, Windows, and macOS for Python 3.11 through 3.14
- Docker image build and smoke tests on Python 3.11 and 3.14
- Package build, metadata, wheel install, and CLI smoke validation

## Logging And Errors

Kinekt emits structured JSON logs on stderr for CLI and MCP command/tool events.

- Set log level with `KINEKT_LOG_LEVEL`, for example `INFO`, `WARNING`, or `ERROR`.
- CLI failures are normalized to JSON error payloads: `{"code": "...", "message": "..."}`.
- MCP tool failures use the same error shape: `{"code": "...", "message": "..."}`.

## Public Beta Limitations

- MCP server transport is stdio-only.
- Ollama is optional and user-managed.
- Deterministic local embeddings/generation are fallbacks, not a replacement for high-quality semantic models.
- Kinekt intentionally avoids automatic git writes, commits, pushes, and source-control mutations.
