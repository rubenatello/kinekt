# Test Kinekt On Another Project

Use this guide to validate Kinekt against a real local repository without depending on its host Python setup.

The goal is to prove three things:

1. Kinekt is easy to install and run outside the Kinekt repo.
2. Kinekt can index another project without changing source files.
3. Kinekt returns context that would help an AI coding agent understand that project.

## 1. Build The Reproducible Images

From the Kinekt repo:

```powershell
docker build -t kinekt:local .
docker build --target test -t kinekt:test .
docker run --rm kinekt:local --help
```

For a locked host development environment instead, use:

```powershell
uv sync --locked --python 3.11 --extra dev --extra mcp
```

## 2. Choose The Target Project

Set the path to the other repo:

```powershell
$workspace = "C:\Projects\target-repo"
```

Kinekt stores its local index under:

```text
<workspace>\.kinekt\
```

Add this to the target project's `.gitignore` unless you intentionally want to commit local indexed context:

```gitignore
.kinekt/
```

## 3. Manual CLI Test

Detect, confirm, and index the repository in one step. The alias preserves the confirmed host identity when the
same project is mounted at `/workspace`:

```powershell
docker run --rm -it `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local attach /workspace --ingest
```

Confirm the detected workspace and diagnostics:

```powershell
docker run --rm `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local workspace-status /workspace
docker run --rm --mount "type=bind,source=$workspace,target=/workspace" kinekt:local doctor /workspace
```

Ask broad project questions:

```powershell
docker run --rm --mount "type=bind,source=$workspace,target=/workspace" kinekt:local query "what does this project do?" --workspace /workspace --limit 5
docker run --rm --mount "type=bind,source=$workspace,target=/workspace" kinekt:local query "where is the main application entrypoint?" --workspace /workspace --limit 5
docker run --rm --mount "type=bind,source=$workspace,target=/workspace" kinekt:local query "how is deployment configured?" --workspace /workspace --limit 5
```

Check git context:

```powershell
docker run --rm --mount "type=bind,source=$workspace,target=/workspace" kinekt:local git-context /workspace
```

## 4. Repeatable Smoke Test

From the Kinekt repo, run the smoke script inside the test image:

```powershell
$kinektRepo = (Get-Location).Path
docker run --rm `
  --mount "type=bind,source=$kinektRepo,target=/kinekt,readonly" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  --workdir /kinekt `
  --env PYTHONPATH=/kinekt/src `
  --entrypoint python `
  kinekt:test scripts/smoke_workspace.py /workspace --query "what does this project do?"
```

The smoke test runs:

- `kinekt doctor`
- `kinekt init`
- `kinekt ingest`
- `kinekt query`
- `kinekt git-context` when the target is a git repo

To remove the generated `.kinekt/` directory after testing:

```powershell
docker run --rm `
  --mount "type=bind,source=$kinektRepo,target=/kinekt,readonly" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  --workdir /kinekt `
  --env PYTHONPATH=/kinekt/src `
  --entrypoint python `
  kinekt:test scripts/smoke_workspace.py /workspace --cleanup
```

## 5. MCP Agent Test

Generate a reviewed Docker-backed client definition. Replace `codex` with `claude`, `gemini`, or `generic` for
another client:

```powershell
docker run --rm `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local agent-setup codex /workspace --docker --mount-source "$workspace"
```

The generated configuration launches this server command:

```powershell
docker run --rm -i `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local mcp-serve --allow-workspace /workspace
```

Then configure the MCP client using [MCP client setup](mcp-clients.md).

When one root is configured, Kinekt makes it the MCP default. Ask the agent to confirm it before querying:

```text
Use Kinekt's workspace_status tool to confirm the attached repository, then answer:
what files should I read first to understand this project?
```

The tool may omit `workspace`; its default resolves to `/workspace` in the generated Docker configuration. Passing
the path explicitly remains valid and is required when a server is intentionally configured with multiple roots:

```text
workspace = /workspace
```

## 6. What Good Looks Like

Kinekt is working well if:

- `ingest` scans expected code and markdown files.
- `query` returns real files from the target project.
- Results are relevant enough to guide the next file to inspect.
- `.kinekt/` is created locally but source files are not modified.
- `git status` in the target project only shows `.kinekt/` if it is not ignored.
- An MCP client can discover Kinekt tools and call `query_knowledge_base`.
- The MCP client's `workspace_status` result names the expected authorized root and reports the index database.

## 7. If Ingest Feels Slow

Kinekt skips common generated and dependency directories such as `node_modules/`, `dist/`, `build/`, `.firebase/`, `.next/`, `.venv/`, and cache folders. It also applies common root `.gitignore` patterns and skips individual text files over 1 MB.

If a real project still ingests too slowly, record the folder structure and file types involved. That is a signal Kinekt needs a better default exclude rule or a user-configurable ignore file.

## 8. What To Record

For each real-project test, record:

- Target repo name and stack
- Install method used
- Ingest stats: scanned, updated, skipped
- Three useful queries
- Whether the top results were useful
- Any confusing setup step
- Any security concern or unexpected file access

This feedback should drive the next retrieval, docs, and security improvements.
