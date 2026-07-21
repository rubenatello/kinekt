# Two-Minute Terminal Demo

Kinekt includes a deterministic sample workspace and a non-interactive demo runner. The runner copies the
sample into a temporary directory, initializes and ingests it, runs an explained retrieval query, prints index
status, and removes the temporary data.

## Run With Docker

```bash
docker build --target test -t kinekt:test .
docker run --rm \
  --entrypoint sh \
  --mount type=bind,source="$(pwd)",target=/workspace,readonly \
  --env PYTHONPATH=/workspace/src \
  kinekt:test -c "cd /workspace && python scripts/run_demo.py"
```

PowerShell:

```powershell
$KinektRepo = (Get-Location).Path
docker run --rm `
  --entrypoint sh `
  --mount "type=bind,source=$KinektRepo,target=/workspace,readonly" `
  --env PYTHONPATH=/workspace/src `
  kinekt:test -c "cd /workspace && python scripts/run_demo.py"
```

## What The Demo Proves

- The database is created only inside disposable workspace storage.
- Code and architecture documentation are indexed together.
- A natural-language reliability question retrieves both the implementation and its design decision.
- `--explain` exposes vector, lexical, path, symbol, and source contributions.
- The sample can be reused for screenshots, terminal recordings, and client demonstrations without exposing a
  private repository.
