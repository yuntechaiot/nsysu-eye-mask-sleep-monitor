-- Explicit upgrade: one-time, owner-scoped cancellation confirmations and audit.
BEGIN IMMEDIATE;
CREATE TABLE binding_cancellations(
 token_hash TEXT PRIMARY KEY,line_user TEXT NOT NULL,account_hash TEXT NOT NULL,
 bound_at TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
CREATE INDEX binding_cancellations_owner ON binding_cancellations(line_user);
CREATE TABLE binding_history(
 change_id TEXT PRIMARY KEY,line_user TEXT NOT NULL,account_hash TEXT NOT NULL,
 study TEXT NOT NULL,member TEXT NOT NULL,bound_at TEXT NOT NULL,
 reminder_start TEXT NOT NULL,cancelled_at TEXT NOT NULL);
INSERT INTO schema_version VALUES(3);
COMMIT;
