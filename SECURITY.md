# Security Policy

Kinekt is designed as a local-first tool. The default runtime should not require sending source code, notes, git state, or session data to external services.

## Supported Versions

Kinekt is preparing for public beta. Security fixes should target the current `main` branch until stable releases are published.

## Reporting A Vulnerability

If you find a security issue, open a private report through GitHub Security Advisories when available. If advisories are unavailable, contact the maintainer directly before publishing details.

Please include:

- A clear description of the issue
- Reproduction steps
- Impacted command, API, or MCP tool
- Whether local files, git state, environment variables, or network calls are involved

## Security Boundaries

Kinekt should preserve these boundaries:

- File reads are scoped to a declared workspace root.
- MCP tools expose read/context operations only unless a future feature explicitly documents otherwise.
- Git commands must not perform automatic write operations.
- Ollama endpoints must be loopback-only.
- User-controlled limits must be clamped.
- Optional backends must fail explicitly or report actionable diagnostics; persisted vector configuration must
  never drift through a silent fallback.
- Repository detection is read-only and bounded; automatic state-writing commands require a confirmed attachment
  unless an explicit workspace path is supplied.
- `.kinekt/workspace.json` records user confirmation for onboarding but never expands the MCP allowlist.
- `workspace_status` is informational. An agent cannot use it, or any other Kinekt tool, to authorize a new root.
- Docker root aliases identify the same user-selected bind mount across host/container paths and are never used as
  filesystem authorization targets inside the container.

## Data Storage

By default, Kinekt stores data locally under `.kinekt/` inside the workspace. Users control whether that directory is ignored, backed up, mounted, or synced by their own infrastructure.

The local index does not itself send source code to a cloud service. If a user connects Kinekt to a cloud-hosted
coding client, the snippets returned through MCP may be processed under that client's data policy.

## Optional ChromaDB Boundary

Kinekt's `vector` extra uses ChromaDB only through an embedded `PersistentClient` rooted under the workspace's
`.kinekt/` directory. Kinekt does not start Chroma's HTTP server, accept remote collection definitions, or expose
Chroma's API through MCP.

As of 2026-07-21, ChromaDB 1.5.9 is reported by `pip-audit` under
[PYSEC-2026-311](https://osv.dev/vulnerability/PYSEC-2026-311), a critical code-injection advisory affecting its
network server's collection-creation API, and no fixed package release is listed. Kinekt's embedded-only use does
not exercise that endpoint, but the package remains optional and is not installed in the default or MCP runtime.
Do not expose a Chroma server based on this dependency; use the default `sqlite_local` backend when that boundary
cannot be guaranteed. The scheduled optional-backend job keeps the integration visible while the base locked
environment must pass a zero-known-vulnerability audit.
