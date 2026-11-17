-- Destructive: only for isolated verification or after restoring a full backup.
BEGIN IMMEDIATE;
DROP TABLE IF EXISTS binding_cancellations;
DROP TABLE IF EXISTS binding_history;
DROP TABLE IF EXISTS outbox;
DROP TABLE IF EXISTS attempts;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS bindings;
DROP TABLE IF EXISTS friends;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS schema_version;
COMMIT;
