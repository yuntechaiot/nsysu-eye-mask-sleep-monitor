-- Explicit upgrade: preserve unknown outcomes across subsequent failed retries.
BEGIN IMMEDIATE;
ALTER TABLE outbox ADD COLUMN uncertainty INTEGER NOT NULL DEFAULT 0;
UPDATE outbox SET uncertainty=1 WHERE attempts>0 AND status<>'accepted';
INSERT INTO schema_version VALUES(2);
COMMIT;
