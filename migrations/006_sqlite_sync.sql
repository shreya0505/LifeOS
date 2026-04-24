-- SQLite web sync metadata and local change journal.
-- This migration is intentionally SQL-only: TUI JSON storage is out of scope.

CREATE TABLE IF NOT EXISTS sync_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sync_runtime (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO sync_state (key, value) VALUES
    ('device_name', 'unknown-device'),
    ('last_pull_at', ''),
    ('last_push_at', ''),
    ('last_error', ''),
    ('applied_bootstrap', '0'),
    ('applied_bundles', '[]');

INSERT OR IGNORE INTO sync_runtime (key, value) VALUES
    ('suppress', '0');

CREATE TABLE IF NOT EXISTS sync_devices (
    name          TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sync_changes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name         TEXT NOT NULL,
    record_id          TEXT NOT NULL,
    op                 TEXT NOT NULL CHECK (op IN ('INSERT','UPDATE','DELETE')),
    base_revision      INTEGER NOT NULL DEFAULT 0,
    local_revision     INTEGER NOT NULL DEFAULT 0,
    origin_device      TEXT NOT NULL,
    row_data           TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sent_at            TEXT,
    remote_bundle_id   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_changes_unsent
    ON sync_changes(sent_at, id);
CREATE INDEX IF NOT EXISTS idx_sync_changes_record
    ON sync_changes(table_name, record_id, id);

CREATE TABLE IF NOT EXISTS sync_conflicts (
    id            TEXT PRIMARY KEY,
    table_name    TEXT NOT NULL,
    record_id     TEXT NOT NULL,
    local_row     TEXT,
    remote_row    TEXT,
    remote_change TEXT NOT NULL,
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open','resolved')),
    resolution    TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    resolved_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_conflicts_open
    ON sync_conflicts(status, created_at);

CREATE TABLE IF NOT EXISTS sync_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    action         TEXT NOT NULL,
    status         TEXT NOT NULL,
    message        TEXT,
    bundles_pulled INTEGER NOT NULL DEFAULT 0,
    changes_pushed INTEGER NOT NULL DEFAULT 0,
    conflicts      INTEGER NOT NULL DEFAULT 0,
    started_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at    TEXT
);

ALTER TABLE challenges ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE challenges ADD COLUMN deleted_at TEXT;
ALTER TABLE challenges ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE challenges ADD COLUMN sync_origin_device TEXT;

ALTER TABLE challenge_tasks ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE challenge_tasks ADD COLUMN deleted_at TEXT;
ALTER TABLE challenge_tasks ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE challenge_tasks ADD COLUMN sync_origin_device TEXT;

ALTER TABLE challenge_entries ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE challenge_entries ADD COLUMN deleted_at TEXT;
ALTER TABLE challenge_entries ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE challenge_entries ADD COLUMN sync_origin_device TEXT;

ALTER TABLE challenge_eras ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE challenge_eras ADD COLUMN deleted_at TEXT;
ALTER TABLE challenge_eras ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE challenge_eras ADD COLUMN sync_origin_device TEXT;

ALTER TABLE quests ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE quests ADD COLUMN deleted_at TEXT;
ALTER TABLE quests ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE quests ADD COLUMN sync_origin_device TEXT;

ALTER TABLE artifact_keys ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE artifact_keys ADD COLUMN deleted_at TEXT;
ALTER TABLE artifact_keys ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE artifact_keys ADD COLUMN sync_origin_device TEXT;

ALTER TABLE pomo_sessions ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE pomo_sessions ADD COLUMN deleted_at TEXT;
ALTER TABLE pomo_sessions ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pomo_sessions ADD COLUMN sync_origin_device TEXT;

ALTER TABLE pomo_segments ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE pomo_segments ADD COLUMN deleted_at TEXT;
ALTER TABLE pomo_segments ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pomo_segments ADD COLUMN sync_origin_device TEXT;

ALTER TABLE trophy_records ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE trophy_records ADD COLUMN deleted_at TEXT;
ALTER TABLE trophy_records ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trophy_records ADD COLUMN sync_origin_device TEXT;

UPDATE challenges
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE challenge_tasks
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE challenge_entries
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE challenge_eras
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE quests
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE artifact_keys
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), created_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE pomo_sessions
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), started_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE pomo_segments
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), ended_at),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));
UPDATE trophy_records
   SET updated_at = COALESCE(NULLIF(updated_at, '1970-01-01T00:00:00Z'), date),
       sync_revision = CASE WHEN sync_revision = 0 THEN 1 ELSE sync_revision END,
       sync_origin_device = COALESCE(sync_origin_device, (SELECT value FROM sync_state WHERE key = 'device_name'));

