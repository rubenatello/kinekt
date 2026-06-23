# Test Kinekt On Another Project

Use this guide to validate Kinekt against a real local repository such as `autocloud`.

The goal is to prove three things:

1. Kinekt is easy to install and run outside the Kinekt repo.
2. Kinekt can index another project without changing source files.
3. Kinekt returns context that would help an AI coding agent understand that project.

## 1. Install Kinekt Locally

From the Kinekt repo:

```powershell
python -m pip install -e ".[mcp]"
kinekt --help
```

If `kinekt` is not found after install, use:

```powershell
python -m kinekt.cli --help
```

## 2. Choose The Target Project

Set the path to the other repo:

```powershell
$workspace = "C:\Users\rcazarez\Projects\autocloud"
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

Run diagnostics:

```powershell
kinekt doctor $workspace
```

Initialize local storage:

```powershell
kinekt init $workspace
```

Index the target project:

```powershell
kinekt ingest $workspace
```

Ask broad project questions:

```powershell
kinekt query "what does this project do?" --workspace $workspace --limit 5
kinekt query "where is the main application entrypoint?" --workspace $workspace --limit 5
kinekt query "how is deployment or infrastructure configured?" --workspace $workspace --limit 5
```

Check git context:

```powershell
kinekt git-context $workspace
```

## 4. Repeatable Smoke Test

From the Kinekt repo, run:

```powershell
python scripts/smoke_workspace.py "C:\Users\rcazarez\Projects\autocloud" --query "what does this project do?"
```

The smoke test runs:

- `kinekt doctor`
- `kinekt init`
- `kinekt ingest`
- `kinekt query`
- `kinekt git-context` when the target is a git repo

To remove the generated `.kinekt/` directory after testing:

```powershell
python scripts/smoke_workspace.py "C:\Users\rcazarez\Projects\autocloud" --cleanup
```

## 5. MCP Agent Test

Start by confirming Kinekt is available to the client:

```powershell
kinekt mcp-serve
```

Then configure the MCP client using [MCP client setup](mcp-clients.md).

When asking the agent to use Kinekt, include the workspace path explicitly:

```text
Use Kinekt to inspect this workspace:
C:\Users\rcazarez\Projects\autocloud

Question: what files should I read first to understand this project?
```

The MCP tool call should pass:

```text
workspace = C:\Users\rcazarez\Projects\autocloud
```

## 6. What Good Looks Like

Kinekt is working well if:

- `ingest` scans expected code and markdown files.
- `query` returns real files from the target project.
- Results are relevant enough to guide the next file to inspect.
- `.kinekt/` is created locally but source files are not modified.
- `git status` in the target project only shows `.kinekt/` if it is not ignored.
- An MCP client can discover Kinekt tools and call `query_knowledge_base`.

## 7. If Ingest Feels Slow

Kinekt skips common generated and dependency directories such as `node_modules/`, `dist/`, `build/`, `.next/`, `.venv/`, and cache folders. It also skips individual text files over 1 MB.

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
