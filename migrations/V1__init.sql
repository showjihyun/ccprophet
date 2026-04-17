-- V1: Initial schema for ccprophet
-- See docs/DATAMODELING.md for design rationale

CREATE TABLE IF NOT EXISTS sessions (
    session_id          VARCHAR PRIMARY KEY,
    project_slug        VARCHAR NOT NULL,
    worktree_path_hash  VARCHAR,
    model               VARCHAR NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    ended_at            TIMESTAMP,
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    compacted           BOOLEAN DEFAULT FALSE,
    compacted_at        TIMESTAMP,
    context_window_size INTEGER DEFAULT 200000,
    created_at          TIMESTAMP DEFAULT now(),
    schema_version      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    event_id       VARCHAR PRIMARY KEY,
    session_id     VARCHAR NOT NULL,
    event_type     VARCHAR NOT NULL,
    ts             TIMESTAMP NOT NULL,
    payload        JSON NOT NULL,
    raw_hash       VARCHAR NOT NULL,
    ingested_at    TIMESTAMP DEFAULT now(),
    ingested_via   VARCHAR NOT NULL DEFAULT 'hook'
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id    VARCHAR PRIMARY KEY,
    session_id      VARCHAR NOT NULL,
    parent_id       VARCHAR,
    tool_name       VARCHAR NOT NULL,
    input_hash      VARCHAR NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    latency_ms      INTEGER DEFAULT 0,
    success         BOOLEAN DEFAULT TRUE,
    error_type      VARCHAR,
    ts              TIMESTAMP NOT NULL,
    phase_id        VARCHAR
);

CREATE TABLE IF NOT EXISTS tool_defs_loaded (
    session_id    VARCHAR NOT NULL,
    tool_name     VARCHAR NOT NULL,
    tokens        INTEGER NOT NULL,
    source        VARCHAR NOT NULL,
    loaded_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (session_id, tool_name)
);

CREATE TABLE IF NOT EXISTS file_reads (
    file_read_id           VARCHAR PRIMARY KEY,
    session_id             VARCHAR NOT NULL,
    file_path_hash         VARCHAR NOT NULL,
    tokens                 INTEGER NOT NULL,
    referenced_in_output   BOOLEAN DEFAULT FALSE,
    referenced_at          TIMESTAMP,
    ts                     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS phases (
    phase_id            VARCHAR PRIMARY KEY,
    session_id          VARCHAR NOT NULL,
    phase_type          VARCHAR NOT NULL,
    start_ts            TIMESTAMP NOT NULL,
    end_ts              TIMESTAMP,
    input_tokens        INTEGER DEFAULT 0,
    output_tokens       INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0,
    detection_confidence FLOAT DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id             VARCHAR PRIMARY KEY,
    session_id              VARCHAR NOT NULL,
    predicted_at            TIMESTAMP NOT NULL,
    predicted_compact_at    TIMESTAMP,
    confidence              FLOAT,
    model_used              VARCHAR NOT NULL,
    input_token_rate        FLOAT,
    context_usage_at_pred   FLOAT
);

CREATE TABLE IF NOT EXISTS subagents (
    subagent_id         VARCHAR PRIMARY KEY,
    parent_session_id   VARCHAR NOT NULL,
    agent_type          VARCHAR,
    started_at          TIMESTAMP NOT NULL,
    ended_at            TIMESTAMP,
    context_tokens      INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prophet_self_metrics (
    metric_id    VARCHAR PRIMARY KEY,
    ts           TIMESTAMP NOT NULL,
    metric_name  VARCHAR NOT NULL,
    value        DOUBLE NOT NULL,
    labels       JSON
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version       INTEGER PRIMARY KEY,
    applied_at    TIMESTAMP NOT NULL,
    description   VARCHAR NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_slug);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON events(raw_hash);
CREATE INDEX IF NOT EXISTS idx_tc_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tc_tool_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tc_ts ON tool_calls(ts);
CREATE INDEX IF NOT EXISTS idx_tdl_source ON tool_defs_loaded(source);
CREATE INDEX IF NOT EXISTS idx_fr_session ON file_reads(session_id);
CREATE INDEX IF NOT EXISTS idx_fr_referenced ON file_reads(referenced_in_output);
CREATE INDEX IF NOT EXISTS idx_phases_session ON phases(session_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_forecasts_session ON forecasts(session_id, predicted_at);
CREATE INDEX IF NOT EXISTS idx_subagents_parent ON subagents(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_psm_name_ts ON prophet_self_metrics(metric_name, ts DESC);

-- Record migration
INSERT INTO schema_migrations(version, applied_at, description)
VALUES (1, now(), 'Initial schema');
