# Contributing To Kinekt

Kinekt is a local-first developer context engine for agentic coding. Contributions should preserve local privacy, predictable behavior, and read-only safety boundaries.

## Development Setup

Kinekt supports Python 3.11 through Python 3.14.

```bash
python -m pip install -e ".[dev,mcp]"
```

Run the test suite:

```bash
python -m pytest -q
```

Run package validation:

```bash
python scripts/check_package.py
```

Run installed-version validation for every local interpreter you have:

```bash
python scripts/test_python_versions.py
```

## Contribution Rules

- Keep Kinekt local-first by default.
- Do not add mandatory cloud dependencies.
- Do not add hidden git writes, commits, pushes, rebases, resets, or deploys.
- Keep workspace file access scoped to an explicit workspace root.
- Clamp user-controlled limits and fail clearly on invalid input.
- Add tests for behavior changes, especially path boundaries, limit clamping, and failure handling.

## Pull Request Checklist

- Tests pass locally with `python -m pytest -q`.
- Package validation passes with `python scripts/check_package.py`.
- Docs are updated for user-facing commands, MCP tools, or environment variables.
- Generated files such as `__pycache__`, `.egg-info`, `dist`, and `.kinekt` are not committed.
- New dependencies are optional unless they are necessary for the base runtime.
