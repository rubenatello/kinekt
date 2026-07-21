# Public Beta Checklist

Kinekt is ready for public beta when this checklist is complete.

## Developer Experience

- [x] README explains the problem, solution, install path, quickstart, MCP usage, local AI options, and beta limitations.
- [x] MCP client docs include Claude Desktop, Codex, Gemini CLI, and Ollama-wrapper guidance.
- [x] `kinekt doctor` gives actionable setup guidance without creating or migrating workspace storage.
- [x] The CLI works from a clean wheel install.
- [x] Kinekt has been smoke-tested against Requests and evaluated against pinned Requests, chi, and serde_json revisions.
- [x] Editor terminals can detect and confirm a Git/project root, optionally ingest it, and generate reviewed MCP
  configuration for Codex, Claude Desktop, Gemini CLI, or a generic client.

## Compatibility

- [x] Python support is declared as `>=3.11,<3.15`.
- [ ] CI passes on Python 3.11, 3.12, 3.13, and 3.14 after these changes are published.
- [ ] CI passes on Ubuntu, Windows, and macOS after these changes are published.
- [ ] Docker smoke tests pass on Python 3.11 and 3.14 in CI (both versions are locally verified).

## Safety

- [x] Workspace file reads block path traversal.
- [x] Ingestion skips symlinks and resolved files outside the declared workspace.
- [x] MCP tools reject workspaces outside configured allowed roots.
- [x] Workspace attachment requires a human confirmation or explicit `--yes`; MCP tools cannot grant access.
- [x] User-controlled limits are clamped.
- [x] Ollama endpoints are loopback-only.
- [x] Kinekt does not automatically install software, pull models, commit, push, deploy, or mutate source control.
- [x] Generated artifacts are ignored and not committed.

## Packaging

- [x] The Dockerized `python -m pytest -q` suite passes.
- [x] `python scripts/check_package.py` passes inside Docker.
- [ ] `python scripts/test_python_versions.py` passes for every installed local interpreter.
- [x] Built wheel installs into a clean virtual environment.
- [x] `kinekt --help` works from the installed wheel.
- [x] `python scripts/smoke_workspace.py <path-to-project>` passes for the pinned Requests workspace with cleanup.

## Portfolio And Release Evidence

- [x] A disposable sample workspace and deterministic terminal demo are included.
- [x] Retrieval gates cover Kinekt plus three external repositories in Python, Go, and Rust.
- [x] Real embedded ChromaDB, Ollama HTTP-contract, MCP SDK, and MCP Inspector checks exist.
- [x] The base locked environment passes `pip-audit` with no known vulnerabilities.
- [x] Release automation builds a wheel, sdist, container archive, CycloneDX SBOM, and tagged provenance attestation.
- [ ] Claude Desktop and Gemini CLI validation are recorded from systems where those clients are installed.
- [ ] A release tag has executed the artifact workflow and its outputs have been manually inspected.
- [ ] The scripted terminal demo has been recorded as a short portfolio video.

## Launch Notes

- Public beta means useful, safe, and documented, not enterprise-stable.
- Hosted sync is not included in public beta.
- Users own local data under `.kinekt/`.
- The roadmap from beta to stronger agentic-development value is tracked in [Game-Changer Roadmap](gamechanger-roadmap.md).
