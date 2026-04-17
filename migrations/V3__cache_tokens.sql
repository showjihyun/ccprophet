-- V3: Separate cache tokens on sessions (accurate cost, matches Anthropic billing)

BEGIN TRANSACTION;

ALTER TABLE sessions ADD COLUMN total_cache_creation_tokens INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN total_cache_read_tokens INTEGER DEFAULT 0;

INSERT INTO schema_migrations(version, applied_at, description)
VALUES (3, now(), 'Split cache tokens on sessions');

COMMIT;
