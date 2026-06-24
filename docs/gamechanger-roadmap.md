# Game-Changer Roadmap

This document captures the current product direction for turning Kinekt from a useful public-beta context tool into a high-leverage system for agentic and AI-assisted development.

## Plain-Term Product Definition

Kinekt is local memory for coding agents.

It scans a developer's local project, indexes useful context from code and markdown, stores that context locally, and exposes it through CLI and MCP tools. An AI coding agent can then ask Kinekt for relevant project context instead of relying only on what the user pasted into a prompt.

Kinekt is not the coding agent. It is the context layer that makes a coding agent less blind.

## LangGraph And LangChain Decision

LangGraph and LangChain are not required for Kinekt's core value.

The core value is:

```text
local workspace -> local index -> retrieval tools -> agent context
```

That can be accomplished with the current architecture: Python, SQLite, local embeddings, optional ChromaDB, optional Ollama, and MCP.

LangGraph becomes useful only if Kinekt becomes its own orchestrating agent instead of primarily serving context to other agents. Good future uses for LangGraph include:

- Multi-step planning loops
- Tool selection and retry flows
- Stateful task execution
- Reflection or self-correction steps
- Human approval gates before write actions
- Long-running workflows that need checkpointing

LangChain may be useful for integration convenience, but it should not be added as a base dependency unless it removes clear complexity. For public beta, avoid LangChain/LangGraph as mandatory dependencies because they increase install weight and maintenance surface without improving the current context-server promise.

Recommended position:

- Public beta: no required LangGraph or LangChain dependency.
- Future optional agent mode: consider LangGraph as an extra dependency, for example `kinekt[agent]`.
- Avoid a broad LangChain dependency unless a specific integration proves it is better than a small local adapter.

## Current Strengths

- Local-first by default with no mandatory cloud service.
- Simple CLI flow: `doctor`, `init`, `ingest`, `query`, `mcp-serve`.
- MCP integration path for Claude Desktop, Codex, Gemini CLI, and Ollama-wrapper clients.
- SQLite storage under `.kinekt/` makes local data location inspectable.
- Workspace file reads block path traversal.
- User-controlled limits are clamped.
- Ollama endpoints are restricted to loopback.
- Ingest prunes common generated, dependency, build, and cache folders before walking them.
- Ingest respects root `.gitignore` patterns for common local-project workflows.
- Query ranking includes path and lexical signals in addition to vector similarity.
- Package build and wheel install smoke tests exist.
- Public-beta docs explain install, storage, agent connections, security, and contribution expectations.

## Current Weak Points

### Ease Of Use

- Kinekt is not yet published to PyPI, so install is still GitHub-based.
- MCP setup requires manual client configuration.
- Users must understand that `.kinekt/` contains local indexed context and should usually be ignored by git.
- Ollama setup is user-managed and can be confusing without a guided local check.
- There is no demo project or first-five-minutes walkthrough proving value quickly.

### Context Quality

- Retrieval quality is MVP-level.
- Python gets AST-aware function/class chunks, but other languages use fixed-size module blocks.
- Markdown chunking is simple heading/block logic.
- Hybrid path/content scoring exists, but there is no symbol graph or learned reranker.
- There is no evaluation dataset to measure whether results are actually useful for coding tasks.

### Agent Integration

- MCP tools work at the interface level, but live validation with real clients still needs to be recorded.
- The MCP server accepts a `workspace` argument from the client. There is no configured workspace allowlist yet.
- Kinekt has a local `agent-turn`, but it is not a full coding agent and should not be marketed as one.

## External Repo Test Findings

A Claude-based test against another repository found that the public beta needs to optimize for real-world project friction, not only toy workspaces.

Findings converted into product requirements:

- Ingest must avoid generated/vendor trees by default.
- Ingest should honor project ignore rules where practical.
- Windows CLI output must not require users to set `PYTHONIOENCODING`.
- Search must understand paths and filenames, not only chunk text.
- MCP tool names in clients must match the public docs exactly.

Current implementation status:

- Default generated/vendor excludes are implemented for common folders such as `node_modules/`, `dist/`, `build/`, `.firebase/`, `.next/`, `.venv/`, and cache directories.
- Root `.gitignore` support is implemented for common file and directory patterns.
- CLI stdout/stderr are configured for UTF-8 with replacement fallback.
- Query scoring includes vector similarity plus path/content lexical boosts.
- FastMCP registers the documented tool names directly: `query_knowledge_base`, `get_git_context`, `read_workspace_file`, `session_start`, `session_history`, and `agent_turn`.

### Security And Trust

- `.kinekt/` stores indexed snippets locally and is not encrypted.
- `kinekt doctor` initializes a local database, so it is diagnostic but not purely read-only.
- There is no user approval model around which workspace paths an MCP client may access.
- There is no audit log or explicit per-tool consent prompt.
- Optional sync/hosted storage is intentionally not implemented and would require encryption, identity, tenancy, deletion, and access controls.

## Path To Game-Changing Status

### 1. Frictionless First Use

- Publish to PyPI after CI is green and package smoke remains clean.
- Document `pipx install kinekt` or `uv tool install kinekt` as the preferred user install path.
- Add a sample workspace and a five-minute demo.
- Add a single command or documented flow that validates install, workspace, index, query, and MCP readiness.

### 2. Safer Agent Connections

- Add a Kinekt config file with allowed workspace roots.
- Make MCP tools reject workspaces outside configured roots.
- Keep `read_workspace_file` read-only and path-scoped.
- Add docs that explain what every MCP tool can and cannot do.
- Record live validation with MCP Inspector plus at least one real client.

### 3. Better Retrieval

- Add language-aware chunking for common stacks: Python, JavaScript, TypeScript, Go, Java, Rust, and SQL.
- Add hybrid search combining vector similarity with lexical matching.
- Add reranking or scoring boosts for filenames, symbols, imports, headings, and recent git context.
- Add query/result evaluation fixtures based on real coding questions.
- Track retrieval quality over time with repeatable tests.

### 4. Context Beyond Files

- Improve git context beyond status: current branch, recent commits, changed files, and unstaged diff summaries.
- Add optional ingestion for docs folders, ADRs, issue exports, and markdown knowledge bases.
- Store session summaries, not only raw messages.
- Add developer profile support only when the behavior is explicit and inspectable.

### 5. Optional Orchestration

- Keep Kinekt's core as a context server.
- Add a separate optional agent mode only after retrieval and MCP trust boundaries are stronger.
- If an agent mode is added, prefer LangGraph for explicit state machines and checkpointing.
- Keep write operations behind explicit user approval; do not add hidden source-control mutations.

## Completion Confidence

Current public-beta foundation: high.

Current game-changing maturity: medium-low.

The main gap is no longer basic packaging or docs. The main gap is proof that Kinekt makes real coding agents materially better on real repositories. That proof requires live MCP validation, better retrieval quality, workspace trust controls, and a demo that makes the value obvious in minutes.
