-- V2: Sellable MVP tables — Auto Fix, Session Optimizer, Cost Dashboard
-- See docs/DATAMODELING.md §4.11-§4.15 + §8.2

BEGIN TRANSACTION;

-- ─── 제품 A: Bloat Detector + Auto Fix ────────────────────────────────────
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id     VARCHAR PRIMARY KEY,
    captured_at     TIMESTAMP NOT NULL,
    reason          VARCHAR NOT NULL,
    triggered_by    VARCHAR,
    files_manifest  JSON NOT NULL,
    byte_size       INTEGER DEFAULT 0,
    restored_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_snapshot_captured ON snapshots(captured_at DESC);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id              VARCHAR PRIMARY KEY,
    session_id          VARCHAR NOT NULL,
    kind                VARCHAR NOT NULL,
    target              VARCHAR,
    est_savings_tokens  INTEGER DEFAULT 0,
    est_savings_usd     DOUBLE DEFAULT 0,
    confidence          FLOAT NOT NULL,
    rationale           VARCHAR NOT NULL,
    status              VARCHAR NOT NULL DEFAULT 'pending',
    snapshot_id         VARCHAR,
    provenance          VARCHAR,
    created_at          TIMESTAMP NOT NULL,
    applied_at          TIMESTAMP,
    dismissed_at        TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rec_session ON recommendations(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rec_status ON recommendations(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rec_kind ON recommendations(kind);

-- ─── 제품 B: Session Optimizer ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outcome_labels (
    session_id   VARCHAR PRIMARY KEY,
    label        VARCHAR NOT NULL,
    task_type    VARCHAR,
    source       VARCHAR NOT NULL,
    reason       VARCHAR,
    labeled_at   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcome_label ON outcome_labels(label, task_type);
CREATE INDEX IF NOT EXISTS idx_outcome_task ON outcome_labels(task_type);

CREATE TABLE IF NOT EXISTS subset_profiles (
    profile_id     VARCHAR PRIMARY KEY,
    name           VARCHAR NOT NULL UNIQUE,
    task_type      VARCHAR,
    content        JSON NOT NULL,
    derived_from   VARCHAR,
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_profile_task ON subset_profiles(task_type);

-- ─── 제품 C: Cost Dashboard ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_rates (
    rate_id                 VARCHAR PRIMARY KEY,
    model                   VARCHAR NOT NULL,
    input_per_mtok          DOUBLE NOT NULL,
    output_per_mtok         DOUBLE NOT NULL,
    cache_write_per_mtok    DOUBLE DEFAULT 0,
    cache_read_per_mtok     DOUBLE DEFAULT 0,
    currency                VARCHAR NOT NULL DEFAULT 'USD',
    effective_at            TIMESTAMP NOT NULL,
    source                  VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pricing_model_eff ON pricing_rates(model, effective_at DESC);

-- Seed 기본 요율 (bundled; user_override는 pricing.toml import 시 추가)
INSERT INTO pricing_rates VALUES
    ('seed-opus-4-7',   'claude-opus-4-7',   15.0, 75.0, 18.75, 1.50, 'USD', TIMESTAMP '2026-01-01 00:00:00', 'bundled'),
    ('seed-opus-4-6',   'claude-opus-4-6',   15.0, 75.0, 18.75, 1.50, 'USD', TIMESTAMP '2026-01-01 00:00:00', 'bundled'),
    ('seed-sonnet-4-6', 'claude-sonnet-4-6',  3.0, 15.0,  3.75, 0.30, 'USD', TIMESTAMP '2026-01-01 00:00:00', 'bundled'),
    ('seed-haiku-4-5',  'claude-haiku-4-5',   1.0,  5.0,  1.25, 0.10, 'USD', TIMESTAMP '2026-01-01 00:00:00', 'bundled');

INSERT INTO schema_migrations(version, applied_at, description)
VALUES (2, now(), 'Sellable MVP: recommendations/snapshots/outcomes/profiles/pricing');

COMMIT;
