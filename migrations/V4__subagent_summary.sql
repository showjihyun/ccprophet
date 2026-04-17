-- V4: Add returned_summary to subagents (aligns runtime schema with
-- docs/DATAMODELING.md §4.8, which has always specified the column).

BEGIN TRANSACTION;

ALTER TABLE subagents ADD COLUMN returned_summary VARCHAR;

INSERT INTO schema_migrations(version, applied_at, description)
VALUES (4, now(), 'Add returned_summary to subagents');

COMMIT;
