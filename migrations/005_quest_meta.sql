-- Add priority, project, labels, artifacts to quests.
-- Labels stored as JSON array (e.g. '["bug","urgent"]').
-- Artifacts stored as JSON object (e.g. '{"MR":"!1234","Ticket":"JIRA-42"}').
-- Filter by label is done in Python via set-subset; join-table upgrade available if cardinality grows.

ALTER TABLE quests ADD COLUMN priority INTEGER NOT NULL DEFAULT 4
    CHECK (priority BETWEEN 0 AND 4);
ALTER TABLE quests ADD COLUMN project   TEXT;
ALTER TABLE quests ADD COLUMN labels    TEXT NOT NULL DEFAULT '[]';
ALTER TABLE quests ADD COLUMN artifacts TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_quests_priority ON quests(priority);
CREATE INDEX IF NOT EXISTS idx_quests_project  ON quests(project);

-- Artifact key registry — user-defined dropdown vocabulary for artifact keys.
-- Deleting a key here does NOT strip existing quest artifact values.
CREATE TABLE IF NOT EXISTS artifact_keys (
    name        TEXT PRIMARY KEY,
    icon        TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

INSERT OR IGNORE INTO artifact_keys (name, icon, sort_order) VALUES
    ('MR',     'git-pull-request', 10),
    ('Ticket', 'tag',               20),
    ('Doc',    'file-text',         30),
    ('Slack',  'message-circle',    40);
