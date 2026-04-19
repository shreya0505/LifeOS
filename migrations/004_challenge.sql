-- ── Hard 90 Challenge ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS challenges (
    id                 TEXT PRIMARY KEY,
    era_name           TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','completed','reset')),
    start_date         TEXT NOT NULL,
    current_level      INTEGER NOT NULL DEFAULT 0,
    current_level_name TEXT,
    midweek_adjective  TEXT,
    days_elapsed       INTEGER NOT NULL DEFAULT 0,
    days_remaining     INTEGER NOT NULL DEFAULT 90,
    peak_level         INTEGER NOT NULL DEFAULT 0,
    is_completed       INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);


CREATE TABLE IF NOT EXISTS challenge_tasks (
    id           TEXT PRIMARY KEY,
    challenge_id TEXT NOT NULL REFERENCES challenges(id),
    name         TEXT NOT NULL,
    bucket       TEXT NOT NULL
                      CHECK (bucket IN ('anchor','improver','enricher')),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(challenge_id, name)
);

CREATE INDEX IF NOT EXISTS idx_challenge_tasks_challenge ON challenge_tasks(challenge_id);


CREATE TABLE IF NOT EXISTS challenge_entries (
    id                   TEXT PRIMARY KEY,
    task_id              TEXT NOT NULL REFERENCES challenge_tasks(id),
    challenge_id         TEXT NOT NULL REFERENCES challenges(id),
    log_date             TEXT NOT NULL,
    state                TEXT NOT NULL CHECK (state IN (
                             'NOT_DONE','STARTED','PARTIAL',
                             'COMPLETED_UNSATISFACTORY','COMPLETED_SATISFACTORY'
                         )),
    notes                TEXT,
    hard_fail_triggered  INTEGER NOT NULL DEFAULT 0,
    soft_fail_triggered  INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(task_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_challenge_entries_task ON challenge_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_challenge_entries_challenge ON challenge_entries(challenge_id);
CREATE INDEX IF NOT EXISTS idx_challenge_entries_log_date ON challenge_entries(log_date);


CREATE TABLE IF NOT EXISTS challenge_eras (
    id                     TEXT PRIMARY KEY,
    era_name               TEXT NOT NULL,
    start_date             TEXT NOT NULL,
    end_date               TEXT NOT NULL,
    duration_days          INTEGER NOT NULL,
    peak_level             INTEGER NOT NULL,
    reset_cause            TEXT NOT NULL,
    reset_trigger_task_id  TEXT,
    summary_prose          TEXT,
    created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_challenge_eras_created ON challenge_eras(created_at);
