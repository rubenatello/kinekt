# kinekt

Kinekt is a local-first developer context engine designed to eliminate context-switching for software engineers. Developers treat their codebases, git commit logs, and markdown knowledge bases (like Obsidian or Notion exports) as fragmented data silos.

## Current implementation (MVP foundation)

This repository now includes a working local-first core with:

- Workspace ingestion for code and markdown files
- File hash registry to skip unchanged files
- Local SQLite persistence with the design document schema (`sessions`, `thread_messages`, `file_registry`, `developer_profile`)
- Local chunk storage and deterministic embedding fallback for semantic retrieval
- CLI commands for ingestion, querying, git context, and safe file reads

## Setup

```bash
python -m pip install -e .
```

For development (tests):

```bash
python -m pip install -e .[dev]
python -m pip install pytest
```

## Usage

Initialize local database:

```bash
kinekt init
```

Ingest a workspace:

```bash
kinekt ingest /path/to/workspace
```

Query the indexed context:

```bash
kinekt query "where is developer profile stored?" --limit 5
```

Show git context:

```bash
kinekt git-context /path/to/repo
```

Read a workspace file safely (path traversal protected):

```bash
kinekt read-file src/main.py --workspace /path/to/workspace --max-chars 2000
```

## Run tests

```bash
python -m pytest -q
```