-- Trigger family: local writes bump row revision and append to sync_changes.

CREATE TRIGGER IF NOT EXISTS sync_challenges_ai
AFTER INSERT ON challenges
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenges SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenges', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM challenges WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenges_au
AFTER UPDATE ON challenges
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenges SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenges', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM challenges WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenges_ad
AFTER DELETE ON challenges
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenges', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_tasks_ai
AFTER INSERT ON challenge_tasks
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_tasks SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_tasks', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM challenge_tasks WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_tasks_au
AFTER UPDATE ON challenge_tasks
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_tasks SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_tasks', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM challenge_tasks WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_tasks_ad
AFTER DELETE ON challenge_tasks
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_tasks', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_entries_ai
AFTER INSERT ON challenge_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_entries', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM challenge_entries WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_entries_au
AFTER UPDATE ON challenge_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_entries', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM challenge_entries WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_entries_ad
AFTER DELETE ON challenge_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_entries', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_eras_ai
AFTER INSERT ON challenge_eras
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_eras SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_eras', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM challenge_eras WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_eras_au
AFTER UPDATE ON challenge_eras
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_eras SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_eras', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM challenge_eras WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_challenge_eras_ad
AFTER DELETE ON challenge_eras
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_eras', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_quests_ai
AFTER INSERT ON quests
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE quests SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'quests', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM quests WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_quests_au
AFTER UPDATE ON quests
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE quests SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'quests', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM quests WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_quests_ad
AFTER DELETE ON quests
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('quests', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_ai
AFTER INSERT ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE artifact_keys SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE name = NEW.name;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'artifact_keys', NEW.name, 'INSERT', 0, sync_revision, sync_origin_device FROM artifact_keys WHERE name = NEW.name;
END;
CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_au
AFTER UPDATE ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'artifact_keys', OLD.name, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE NEW.name != OLD.name;
    UPDATE artifact_keys SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE name = NEW.name;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'artifact_keys', NEW.name, CASE WHEN NEW.name = OLD.name THEN 'UPDATE' ELSE 'INSERT' END,
           CASE WHEN NEW.name = OLD.name THEN OLD.sync_revision ELSE 0 END,
           sync_revision, sync_origin_device FROM artifact_keys WHERE name = NEW.name;
END;
CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_ad
AFTER DELETE ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('artifact_keys', OLD.name, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_pomo_sessions_ai
AFTER INSERT ON pomo_sessions
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE pomo_sessions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'pomo_sessions', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM pomo_sessions WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_pomo_sessions_au
AFTER UPDATE ON pomo_sessions
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE pomo_sessions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'pomo_sessions', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM pomo_sessions WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_pomo_sessions_ad
AFTER DELETE ON pomo_sessions
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('pomo_sessions', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_pomo_segments_ai
AFTER INSERT ON pomo_segments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE pomo_segments SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'pomo_segments', CAST(NEW.id AS TEXT), 'INSERT', 0, sync_revision, sync_origin_device FROM pomo_segments WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_pomo_segments_au
AFTER UPDATE ON pomo_segments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE pomo_segments SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'pomo_segments', CAST(NEW.id AS TEXT), 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM pomo_segments WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_pomo_segments_ad
AFTER DELETE ON pomo_segments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('pomo_segments', CAST(OLD.id AS TEXT), 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_trophy_records_ai
AFTER INSERT ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE trophy_records SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE trophy_id = NEW.trophy_id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'trophy_records', NEW.trophy_id, 'INSERT', 0, sync_revision, sync_origin_device FROM trophy_records WHERE trophy_id = NEW.trophy_id;
END;
CREATE TRIGGER IF NOT EXISTS sync_trophy_records_au
AFTER UPDATE ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE trophy_records SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE trophy_id = NEW.trophy_id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'trophy_records', NEW.trophy_id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM trophy_records WHERE trophy_id = NEW.trophy_id;
END;
CREATE TRIGGER IF NOT EXISTS sync_trophy_records_ad
AFTER DELETE ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('trophy_records', OLD.trophy_id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;
