-- ── Quests ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quests (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'log'
                      CHECK (status IN ('log','active','blocked','done')),
    frog         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at   TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status);


-- ── Pomo Sessions ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pomo_sessions (
    id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    quest_id             TEXT NOT NULL REFERENCES quests(id),
    quest_title          TEXT NOT NULL,
    started_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    ended_at             TEXT,
    actual_pomos         INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running','completed','stopped')),
    streak_peak          INTEGER NOT NULL DEFAULT 0,
    total_interruptions  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_quest ON pomo_sessions(quest_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON pomo_sessions(started_at);


-- ── Pomo Segments ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pomo_segments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES pomo_sessions(id),
    type                 TEXT NOT NULL CHECK (type IN ('work','short_break','long_break')),
    lap                  INTEGER NOT NULL,
    cycle                INTEGER NOT NULL DEFAULT 0,
    completed            INTEGER NOT NULL DEFAULT 0,
    interruptions        INTEGER NOT NULL DEFAULT 0,
    started_at           TEXT NOT NULL,
    ended_at             TEXT NOT NULL,
    charge               TEXT,
    deed                 TEXT,
    break_size           TEXT,
    interruption_reason  TEXT,
    early_completion     INTEGER NOT NULL DEFAULT 0,
    forge_type           TEXT CHECK (forge_type IS NULL
                                    OR forge_type IN ('hollow','berserker'))
);

CREATE INDEX IF NOT EXISTS idx_segments_session ON pomo_segments(session_id);
CREATE INDEX IF NOT EXISTS idx_segments_started ON pomo_segments(started_at);
CREATE INDEX IF NOT EXISTS idx_segments_type    ON pomo_segments(type, completed);


-- ── Trophy Records (Personal Records) ────────────────────────────
CREATE TABLE IF NOT EXISTS trophy_records (
    trophy_id  TEXT PRIMARY KEY,
    best       TEXT NOT NULL,
    date       TEXT NOT NULL,
    detail     TEXT
);


-- ── Migration Tracking ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS _migrations (
    id         INTEGER PRIMARY KEY,
    filename   TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
