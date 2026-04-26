-- Add 'abandoned' to challenge_experiments.status CHECK constraint.
-- Rebuilds the table because SQLite cannot ALTER a CHECK in place.

PRAGMA foreign_keys=OFF;

INSERT INTO sync_runtime(key, value) VALUES('suppress','1')
    ON CONFLICT(key) DO UPDATE SET value='1';

DROP TRIGGER IF EXISTS sync_challenge_experiments_ai;
DROP TRIGGER IF EXISTS sync_challenge_experiments_au;
DROP TRIGGER IF EXISTS sync_challenge_experiments_ad;

CREATE TABLE challenge_experiments_new (
    id                 TEXT PRIMARY KEY,
    challenge_id       TEXT NOT NULL REFERENCES challenges(id),
    action             TEXT NOT NULL,
    motivation         TEXT NOT NULL,
    timeframe          TEXT NOT NULL CHECK (timeframe IN ('day','weekend','week','month')),
    status             TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','running','judged','abandoned')),
    started_at         TEXT,
    ends_at            TEXT,
    verdict            TEXT CHECK (
                           verdict IS NULL OR verdict IN (
                               'success','partial_success',
                               'failed_process','failed_premise'
                           )
                       ),
    observation_notes  TEXT,
    conclusion_notes   TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT
);

INSERT INTO challenge_experiments_new
    (id, challenge_id, action, motivation, timeframe, status,
     started_at, ends_at, verdict, observation_notes, conclusion_notes,
     created_at, updated_at, deleted_at, sync_revision, sync_origin_device)
SELECT
    id, challenge_id, action, motivation, timeframe, status,
    started_at, ends_at, verdict, observation_notes, conclusion_notes,
    created_at, updated_at, deleted_at, sync_revision, sync_origin_device
FROM challenge_experiments;

DROP TABLE challenge_experiments;
ALTER TABLE challenge_experiments_new RENAME TO challenge_experiments;

CREATE INDEX IF NOT EXISTS idx_challenge_experiments_challenge
    ON challenge_experiments(challenge_id, status);
CREATE INDEX IF NOT EXISTS idx_challenge_experiments_status
    ON challenge_experiments(status, created_at);

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiments_ai
AFTER INSERT ON challenge_experiments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_experiments SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_experiments', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device
      FROM challenge_experiments WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiments_au
AFTER UPDATE ON challenge_experiments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_experiments SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_experiments', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device
      FROM challenge_experiments WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiments_ad
AFTER DELETE ON challenge_experiments
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_experiments', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1,
            (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

UPDATE sync_runtime SET value='0' WHERE key='suppress';

PRAGMA foreign_keys=ON;
