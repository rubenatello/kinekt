# MCP Client Validation

Kinekt separates protocol evidence from named-client evidence. A standard MCP handshake proves server
conformance; it does not prove that every desktop client was configured successfully on every operating system.

## Validation Matrix

| Client | Validation level | Result | Reproduce |
| --- | --- | --- | --- |
| MCP Python SDK | Automated initialize, `tools/list`, and default-root `workspace_status` call over stdio | Pass: seven expected tools with descriptions and configured root | `python scripts/check_mcp_protocol.py` |
| MCP Inspector 0.21.2 | Real CLI process against the non-root Docker image | Pass: all seven tools, descriptions, and schemas discovered | Command below |
| Codex CLI 0.144.1 | Ephemeral configuration parsing for Docker stdio transport | Pass; no user config modified | Command below |
| Claude Desktop | Configuration example reviewed; application unavailable in this environment | Manual validation pending | [mcp-clients.md](mcp-clients.md#claude-desktop) |
| Gemini CLI | Configuration example reviewed; executable unavailable in this environment | Manual validation pending | [mcp-clients.md](mcp-clients.md#gemini-cli) |
| Ollama wrappers | Server-independent because Ollama is not itself an MCP client | Wrapper-specific validation pending | [mcp-clients.md](mcp-clients.md#ollama-and-local-agents) |

Validation recorded on 2026-07-21. Re-run it after MCP SDK, Inspector, or tool-schema changes.

## MCP Inspector

The official Inspector CLI can launch the production container directly:

```bash
npx -y @modelcontextprotocol/inspector@0.21.2 --cli \
  docker run --rm -i kinekt:local \
  mcp-serve --allow-workspace /workspace \
  --method tools/list
```

This performs a real initialize and tool-discovery exchange. It does not expose host source code because the
validation command mounts no workspace.

## Codex Configuration Parsing Without Mutation

Codex accepts temporary `-c` overrides, allowing the server definition to be validated without writing the
user's configuration:

```powershell
codex mcp get kinekt `
  -c "mcp_servers.kinekt.command='docker'" `
  -c "mcp_servers.kinekt.args=['run','--rm','-i','kinekt:local','mcp-serve','--allow-workspace','/workspace']"
```

For an actual project, add a read-only bind mount and set the allowed path to that mounted workspace. Persistent
configuration remains an explicit user action.

## Required Manual Evidence

For each pending named client, record the client version, operating system, server configuration with private
paths redacted, discovered tool names, one successful `query_knowledge_base` call, and one rejected unauthorized
workspace call. Do not mark the client validated from configuration syntax alone.
