# Agent Connections

Kinekt connects to agents through MCP and through its own CLI.

## Recommended Public Beta Model

Kinekt should be treated as a context server:

```text
Developer workspace -> Kinekt index -> MCP tools -> Coding agent
```

The agent remains user-selected. Kinekt supplies local context.

## MCP Clients

For MCP-capable clients, run:

```bash
kinekt mcp-serve --allow-workspace /path/to/workspace
```

Then configure the client to launch that command as a stdio MCP server.

Supported public beta documentation covers:

- Claude Desktop
- Codex
- Gemini CLI
- Ollama-wrapper clients

See [MCP client setup](mcp-clients.md).

## Ollama

Ollama is not an MCP client by itself. It is a local model runtime.

Kinekt supports Ollama in two ways:

1. Kinekt can use Ollama for local embeddings.
2. Kinekt can use Ollama for local generation in `agent-turn`.

For a full Ollama-based coding agent experience, users need an MCP-aware client or wrapper that can call Kinekt's MCP tools while using Ollama-hosted models.

Kinekt does not auto-install Ollama, start services, or pull models.

## Clean User Experience Goals

Users should be able to:

1. Install Kinekt.
2. Open a repository in any editor terminal and run `kinekt attach`.
3. Confirm the detected root with `kinekt workspace-status`.
4. Run `kinekt attach --ingest` or `kinekt ingest`.
5. Run `kinekt query`.
6. Generate reviewed configuration with `kinekt agent-setup codex`, `claude`, or `gemini`.
7. Confirm the client sees `workspace_status` and the other Kinekt tools.

If any step fails, Kinekt should return a clear error or diagnostic next step.

For a practical end-to-end validation flow against a real repository, see [Test Kinekt On Another Project](test-another-project.md).
For automatic root detection, Docker path aliases, and agent-specific setup, see
[Workspace Detection And Agent Setup](workspace-attachment.md).
