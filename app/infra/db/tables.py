"""SQLite schema definitions for auditable processing state."""

from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processing_runs (
    process_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    final_action TEXT,
    review_required INTEGER NOT NULL DEFAULT 0,
    decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id TEXT NOT NULL UNIQUE,
    message_id TEXT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    plain_text_body TEXT,
    attachment_count INTEGER NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS parsed_documents (
    process_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    extracted_tables TEXT NOT NULL DEFAULT '[]',
    parse_warnings TEXT NOT NULL DEFAULT '[]',
    confidence_hint REAL,
    PRIMARY KEY (process_id, document_id),
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extracted_contracts (
    process_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    vendor_name TEXT,
    contract_type TEXT,
    payment_terms TEXT,
    liability_clause TEXT,
    termination_clause TEXT,
    renewal_clause TEXT,
    governing_law TEXT,
    data_usage_clause TEXT,
    key_missing_fields TEXT NOT NULL DEFAULT '[]',
    extraction_confidence REAL NOT NULL,
    PRIMARY KEY (process_id, document_id),
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS retrieved_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    source TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    clause_type TEXT,
    score REAL NOT NULL,
    content_excerpt TEXT,
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS classifications (
    process_id TEXT PRIMARY KEY,
    risk_level TEXT NOT NULL,
    policy_conflicts TEXT NOT NULL DEFAULT '[]',
    recommended_action TEXT NOT NULL,
    rationale TEXT NOT NULL,
    clause_evaluations TEXT NOT NULL DEFAULT '{}',
    final_confidence REAL NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_evaluations (
    process_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,
    final_action TEXT,
    review_required INTEGER NOT NULL DEFAULT 0,
    decision_reason TEXT,
    errors TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT,
    policy_conflicts TEXT NOT NULL DEFAULT '[]',
    recommended_action TEXT,
    rationale TEXT,
    clause_evaluations TEXT NOT NULL DEFAULT '{}',
    final_confidence REAL,
    PRIMARY KEY (process_id, document_id),
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id TEXT NOT NULL,
    review_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processing_runs(process_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attachments_process_id ON attachments(process_id);
CREATE INDEX IF NOT EXISTS idx_retrieved_contexts_process_id ON retrieved_contexts(process_id);
CREATE INDEX IF NOT EXISTS idx_document_evaluations_process_id ON document_evaluations(process_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    """Create all persistence tables if they do not already exist."""
    connection.executescript(SCHEMA_SQL)
    _ensure_column(
        connection,
        table_name="classifications",
        column_name="clause_evaluations",
        definition="TEXT NOT NULL DEFAULT '{}'",
    )
    _ensure_column(
        connection,
        table_name="document_evaluations",
        column_name="clause_evaluations",
        definition="TEXT NOT NULL DEFAULT '{}'",
    )
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
