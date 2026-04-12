-- Add 'abandoned' as a valid quest status.
-- SQLite CHECK constraints can't be altered in-place, so we recreate the table.
-- FK enforcement is temporarily disabled for the table swap; re-enabled after.

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS quests_new;

CREATE TABLE quests_new (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'log'
                      CHECK (status IN ('log','active','blocked','done','abandoned')),
    frog         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at   TEXT,
    completed_at TEXT,
    abandoned_at TEXT
);

INSERT INTO quests_new (id, title, status, frog, created_at, started_at, completed_at)
    SELECT id, title, status, frog, created_at, started_at, completed_at FROM quests;

DROP TABLE quests;
ALTER TABLE quests_new RENAME TO quests;

CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status);

PRAGMA foreign_keys=ON;
