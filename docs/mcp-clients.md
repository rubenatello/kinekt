# MCP Client Setup

Kinekt exposes local developer context through a stdio MCP server:

```bash
kinekt mcp-serve --allow-workspace /path/to/workspace
```

For new users, the recommended flow detects and confirms the current repository, indexes it, and renders the
client-specific configuration:

```bash
kinekt attach --ingest
kinekt agent-setup codex
```

Replace `codex` with `claude`, `gemini`, or `generic`. The generated configuration uses one exact workspace root
and is printed for review; Kinekt does not edit another application's settings.

When exactly one allowed root is supplied, Kinekt also makes it the MCP default. Clients can call
`workspace_status` without knowing whether the underlying path is a host path or Docker's `/workspace`.

MCP tools can only access the server working directory by default. Add one or more `--allow-workspace` arguments
for other workspace roots. Each allowed root includes its descendants.

Install Kinekt with MCP support before configuring a client:

```bash
python -m pip install "kinekt[mcp] @ git+https://github.com/rubenatello/kinekt.git"
```

For local development from a clone:

```bash
uv sync --locked --python 3.11 --extra mcp
uv run --locked kinekt mcp-serve --allow-workspace /path/to/workspace
```

If your MCP client cannot find `kinekt` on `PATH`, replace `"kinekt"` in the examples with the absolute path to the installed executable.

## Available Tools

Kinekt exposes these MCP tools:

| Tool | Purpose |
| --- | --- |
| `workspace_status` | Confirm the authorized root, git branch, attachment, and local index state. |
| `query_knowledge_base` | Search indexed code and markdown context for a workspace. |
| `get_git_context` | Read local git branch/status context for a repository. |
| `read_workspace_file` | Safely read a file scoped to a declared workspace root. |
| `session_start` | Create or reuse a local Kinekt session. |
| `session_history` | Read saved session messages. |
| `agent_turn` | Run a bounded stateful turn and return retrieval and session-summary provenance. |

## Portable Docker Server

After building `kinekt:local`, a client can launch the server without relying on a host Python environment:

```bash
docker run --rm -i \
  --env KINEKT_WORKSPACE_ROOT_ALIAS=/absolute/path/to/workspace \
  --mount type=bind,source=/absolute/path/to/workspace,target=/workspace \
  kinekt:local mcp-serve --allow-workspace /workspace
```

Use the full `docker` command and arguments as the client's stdio server configuration. The workspace mount is
writeable because `session_start` and `agent_turn` persist local state under `.kinekt/`; Kinekt's tools do not write
source files or git state. See [MCP client validation](client-validation.md) for automated protocol evidence and the
remaining manual-client matrix.

To generate that Docker command safely, use:

```bash
kinekt agent-setup codex --docker
```

When running `agent-setup` from inside the Kinekt container, also pass the host path with
`--mount-source /absolute/host/path`. See [Workspace detection and agent setup](workspace-attachment.md).

## Claude Desktop

Claude Desktop uses a JSON config with an `mcpServers` object. The official MCP docs recommend absolute paths for reliable local server startup.

macOS config location:

```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

Windows config location:

```powershell
$env:AppData\Claude\claude_desktop_config.json
```

Example:

```json
{
  "mcpServers": {
    "kinekt": {
      "command": "kinekt",
      "args": ["mcp-serve", "--allow-workspace", "/absolute/path/to/workspace"]
    }
  }
}
```

Completely quit and restart Claude Desktop after editing the config, then use its MCP server indicator to confirm
that Kinekt tools are listed.

Reference: https://modelcontextprotocol.io/docs/develop/connect-local-servers

## Codex

Codex uses `~/.codex/config.toml` or project-scoped `.codex/config.toml` files for MCP server configuration.

Example:

```toml
[mcp_servers.kinekt]
command = "kinekt"
args = ["mcp-serve", "--allow-workspace", "/absolute/path/to/workspace"]
startup_timeout_sec = 10
tool_timeout_sec = 60
```

You can also add the server with the Codex CLI:

```bash
codex mcp add kinekt -- kinekt mcp-serve --allow-workspace /absolute/path/to/workspace
```

Use `/mcp` in the Codex TUI to inspect loaded MCP servers.

Reference: https://learn.chatgpt.com/docs/extend/mcp

## Gemini CLI

Gemini CLI reads MCP servers from `settings.json`. You can configure this globally in `~/.gemini/settings.json` or per project in `.gemini/settings.json`.

Example:

```json
{
  "mcpServers": {
    "kinekt": {
      "command": "kinekt",
      "args": ["mcp-serve", "--allow-workspace", "/absolute/path/to/workspace"],
      "timeout": 30000,
      "trust": false
    }
  }
}
```

Use Gemini CLI MCP commands or `/mcp` features to confirm tool discovery.

`gemini mcp list` reports configured server connection status without requiring a model prompt.

Reference: https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html

## Ollama And Local Agents

Ollama is a local model runtime, not an MCP client by itself. Kinekt does not install Ollama, start Ollama, or pull Ollama models automatically.

There are two supported beta paths:

1. Use Kinekt's own local `agent-turn` command with Ollama-backed generation:

```bash
export KINEKT_GENERATION_BACKEND=ollama
export KINEKT_OLLAMA_GENERATE_URL=http://127.0.0.1:11434/api/generate
export KINEKT_OLLAMA_GENERATE_MODEL=llama3.1:8b
kinekt doctor /path/to/workspace
kinekt agent-turn "what should I inspect first?" --workspace /path/to/workspace
```

2. Use an MCP-aware client or wrapper that can call MCP tools while using Ollama-hosted models.

For local embeddings with Ollama:

```bash
export KINEKT_EMBEDDING_BACKEND=ollama
export KINEKT_OLLAMA_URL=http://127.0.0.1:11434/api/embeddings
export KINEKT_OLLAMA_MODEL=nomic-embed-text
kinekt doctor /path/to/workspace
```

Run the relevant `ollama pull <model>` commands yourself before expecting Ollama-backed behavior. Generation may
fall back to deterministic output. Embedding operations fail clearly when an explicitly configured Ollama backend
is unavailable so the persisted index cannot mix embedding providers or dimensions.

## Troubleshooting

Run:

```bash
kinekt doctor /path/to/workspace
```

Common fixes:

- Use an absolute path to `kinekt` if the client cannot resolve the command.
- Keep Kinekt as a stdio server for this beta; SSE and HTTP server modes are not implemented.
- Keep Ollama endpoints on loopback addresses such as `127.0.0.1`, `localhost`, or `::1`.
- Re-run `kinekt ingest /path/to/workspace` after changing project files.
