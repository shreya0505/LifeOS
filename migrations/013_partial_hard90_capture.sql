-- Allow notes-only day capture for Hard 90 tasks and Tiny Experiments.
-- A NULL state means "captured, not rated yet"; sealing and metrics should
-- continue to treat only non-NULL states as rated signals.

PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS sync_challenge_entries_ai;
DROP TRIGGER IF EXISTS sync_challenge_entries_au;
DROP TRIGGER IF EXISTS sync_challenge_entries_ad;

CREATE TABLE challenge_entries_new (
    id                   TEXT PRIMARY KEY,
    task_id              TEXT NOT NULL REFERENCES challenge_tasks(id),
    challenge_id         TEXT NOT NULL REFERENCES challenges(id),
    log_date             TEXT NOT NULL,
    state                TEXT CHECK (
                             state IS NULL OR state IN (
                                 'NOT_DONE','STARTED','PARTIAL',
                                 'COMPLETED_UNSATISFACTORY','COMPLETED_SATISFACTORY'
                             )
                         ),
    notes                TEXT,
    hard_fail_triggered  INTEGER NOT NULL DEFAULT 0,
    soft_fail_triggered  INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at           TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at           TEXT,
    sync_revision        INTEGER NOT NULL DEFAULT 0,
    sync_origin_device   TEXT,
    UNIQUE(task_id, log_date)
);

INSERT INTO challenge_entries_new (
    id, task_id, challenge_id, log_date, state, notes,
    hard_fail_triggered, soft_fail_triggered, created_at,
    updated_at, deleted_at, sync_revision, sync_origin_device
)
SELECT
    id, task_id, challenge_id, log_date, state, notes,
    hard_fail_triggered, soft_fail_triggered, created_at,
    updated_at, deleted_at, sync_revision, sync_origin_device
FROM challenge_entries;

DROP TABLE challenge_entries;
ALTER TABLE challenge_entries_new RENAME TO challenge_entries;

CREATE INDEX IF NOT EXISTS idx_challenge_entries_task ON challenge_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_challenge_entries_challenge ON challenge_entries(challenge_id);
CREATE INDEX IF NOT EXISTS idx_challenge_entries_log_date ON challenge_entries(log_date);

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

DROP TRIGGER IF EXISTS sync_challenge_experiment_entries_ai;
DROP TRIGGER IF EXISTS sync_challenge_experiment_entries_au;
DROP TRIGGER IF EXISTS sync_challenge_experiment_entries_ad;

CREATE TABLE challenge_experiment_entries_new (
    id                 TEXT PRIMARY KEY,
    experiment_id      TEXT NOT NULL REFERENCES challenge_experiments(id),
    challenge_id       TEXT NOT NULL REFERENCES challenges(id),
    log_date           TEXT NOT NULL,
    state              TEXT CHECK (
                           state IS NULL OR state IN (
                               'NOT_DONE','STARTED','PARTIAL',
                               'COMPLETED_UNSATISFACTORY','COMPLETED_SATISFACTORY'
                           )
                       ),
    notes              TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT,
    UNIQUE(experiment_id, log_date)
);

INSERT INTO challenge_experiment_entries_new (
    id, experiment_id, challenge_id, log_date, state, notes, created_at,
    updated_at, deleted_at, sync_revision, sync_origin_device
)
SELECT
    id, experiment_id, challenge_id, log_date, state, notes, created_at,
    updated_at, deleted_at, sync_revision, sync_origin_device
FROM challenge_experiment_entries;

DROP TABLE challenge_experiment_entries;
ALTER TABLE challenge_experiment_entries_new RENAME TO challenge_experiment_entries;

CREATE INDEX IF NOT EXISTS idx_challenge_experiment_entries_experiment
    ON challenge_experiment_entries(experiment_id, log_date);
CREATE INDEX IF NOT EXISTS idx_challenge_experiment_entries_challenge
    ON challenge_experiment_entries(challenge_id, log_date);

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiment_entries_ai
AFTER INSERT ON challenge_experiment_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    UPDATE challenge_experiment_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = CASE WHEN NEW.sync_revision <= 0 THEN 1 ELSE NEW.sync_revision END,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_experiment_entries', NEW.id, 'INSERT', 0, sync_revision, sync_origin_device
      FROM challenge_experiment_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiment_entries_au
AFTER UPDATE ON challenge_experiment_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1' AND NEW.sync_revision = OLD.sync_revision
BEGIN
    UPDATE challenge_experiment_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_revision = OLD.sync_revision + 1,
        sync_origin_device = (SELECT value FROM sync_state WHERE key = 'device_name')
    WHERE id = NEW.id;
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    SELECT 'challenge_experiment_entries', NEW.id, 'UPDATE', OLD.sync_revision, sync_revision, sync_origin_device
      FROM challenge_experiment_entries WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS sync_challenge_experiment_entries_ad
AFTER DELETE ON challenge_experiment_entries
WHEN (SELECT value FROM sync_runtime WHERE key = 'suppress') != '1'
BEGIN
    INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device)
    VALUES ('challenge_experiment_entries', OLD.id, 'DELETE', OLD.sync_revision, OLD.sync_revision + 1,
            (SELECT value FROM sync_state WHERE key = 'device_name'));
END;

PRAGMA foreign_keys = ON;
