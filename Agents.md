# Agents.md

This document defines repository-specific instructions and best practices for contributors and coding agents working on Kinekt.

## Product Intent

Kinekt is a local-first developer context engine. Keep implementation aligned with these constraints:

- Local-by-default behavior (no mandatory cloud dependencies)
- Read-only safety boundaries for workspace and git interactions unless explicitly requested
- Deterministic, inspectable behavior for indexing and retrieval paths

## Architecture Priorities

- Keep orchestration, transport/tooling, and data/storage concerns separated by module boundaries.
- Preserve the schema contract from the design document (`sessions`, `thread_messages`, `file_registry`, `developer_profile`).
- Prefer explicit interfaces for tool payloads and predictable return shapes.

## Security And Safety

- Never bypass workspace path validation. Any file read/write operation must be scoped to a declared workspace root.
- Do not add automatic git write operations (commit, push, rebase, reset) behind APIs/tools.
- Clamp user-controlled limits (`limit`, `max_chars`) to safe upper bounds.
- Keep dependencies minimal and avoid introducing services that require sending local source code externally.

## Coding Guidelines

- Use Python 3.11+ compatible code and standard library first.
- Keep functions small and composable; avoid hidden side effects.
- Maintain deterministic behavior in local fallback paths (chunking, embeddings, ranking).
- Raise clear errors for invalid inputs instead of silently ignoring issues.

## Testing Expectations

For behavior changes, cover at least:

- Happy-path indexing/query behavior
- Path traversal and boundary checks
- Input clamping and edge-case handling

Current test command:

```bash
python -m pytest -q
```

## Documentation Expectations

When adding user-facing commands or server modes:

- Update `README.md` with install and usage examples.
- Keep docs aligned with actual CLI arguments and defaults.
- Document optional dependencies separately from the base runtime.
