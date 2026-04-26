"""Hard 90 Challenge — constants and tuneables."""

from __future__ import annotations

# ── State machine ───────────────────────────────────────────────────────────
STATES = [
    "NOT_DONE",
    "STARTED",
    "PARTIAL",
    "COMPLETED_UNSATISFACTORY",
    "COMPLETED_SATISFACTORY",
]

STATE_RANK = {
    "NOT_DONE": 1,
    "STARTED": 2,
    "PARTIAL": 3,
    "COMPLETED_UNSATISFACTORY": 4,
    "COMPLETED_SATISFACTORY": 5,
}

STATE_ICONS = {
    "NOT_DONE": "✗",
    "STARTED": "⋯",
    "PARTIAL": "–",
    "COMPLETED_UNSATISFACTORY": "✓−",
    "COMPLETED_SATISFACTORY": "✓",
}

STATE_LABELS = {
    "NOT_DONE": "Not Done",
    "STARTED": "Started",
    "PARTIAL": "Partial",
    "COMPLETED_UNSATISFACTORY": "Completed (unsatisfactory)",
    "COMPLETED_SATISFACTORY": "Completed",
}

STATE_SHORT = {
    "NOT_DONE": "MISSED",
    "STARTED": "STARTED",
    "PARTIAL": "PARTIAL",
    "COMPLETED_UNSATISFACTORY": "SUB-PAR",
    "COMPLETED_SATISFACTORY": "DONE",
}

BUCKETS = ["anchor", "improver", "enricher"]

BUCKET_LABELS = {
    "anchor": "Anchors",
    "improver": "Improvers",
    "enricher": "Enrichers",
}

BUCKET_DESCRIPTIONS = {
    "anchor": "Non-negotiable. Daily. Core to survival.",
    "improver": "Growth. Discipline. Elevation.",
    "enricher": "Optional. Engagement without penalty.",
}

# ── Reset rules ─────────────────────────────────────────────────────────────
RESET_HARD_WINDOW = 3          # last N entries
RESET_SOFT_WINDOW = 7
RESET_SOFT_STATES = {"NOT_DONE", "STARTED"}  # soft streak set
RESET_HARD_STATES = {"NOT_DONE"}             # hard streak set

TRACKED_BUCKETS = {"anchor", "improver"}     # enrichers never trigger reset

# ── Tiny Experiments ────────────────────────────────────────────────────────
EXPERIMENT_TIMEFRAME_DAYS = {
    "day": 1,
    "weekend": 2,
    "week": 7,
    "month": 30,
}

EXPERIMENT_TIMEFRAME_LABELS = {
    "day": "Day",
    "weekend": "Weekend",
    "week": "Week",
    "month": "Month",
}

EXPERIMENT_STATUSES = {"draft", "running", "judged", "abandoned"}

EXPERIMENT_VERDICTS = {
    "success": "Breakthrough",
    "partial_success": "Partial Discovery",
    "failed_process": "Protocol Failure",
    "failed_premise": "Premise Refuted",
}

# ── Challenge length ────────────────────────────────────────────────────────
CHALLENGE_LENGTH_DAYS = 90

# ── Levels (26 tiers: 13 main + 13 mid-week) ────────────────────────────────
# Main levels: stable IDs across eras; index = week_num (0..12)
# week_num = days_elapsed // 7  (day 0..6 → week 0; day 7..13 → week 1; ...)
MAIN_LEVEL_NAMES = [
    "Initiate",       # week 0, days 0..6
    "Acolyte",        # week 1
    "Wanderer",       # week 2
    "Sentinel",       # week 3
    "Guardian",       # week 4
    "Vanguard",       # week 5
    "Champion",       # week 6
    "Warlord",        # week 7
    "Ascendant",      # week 8
    "Sovereign",      # week 9
    "Ironclad",       # week 10
    "Forgeborn",      # week 11
    "Legendborn",     # week 12
    "Godbound",       # completion (week 13 = day 90)
]

# Adjectives for mid-week tier name: picked once per era
MID_WEEK_ADJECTIVES = [
    "Novice",
    "Apprentice",
    "Neophyte",
    "Disciple",
    "Recruit",
    "Aspirant",
    "Initiate-Prime",
    "Fledgling",
    "Probationer",
    "Cadet",
    "Pupil",
    "Squire",
    "Trainee",
    "Understudy",
    "Greenhorn",
]

MID_WEEK_DAY_OFFSET = 3   # day 3 of each week = mid-week promote

# ── Era names (High Progression / Strong RPG Tone Only) ─────────────────────
ERA_NAMES = [
    "Era of Sovereign Awakening",
    "The Ascendant Apex",
    "Cycle of Relentless Ascension",
    "The Path of Dominion",
    "Era of Unyielding Ascension",
    "The Sovereign Ascent",
    "Cycle of Limitless Ascension",
    "The Conqueror’s Ascension",
    "Era of Boundless Dominion",
    "The Apex Ascendant",

    "Cycle of Transcendent Ascension",
    "The Evolution Ascendant",
    "Era of Infinite Ascension",
    "The Supreme Ascension",
    "Cycle of Absolute Dominion",
    "The Apex Awakening",
    "Era of Commanding Sovereignty",
    "The Overlord’s Ascension",
    "Cycle of Unstoppable Ascension",
    "The Pinnacle Ascendant",

    "Era of Final Ascension",
    "The Eternal Ascendant",
    "Cycle of True Ascension",
    "The Ascension Prime",
    "Era of Total Sovereignty",
    "The Godform Ascension",
    "Cycle of Supreme Ascension",
    "The Zenith Ascendant",
    "Era of Absolute Dominion",
    "The Eternal Apex",
]
