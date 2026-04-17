-- V5: Roll-up session_summary table for DATAMODELING §6.2 / PRD NFR-6.
-- Stores aggregate-only view of old sessions; source hot-table rows can be
-- pruned after summary + optional Parquet archive.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS session_summary (
    session_id              VARCHAR PRIMARY KEY,
    project_slug            VARCHAR NOT NULL,
    model                   VARCHAR NOT NULL,
    started_at              TIMESTAMP NOT NULL,
    ended_at                TIMESTAMP,
    total_input_tokens      INTEGER DEFAULT 0,
    total_output_tokens     INTEGER DEFAULT 0,
    total_cache_creation_tokens INTEGER DEFAULT 0,
    total_cache_read_tokens INTEGER DEFAULT 0,
    compacted               BOOLEAN DEFAULT FALSE,
    tool_call_count         INTEGER DEFAULT 0,
    unique_tools_used       INTEGER DEFAULT 0,
    loaded_tool_def_tokens  INTEGER DEFAULT 0,
    bloat_tokens            INTEGER DEFAULT 0,
    bloat_ratio             DOUBLE DEFAULT 0.0,
    file_read_count         INTEGER DEFAULT 0,
    phase_count             INTEGER DEFAULT 0,
    summarized_at           TIMESTAMP NOT NULL,
    source_rows_deleted     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_session_summary_started ON session_summary(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_summary_project ON session_summary(project_slug);

INSERT INTO schema_migrations(version, applied_at, description)
VALUES (5, now(), 'Add session_summary rollup table');

COMMIT;
