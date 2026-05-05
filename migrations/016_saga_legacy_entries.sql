-- Saga Legacy entries: reflective markdown notes with optional source links.

CREATE TABLE IF NOT EXISTS saga_legacy_entries (
    id                 TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,
    local_date         TEXT NOT NULL,
    source_url         TEXT,
    source_kind        TEXT NOT NULL DEFAULT 'none'
                       CHECK (source_kind IN ('none','youtube','image','article')),
    labels             TEXT NOT NULL DEFAULT '[]',
    markdown           TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT
);

CREATE INDEX IF NOT EXISTS idx_saga_legacy_entries_local_date
    ON saga_legacy_entries(local_date, timestamp);
CREATE INDEX IF NOT EXISTS idx_saga_legacy_entries_timestamp
    ON saga_legacy_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_saga_legacy_entries_source_kind
    ON saga_legacy_entries(source_kind, local_date);

CREATE TRIGGER IF NOT EXISTS sync_saga_legacy_entries_ai
AFTER INSERT ON saga_legacy_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE saga_legacy_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'saga_legacy_entries', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device
      FROM saga_legacy_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_saga_legacy_entries_au
AFTER UPDATE ON saga_legacy_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE saga_legacy_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'saga_legacy_entries', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device
      FROM saga_legacy_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_saga_legacy_entries_ad
AFTER DELETE ON saga_legacy_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('saga_legacy_entries', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1,
            (SELECT value FROM sync_state WHERE key = 'device_name'));
END;
