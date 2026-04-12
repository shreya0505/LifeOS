"""Centralized configuration for QuestLog.

All tuneable values live here so they can be adjusted in one place.
"""

from zoneinfo import ZoneInfo

# ── Timezone ─────────────────────────────────────────────────────────────────
# All timestamps are stored as UTC.  Display conversion uses this timezone.
USER_TZ = ZoneInfo("Asia/Kolkata")

# ── Pomodoro timer durations ─────────────────────────────────────────────────
POMO_CONFIG = {
    "work_secs":           25 * 60,
    "short_break_secs":     5 * 60,
    "extended_break_secs": 10 * 60,
    "long_break_secs":     30 * 60,
    "laps_before_long":    4,
}

# ── Quest state machine ─────────────────────────────────────────────────────
# Maps each transition verb to the set of statuses it may originate from.
VALID_SOURCES: dict[str, set[str]] = {
    "start":   {"log", "blocked"},
    "block":   {"log", "active"},
    "done":    {"active", "blocked"},
    "abandon": {"log", "active", "blocked"},
}
