-- New private SQLite state. Apply explicitly with tools/reminder_worker.py --init-state.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS accounts(
 account_hash TEXT PRIMARY KEY,password_hash TEXT NOT NULL,
 study TEXT NOT NULL,member TEXT NOT NULL UNIQUE,
 starts TEXT,ends TEXT,active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
 UNIQUE(study,member));
CREATE TABLE IF NOT EXISTS friends(line_user TEXT PRIMARY KEY,active INTEGER NOT NULL,event_ms INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS bindings(
 line_user TEXT PRIMARY KEY,account_hash TEXT NOT NULL UNIQUE REFERENCES accounts(account_hash),
 bound_at TEXT NOT NULL,reminder_start TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,processed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(bucket TEXT NOT NULL,at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_bucket ON attempts(bucket,at);
CREATE TABLE IF NOT EXISTS outbox(
 job_key TEXT PRIMARY KEY,kind TEXT NOT NULL,study TEXT,member TEXT,target_date TEXT,slot TEXT,
 line_user TEXT NOT NULL,due_at TEXT NOT NULL,retry_key TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
 retry_at TEXT,processed_at TEXT,request_id TEXT,error_code TEXT,
 UNIQUE(study,member,target_date,slot));
COMMIT;
