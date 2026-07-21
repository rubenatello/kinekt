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
- Editor-neutral `attach`, `workspace-status`, `ingest`, `query`, `agent-setup`, and `mcp-serve` flow.
- Git/project-marker discovery confirms the exact root before persisting attachment metadata.
- Native and Docker-backed configurations can be rendered for Codex, Claude Desktop, Gemini CLI, or generic MCP
  clients without silently editing their settings.
- MCP integration path for Claude Desktop, Codex, Gemini CLI, and Ollama-wrapper clients.
- SQLite storage under `.kinekt/` makes local data location inspectable.
- Workspace file reads block path traversal.
- User-controlled limits are clamped.
- Ollama endpoints are restricted to loopback.
- Ingestion rejects symlinks and resolved paths outside the workspace.
- Deleted, renamed, ignored, or unreadable indexed files are pruned on the next ingest.
- Index backend/model/dimension/chunker configuration is fingerprinted and incompatible indexes are rebuilt.
- MCP workspace access is restricted to explicitly allowed roots.
- `doctor` reports storage state without creating or migrating a database.
- Ingest prunes common generated, dependency, build, and cache folders before walking them.
- Ingest respects root `.gitignore` patterns for common local-project workflows.
- Query ranking includes path and lexical signals in addition to vector similarity.
- Package build and wheel install smoke tests exist.
- A committed cross-platform `uv.lock` drives local development, Docker builds, and CI.
- Structural bounded chunking covers Python, JavaScript, TypeScript, Go, Java, Rust, SQL, and Markdown.
- Long sessions compact older turns into an incremental deterministic summary while preserving recent raw turns.
- A pinned twelve-case external corpus measures Python, Go, and Rust repositories independently of Kinekt.
- A disposable sample workspace and terminal demo make the first-use story reproducible.
- Dependency review, vulnerability audit, SBOM, artifact-attestation, and scheduled integration workflows exist.
- Public-beta docs explain install, storage, agent connections, security, and contribution expectations.

## Current Weak Points

### Ease Of Use

- Kinekt is not yet published to PyPI, so install is still GitHub-based.
- MCP client configuration is generated for review, but users still save it in the selected client themselves.
- Users must understand that `.kinekt/` contains local indexed context and should usually be ignored by git.
- Ollama setup is user-managed and can be confusing without a guided local check.
- The scripted demo still needs a recorded portfolio video and live named-client captures.

### Context Quality

- Retrieval quality now has both repository-specific and pinned external-repository evidence, but twelve external
  cases remain too small for broad product claims.
- Python gets AST-aware chunks; other supported languages use deterministic declaration-aware heuristics rather
  than full parsers.
- Markdown is heading-aware and bounded, but does not parse embedded language structure.
- Explainable hybrid vector, FTS5, path, symbol, and source scoring exists, but there is no symbol graph or
  learned reranker.
- The benchmark measures retrieval, not whether an agent completes software tasks faster or more accurately.

### Agent Integration

- MCP SDK and Inspector discovery pass, and Codex Docker configuration parsing is recorded.
- Live tool calls from Claude Desktop and Gemini CLI still need to be recorded on machines with those clients.
- Kinekt has a local `agent-turn`, but it is not a full coding agent and should not be marketed as one.

## External Repository Evidence

The pinned external evaluation clones exact revisions of Requests (Python), chi (Go), and serde_json (Rust), then
indexes and queries each in temporary local storage. Across twelve curated questions, the current deterministic
Docker run scored 0.958 Recall@5, 0.917 MRR, and 0.918 nDCG@5. See
[retrieval-evaluation.md](retrieval-evaluation.md) for per-repository results and limitations.

An earlier client-led test against another repository also showed that public beta must optimize for real-world
project friction, not only toy workspaces.

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
- FastMCP registers the documented tool names directly, and a real stdio client/server integration test validates
  discovery of `query_knowledge_base`, `get_git_context`, `read_workspace_file`, `session_start`,
  `session_history`, `agent_turn`, and `workspace_status`.

### Security And Trust

- `.kinekt/` stores indexed snippets locally and is not encrypted.
- Allowed roots are configured at MCP server startup; interactive per-tool approval remains client-managed.
- There is no audit log or explicit per-tool consent prompt.
- Optional sync/hosted storage is intentionally not implemented and would require encryption, identity, tenancy, deletion, and access controls.

## Path To Game-Changing Status

### 1. Frictionless First Use

- Publish to PyPI after CI is green and package smoke remains clean.
- Document `pipx install kinekt` or `uv tool install kinekt` as the preferred user install path.
- The sample workspace and disposable terminal demo are implemented; record the short video and add it to the
  portfolio surface.
- Extend `doctor` into a single explicit readiness report only if user testing shows the documented demo and MCP
  protocol checker are still too fragmented.
- Workspace auto-detection, explicit attachment, attach-and-ingest, Docker root aliases, and agent config rendering
  are implemented; validate the flow with first-time users before adding editor-specific plugins.

### 2. Safer Agent Connections

- Optionally persist allowed workspace roots in an explicit Kinekt config file; CLI and environment allowlists
  are already implemented.
- Preserve the existing canonical allowlist check for every MCP tool.
- Keep `read_workspace_file` read-only and path-scoped.
- Add docs that explain what every MCP tool can and cannot do.
- MCP Inspector validation is recorded; complete live query and rejection evidence for Claude Desktop and Gemini
  CLI.

### 3. Better Retrieval

- Language-aware bounded chunking is implemented for Python, JavaScript, TypeScript, Go, Java, Rust, and SQL.
- Expand the implemented hybrid search with import and recent-git signals only when evaluation shows value.
- Grow the external gate beyond the current three repositories and twelve cases.
- Report retrieval quality by language and question type before adopting a full parser or learned reranker.

### 4. Context Beyond Files

- Improve git context beyond status: current branch, recent commits, changed files, and unstaged diff summaries.
- Add optional ingestion for docs folders, ADRs, issue exports, and markdown knowledge bases.
- Deterministic session summaries are implemented; evaluate optional model-backed summaries only if they remain
  local, bounded, and inspectable.
- Add developer profile support only when the behavior is explicit and inspectable.

### 5. Optional Orchestration

- Keep Kinekt's core as a context server.
- Add a separate optional agent mode only after retrieval and MCP trust boundaries are stronger.
- If an agent mode is added, prefer LangGraph for explicit state machines and checkpointing.
- Keep write operations behind explicit user approval; do not add hidden source-control mutations.

## Completion Confidence

Current public-beta foundation: high.

Current game-changing maturity: medium.

The main gap is no longer repository implementation, packaging, workspace trust, or a first external retrieval
benchmark. It is causal product evidence: whether real coding agents complete representative tasks better with
Kinekt than without it. That requires live client validation, a larger task corpus, and the already-scripted demo
presented clearly to portfolio reviewers.
