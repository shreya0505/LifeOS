-- Saga mood meter migration.
-- Test data is intentionally discarded while replacing Plutchik columns.

DROP INDEX IF EXISTS idx_saga_entries_family;
DROP INDEX IF EXISTS idx_saga_entries_dyad;
DROP INDEX IF EXISTS idx_saga_entries_local_date;
DROP INDEX IF EXISTS idx_saga_entries_timestamp;

DROP TRIGGER IF EXISTS sync_saga_entries_ai;
DROP TRIGGER IF EXISTS sync_saga_entries_au;
DROP TRIGGER IF EXISTS sync_saga_entries_ad;

CREATE TABLE saga_entries_new (
    id                 TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,
    local_date         TEXT NOT NULL,
    energy             INTEGER NOT NULL CHECK (energy BETWEEN -5 AND 5 AND energy != 0),
    pleasantness       INTEGER NOT NULL CHECK (pleasantness BETWEEN -5 AND 5 AND pleasantness != 0),
    quadrant           TEXT NOT NULL CHECK (quadrant IN ('yellow','red','green','blue')),
    mood_word          TEXT NOT NULL,
    note               TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT
);

DROP TABLE saga_entries;
ALTER TABLE saga_entries_new RENAME TO saga_entries;

CREATE INDEX idx_saga_entries_local_date
    ON saga_entries(local_date, timestamp);
CREATE INDEX idx_saga_entries_timestamp
    ON saga_entries(timestamp);
CREATE INDEX idx_saga_entries_quadrant
    ON saga_entries(quadrant, local_date);

CREATE TRIGGER IF NOT EXISTS sync_saga_entries_ai
AFTER INSERT ON saga_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE saga_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'saga_entries', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device FROM saga_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_saga_entries_au
AFTER UPDATE ON saga_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE saga_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'saga_entries', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device FROM saga_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_saga_entries_ad
AFTER DELETE ON saga_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('saga_entries', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1, (SELECT value FROM sync_state WHERE key = 'device_name'));
END;
