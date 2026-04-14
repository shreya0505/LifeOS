-- Add checklist column to quests table.
-- Stores a JSON array of {id, text, done} objects.
ALTER TABLE quests ADD COLUMN checklist TEXT NOT NULL DEFAULT '[]';
