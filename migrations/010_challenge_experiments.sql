-- Tiny Experiments for Hard 90.

CREATE TABLE IF NOT EXISTS challenge_experiments (
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

CREATE INDEX IF NOT EXISTS idx_challenge_experiments_challenge
    ON challenge_experiments(challenge_id, status);
CREATE INDEX IF NOT EXISTS idx_challenge_experiments_status
    ON challenge_experiments(status, created_at);

CREATE TABLE IF NOT EXISTS challenge_experiment_entries (
    id                 TEXT PRIMARY KEY,
    experiment_id      TEXT NOT NULL REFERENCES challenge_experiments(id),
    challenge_id       TEXT NOT NULL REFERENCES challenges(id),
    log_date           TEXT NOT NULL,
    state              TEXT NOT NULL CHECK (state IN (
                           'NOT_DONE','STARTED','PARTIAL',
                           'COMPLETED_UNSATISFACTORY','COMPLETED_SATISFACTORY'
                       )),
    notes              TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at         TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    deleted_at         TEXT,
    sync_revision      INTEGER NOT NULL DEFAULT 0,
    sync_origin_device TEXT,
    UNIQUE(experiment_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_challenge_experiment_entries_experiment
    ON challenge_experiment_entries(experiment_id, log_date);
CREATE INDEX IF NOT EXISTS idx_challenge_experiment_entries_challenge
    ON challenge_experiment_entries(challenge_id, log_date);

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
