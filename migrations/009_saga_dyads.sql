-- Store optional second Saga emotions and their Plutchik dyad conclusion.

ALTER TABLE saga_entries ADD COLUMN secondary_emotion_family TEXT;
ALTER TABLE saga_entries ADD COLUMN secondary_emotion_label TEXT;
ALTER TABLE saga_entries ADD COLUMN dyad_label TEXT;
ALTER TABLE saga_entries ADD COLUMN dyad_type TEXT;

CREATE INDEX IF NOT EXISTS idx_saga_entries_dyad
    ON saga_entries(dyad_type, dyad_label, local_date);
