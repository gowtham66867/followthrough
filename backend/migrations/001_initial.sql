PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS opportunities (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, organizer TEXT NOT NULL,
 deadline_json TEXT, revision INTEGER NOT NULL DEFAULT 1,
 workflow TEXT NOT NULL DEFAULT 'discovered', completion_basis TEXT NOT NULL DEFAULT 'none',
 mode TEXT NOT NULL, created_at TEXT NOT NULL, application_ref TEXT
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
 received_at TEXT NOT NULL, body TEXT NOT NULL, content_hash TEXT NOT NULL,
 mode TEXT NOT NULL, external_url TEXT, opportunity_id TEXT REFERENCES opportunities(id)
);
CREATE TABLE IF NOT EXISTS requirements (
 id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
 requirement_key TEXT NOT NULL, title TEXT NOT NULL, required INTEGER NOT NULL,
 source_id TEXT NOT NULL REFERENCES messages(id), quote TEXT NOT NULL,
 span_start INTEGER NOT NULL, span_end INTEGER NOT NULL, revision INTEGER NOT NULL,
 UNIQUE(opportunity_id, requirement_key)
);
CREATE TABLE IF NOT EXISTS packages (
 opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id), revision INTEGER NOT NULL DEFAULT 1,
 answers_json TEXT NOT NULL DEFAULT '{}', approval_revision INTEGER, approval_hash TEXT
);
CREATE TABLE IF NOT EXISTS receipts (
 id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
 source_id TEXT NOT NULL REFERENCES messages(id), quote TEXT NOT NULL,
 application_ref TEXT, verdict TEXT NOT NULL, reason TEXT NOT NULL,
 reviewed INTEGER NOT NULL DEFAULT 0, UNIQUE(opportunity_id, source_id)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT REFERENCES opportunities(id),
 job_id TEXT, kind TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, command_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, mode TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', payload_json TEXT NOT NULL, result_json TEXT,
 error TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, provenance TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
 role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL
);
PRAGMA user_version = 1;
