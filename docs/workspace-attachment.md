# Workspace Detection And Agent Setup

Kinekt can detect the repository opened in an editor terminal, show the exact root it found, require human
confirmation, optionally index it, and generate an MCP configuration for a coding agent. The detection core is
editor-neutral: VS Code, PyCharm, other editors, and a normal terminal all use the same workflow.

Kinekt does not run a background scanner when an editor opens. Detection starts only when the user runs a Kinekt
command, and a workspace is not attached until the user confirms it.

## Detection Rules

When no workspace argument is provided, Kinekt uses this order:

1. `KINEKT_WORKSPACE`, when explicitly set.
2. The current directory, normally supplied by the editor terminal.
3. The nearest Git root reported by a bounded read-only `git rev-parse` call.
4. The nearest recognized project marker: `.git`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`,
   `pom.xml`, `build.gradle`, `build.gradle.kts`, or `.idea`.

If no root can be established, Kinekt fails with guidance instead of authorizing an arbitrary directory. In a
nested repository, the nearest Git root wins. For a multi-root editor workspace, run the command from the desired
folder or pass its path explicitly.

## Native Five-Step Setup

Install Kinekt, open the target repository in an editor, and use its integrated terminal:

```powershell
cd C:\Projects\target-repo
kinekt attach
kinekt workspace-status
kinekt ingest
kinekt agent-setup codex
```

`attach` prints the detected root, branch, state path, and access boundary before asking for confirmation. Use the
single-command version when immediate indexing is desired:

```powershell
kinekt attach --ingest
```

For a non-interactive script, confirmation must be explicit:

```powershell
kinekt attach --yes --ingest --json
```

The confirmation is stored in `.kinekt/workspace.json`. Kinekt never adds itself to `.gitignore`; add this local
state directory yourself:

```gitignore
.kinekt/
```

After attachment, commands issued from nested folders automatically use the detected project root. An explicit
`--workspace` argument still wins when supplied.

State-writing commands such as automatic `ingest`, `init`, `reindex`, and session creation refuse an unconfirmed
auto-detected root. Passing an explicit workspace remains available for backward-compatible automation because
that path is itself an explicit user selection.

## Docker-First Setup

Build Kinekt once:

```powershell
docker build -t kinekt:local .
```

Choose the repository and attach it. The root alias records that the host path and `/workspace` refer to the same
confirmed repository; authorization inside the container remains restricted to `/workspace`.

```powershell
$workspace = "C:\Projects\target-repo"

docker run --rm -it `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local attach /workspace --ingest
```

Confirm the mounted project later without rescanning it:

```powershell
docker run --rm `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local workspace-status /workspace
```

Generate a Docker-backed agent configuration from the same image. `--mount-source` is needed because the
container cannot otherwise discover the host-side path it should put in a future `docker run` command.

```powershell
docker run --rm `
  --env "KINEKT_WORKSPACE_ROOT_ALIAS=$workspace" `
  --mount "type=bind,source=$workspace,target=/workspace" `
  kinekt:local agent-setup codex /workspace --docker --mount-source "$workspace"
```

Use `claude`, `gemini`, or `generic` instead of `codex` to render another client format. `agent-setup` prints a
configuration; it does not silently edit client settings.

Compose carries the same root alias automatically when `KINEKT_WORKSPACE` is absolute:

```powershell
$env:KINEKT_WORKSPACE = "C:\Projects\target-repo"
docker compose run --rm kinekt attach /workspace --ingest
docker compose run --rm kinekt workspace-status /workspace
docker compose run --rm kinekt agent-setup codex /workspace --docker --mount-source "$env:KINEKT_WORKSPACE"
```

## Connect Codex

Generate configuration:

```powershell
kinekt agent-setup codex
```

Save the rendered TOML in project `.codex/config.toml` or the global Codex `config.toml`. Start a new Codex
session and run `/mcp`. Kinekt should expose seven tools, including `workspace_status`, which lets the agent report
the exact authorized root and local index state before it begins an investigation.

Generated single-workspace configurations also make that root the MCP default, so the agent does not need to guess
or repeatedly supply a host-specific path. Multi-root servers continue to require an explicit workspace choice.

Codex also provides `codex mcp` commands for managing MCP servers. Kinekt prints configuration instead of invoking
those commands so the user remains in control of persistent client changes.

Reference: https://learn.chatgpt.com/docs/extend/mcp

## Connect Claude Desktop

Generate configuration:

```powershell
kinekt agent-setup claude
```

Merge the JSON into the `mcpServers` object in `claude_desktop_config.json`, completely quit Claude Desktop, and
restart it. On Windows the file is normally under `%APPDATA%\Claude\`; on macOS it is under
`~/Library/Application Support/Claude/`.

Reference: https://modelcontextprotocol.io/docs/develop/connect-local-servers

## Connect Gemini CLI

Generate configuration:

```powershell
kinekt agent-setup gemini
```

Merge the JSON into project `.gemini/settings.json` or the global Gemini `settings.json`. Kinekt leaves `trust`
set to `false`, preserving Gemini's tool confirmation flow. Start a new session and inspect MCP status; Gemini also
supports `gemini mcp list` for configured servers.

Reference: https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html

## Editor Behavior

No editor plugin is required for the first release:

- VS Code: open its integrated terminal in the workspace and run `kinekt attach`.
- PyCharm and other JetBrains IDEs: use the project terminal or an External Tool whose working directory is the
  project root.
- Other editors: launch Kinekt with the project root as the process working directory or set `KINEKT_WORKSPACE`.

An editor extension may later add a status bar and multi-root selector, but it should call this same detection and
confirmation layer rather than implementing a second trust model.

## Security Properties

- Detection is read-only and bounded.
- Confirmation is a CLI/user action; no MCP tool can authorize a workspace.
- `agent-setup` never writes another application's configuration.
- The generated MCP command grants one exact repository root by default.
- Docker receives one exact bind mount and authorizes only `/workspace`.
- Kinekt writes project state only under `.kinekt/`.
- Source reads, git inspection, limits, symlink rejection, and path containment continue to use the existing
  workspace safety boundary.

If a stored attachment is malformed or was created for a different path, `workspace-status` reports it as invalid
and `agent-setup` refuses to proceed until the user confirms the workspace again.
