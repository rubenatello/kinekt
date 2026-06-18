# MCP Client Setup

Kinekt exposes local developer context through a stdio MCP server:

```bash
kinekt mcp-serve
```

Install Kinekt with MCP support before configuring a client:

```bash
python -m pip install "kinekt[mcp] @ git+https://github.com/rubenatello/kinekt.git"
```

For local development from a clone:

```bash
python -m pip install -e ".[mcp]"
```

If your MCP client cannot find `kinekt` on `PATH`, replace `"kinekt"` in the examples with the absolute path to the installed executable.

## Available Tools

Kinekt exposes these MCP tools:

| Tool | Purpose |
| --- | --- |
| `query_knowledge_base` | Search indexed code and markdown context for a workspace. |
| `get_git_context` | Read local git branch/status context for a repository. |
| `read_workspace_file` | Safely read a file scoped to a declared workspace root. |
| `session_start` | Create or reuse a local Kinekt session. |
| `session_history` | Read saved session messages. |
| `agent_turn` | Run a stateful local Kinekt agent turn using indexed context. |

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
      "args": ["mcp-serve"]
    }
  }
}
```

Restart Claude Desktop after editing the config, then check Connectors to confirm that Kinekt tools are listed.

Reference: https://modelcontextprotocol.io/docs/develop/connect-local-servers

## Codex

Codex uses `~/.codex/config.toml` or project-scoped `.codex/config.toml` files for MCP server configuration.

Example:

```toml
[mcp_servers.kinekt]
command = "kinekt"
args = ["mcp-serve"]
startup_timeout_sec = 10
tool_timeout_sec = 60
```

You can also add the server with the Codex CLI:

```bash
codex mcp add kinekt -- kinekt mcp-serve
```

Use `/mcp` in the Codex TUI to inspect loaded MCP servers.

Reference: https://developers.openai.com/codex/mcp

## Gemini CLI

Gemini CLI reads MCP servers from `settings.json`. You can configure this globally in `~/.gemini/settings.json` or per project in `.gemini/settings.json`.

Example:

```json
{
  "mcpServers": {
    "kinekt": {
      "command": "kinekt",
      "args": ["mcp-serve"],
      "timeout": 30000,
      "trust": false
    }
  }
}
```

Use Gemini CLI MCP commands or `/mcp` features to confirm tool discovery.

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

Run the relevant `ollama pull <model>` commands yourself before expecting Ollama-backed behavior. Kinekt falls back to deterministic local behavior when Ollama is unavailable.

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
