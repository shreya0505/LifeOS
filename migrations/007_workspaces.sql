-- Hard-boundary QuestLog workspaces.
-- Existing QuestLog data belongs to the seeded Work workspace.

UPDATE sync_runtime SET value = '1' WHERE key = 'suppress';

CREATE TABLE IF NOT EXISTS workspaces (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    icon               TEXT NOT NULL DEFAULT 'folder',
    color              TEXT NOT NULL DEFAULT 'blue',
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 1,
    sync_origin_device TEXT
);

INSERT OR IGNORE INTO workspaces
    (id, name, icon, color, sort_order, created_at, updated_at, sync_revision, sync_origin_device)
VALUES
    ('work', 'Work', 'folder', 'blue', 10,
     strftime('%Y-%m-%dT%H:%M:%SZ','now'),
     strftime('%Y-%m-%dT%H:%M:%fZ','now'),
     1,
     (SELECT value FROM sync_state WHERE key = 'device_name'));

ALTER TABLE quests ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'work';
ALTER TABLE pomo_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'work';
ALTER TABLE pomo_segments ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'work';

UPDATE quests SET workspace_id = 'work' WHERE workspace_id IS NULL OR workspace_id = '';
UPDATE pomo_sessions SET workspace_id = 'work' WHERE workspace_id IS NULL OR workspace_id = '';
UPDATE pomo_segments SET workspace_id = 'work' WHERE workspace_id IS NULL OR workspace_id = '';

CREATE INDEX IF NOT EXISTS idx_quests_workspace_status
    ON quests(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_pomo_sessions_workspace_started
    ON pomo_sessions(workspace_id, started_at);
CREATE INDEX IF NOT EXISTS idx_pomo_segments_workspace_session
    ON pomo_segments(workspace_id, session_id);

DROP TRIGGER IF EXISTS sync_artifact_keys_ai;
DROP TRIGGER IF EXISTS sync_artifact_keys_au;
DROP TRIGGER IF EXISTS sync_artifact_keys_ad;
DROP TRIGGER IF EXISTS sync_trophy_records_ai;
DROP TRIGGER IF EXISTS sync_trophy_records_au;
DROP TRIGGER IF EXISTS sync_trophy_records_ad;

ALTER TABLE artifact_keys RENAME TO artifact_keys_old;
CREATE TABLE artifact_keys (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL DEFAULT 'work',
    name               TEXT NOT NULL,
    icon               TEXT,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT,
    UNIQUE(workspace_id, name)
);

INSERT INTO artifact_keys
    (id, workspace_id, name, icon, sort_order, created_at, updated_at,
     deleted_at, sync_revision, sync_origin_device)
SELECT
    'work:' || name,
    'work',
    name,
    icon,
    sort_order,
    created_at,
    updated_at,
    deleted_at,
    sync_revision,
    sync_origin_device
FROM artifact_keys_old;

UPDATE sync_changes
   SET record_id = 'work:' || record_id
 WHERE table_name = 'artifact_keys'
   AND record_id NOT LIKE 'work:%';

DROP TABLE artifact_keys_old;

CREATE INDEX IF NOT EXISTS idx_artifact_keys_workspace_order
    ON artifact_keys(workspace_id, sort_order, name);

ALTER TABLE trophy_records RENAME TO trophy_records_old;
CREATE TABLE trophy_records (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL DEFAULT 'work',
    trophy_id          TEXT NOT NULL,
    best               TEXT NOT NULL,
    date               TEXT NOT NULL,
    detail             TEXT,
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT,
    UNIQUE(workspace_id, trophy_id)
);

INSERT INTO trophy_records
    (id, workspace_id, trophy_id, best, date, detail, updated_at,
     deleted_at, sync_revision, sync_origin_device)
SELECT
    'work:' || trophy_id,
    'work',
    trophy_id,
    best,
    date,
    detail,
    updated_at,
    deleted_at,
    sync_revision,
    sync_origin_device
FROM trophy_records_old;

UPDATE sync_changes
   SET record_id = 'work:' || record_id
 WHERE table_name = 'trophy_records'
   AND record_id NOT LIKE 'work:%';

DROP TABLE trophy_records_old;

CREATE INDEX IF NOT EXISTS idx_trophy_records_workspace
    ON trophy_records(workspace_id, trophy_id);

CREATE TRIGGER IF NOT EXISTS sync_workspaces_ai
AFTER INSERT ON workspaces
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE workspaces SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'workspaces', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM workspaces WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_workspaces_au
AFTER UPDATE ON workspaces
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE workspaces SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'workspaces', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM workspaces WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_workspaces_ad
AFTER DELETE ON workspaces
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('workspaces', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_ai
AFTER INSERT ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE artifact_keys SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'artifact_keys', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM artifact_keys WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_au
AFTER UPDATE ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE artifact_keys SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'artifact_keys', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM artifact_keys WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_artifact_keys_ad
AFTER DELETE ON artifact_keys
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('artifact_keys', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

CREATE TRIGGER IF NOT EXISTS sync_trophy_records_ai
AFTER INSERT ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE trophy_records SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'trophy_records', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM trophy_records WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_trophy_records_au
AFTER UPDATE ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE trophy_records SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'trophy_records', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM trophy_records WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS sync_trophy_records_ad
AFTER DELETE ON trophy_records
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('trophy_records', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

UPDATE sync_runtime SET value = '0' WHERE key = 'suppress';
