# Public Beta Checklist

Kinekt is ready for public beta when this checklist is complete.

## Developer Experience

- README explains the problem, solution, install path, quickstart, MCP usage, local AI options, and beta limitations.
- MCP client docs include Claude Desktop, Codex, Gemini CLI, and Ollama-wrapper guidance.
- `kinekt doctor` gives actionable setup guidance without mutating the user's machine.
- The CLI works from a clean wheel install.

## Compatibility

- Python support is declared as `>=3.11,<3.15`.
- CI passes on Python 3.11, 3.12, 3.13, and 3.14.
- CI passes on Ubuntu, Windows, and macOS.
- Docker smoke tests pass on Python 3.11 and 3.14.

## Safety

- Workspace file reads block path traversal.
- User-controlled limits are clamped.
- Ollama endpoints are loopback-only.
- Kinekt does not automatically install software, pull models, commit, push, deploy, or mutate source control.
- Generated artifacts are ignored and not committed.

## Packaging

- `python -m pytest -q` passes.
- `python scripts/check_package.py` passes.
- `python scripts/test_python_versions.py` passes for installed local interpreters.
- Built wheel installs into a clean virtual environment.
- `kinekt --help` works from the installed wheel.

## Launch Notes

- Public beta means useful, safe, and documented, not enterprise-stable.
- Hosted sync is not included in public beta.
- Users own local data under `.kinekt/`.
