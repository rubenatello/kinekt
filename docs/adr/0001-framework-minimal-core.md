# ADR 0001: Keep The Core Free Of Agent Orchestration Frameworks

- Status: Accepted
- Date: 2026-07-21

## Context

The original design proposed LangGraph, SQLAlchemy, Tree-sitter, and ChromaDB as mandatory core technologies.
The validated public-beta value is narrower: safely index local workspaces and expose useful context to an agent
selected by the user.

## Decision

Use Python's standard library and SQLite for the default runtime. Keep MCP and Chroma optional. Do not add
LangGraph until Kinekt owns a workflow that requires explicit graph state, checkpointing, retries, or human
approval gates.

## Consequences

- Base installation and deterministic tests remain small and inspectable.
- Kinekt demonstrates framework judgment rather than framework accumulation.
- Language-aware parsing and future orchestration require isolated adapters when evidence justifies them.
