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
- Optional backends must fall back safely or report actionable diagnostics.

## Data Storage

By default, Kinekt stores data locally under `.kinekt/` inside the workspace. Users control whether that directory is ignored, backed up, mounted, or synced by their own infrastructure.
