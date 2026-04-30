-- Hard 90 holidays: skipped dates that do not count as challenge days.

CREATE TABLE IF NOT EXISTS challenge_holidays (
    id                 TEXT PRIMARY KEY,
    challenge_id       TEXT NOT NULL REFERENCES challenges(id),
    log_date           TEXT NOT NULL,
    reason             TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT,
    UNIQUE(challenge_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_challenge_holidays_challenge
    ON challenge_holidays(challenge_id, log_date);

CREATE TRIGGER IF NOT EXISTS sync_challenge_holidays_ai
AFTER INSERT ON challenge_holidays
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_holidays SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_holidays', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device
      FROM challenge_holidays WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_holidays_au
AFTER UPDATE ON challenge_holidays
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_holidays SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_holidays', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device
      FROM challenge_holidays WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_holidays_ad
AFTER DELETE ON challenge_holidays
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_holidays', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1,
            (SELECT value FROM sync_state WHERE key = 'device_name'));
END;
