from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS thread_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    role TEXT CHECK(role IN ('user', 'assistant', 'tool')),
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_registry (
    file_path TEXT PRIMARY KEY,
    file_type TEXT CHECK(file_type IN ('code', 'markdown')),
    last_modified_hash TEXT,
    last_indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS developer_profile (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Local fallback for vector search when ChromaDB is not configured.
CREATE TABLE IF NOT EXISTS code_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    construct_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    tags TEXT NOT NULL,
    heading_context TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_code_chunks_file_path ON code_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_notes_chunks_file_path ON notes_chunks(file_path);
"""
