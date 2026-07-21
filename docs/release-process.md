# Release Process

Kinekt's release workflow builds and attests artifacts; it does not publish them to PyPI or a container registry.
Publishing remains a separate, explicit maintainer decision.

## 1. Prepare The Version

- Update the version in `pyproject.toml`.
- Move release notes into a dated section in `CHANGELOG.md`.
- Regenerate `uv.lock` with the repository's pinned uv line and verify `uv lock --check`.
- Review optional-backend security notes, especially the current ChromaDB advisory boundary in `SECURITY.md`.

## 2. Run Local Docker Gates

```bash
docker build --target test -t kinekt:test .
docker run --rm kinekt:test
docker run --rm --entrypoint python kinekt:test -m pip_audit --local
```

Run the repository evaluations from a source bind mount so their fixtures and scripts are available:

```bash
docker run --rm --entrypoint sh \
  --mount type=bind,source="$(pwd)",target=/workspace,readonly \
  --env PYTHONPATH=/workspace/src \
  kinekt:test -c "cd /workspace && python scripts/check_retrieval_eval.py"
```

The external gate additionally requires network access:

```bash
docker run --rm --entrypoint sh \
  --mount type=bind,source="$(pwd)",target=/workspace,readonly \
  --env PYTHONPATH=/workspace/src \
  kinekt:test -c "cd /workspace && python scripts/check_external_retrieval_eval.py"
```

## 3. Verify Hosted CI

Before tagging, require green results for:

- Static quality, coverage, package verification, and dependency audit
- Python 3.11-3.14 on Ubuntu, Windows, and macOS
- Python 3.11 and 3.14 Docker smoke builds
- Dependency review
- Optional ChromaDB, Ollama contract, MCP SDK, and MCP Inspector integration evidence
- Pinned external retrieval evaluation

## 4. Build Tagged Artifacts

Push an intentional `v*` tag only after the version and changelog match. The `Release Artifacts` workflow creates:

- Wheel and source distribution
- Non-root production container archive
- CycloneDX 1.5 SBOM for the MCP runtime dependency graph
- GitHub build-provenance attestations over the tagged artifacts

The workflow also validates package metadata and smoke-tests the container before upload.

## 5. Inspect Before Publishing

Download the `kinekt-release-artifacts` workflow artifact and verify:

- Wheel and sdist filenames match the intended version.
- `twine check` passed and the wheel installs in a clean environment.
- `kinekt --help` works from both the wheel and container.
- The SBOM lists the expected MCP runtime packages and no development-only dependency is presented as runtime.
- GitHub displays a valid provenance attestation for each tagged artifact.
- The container runs as the `kinekt` user and has no embedded workspace data.

Only then make a separate decision to publish. A failed or questionable build should be replaced by a new version;
do not overwrite an existing release artifact under the same version.
