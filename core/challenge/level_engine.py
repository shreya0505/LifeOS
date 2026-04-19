"""Level / tier computation."""

from __future__ import annotations

from .config import MAIN_LEVEL_NAMES, MID_WEEK_DAY_OFFSET, CHALLENGE_LENGTH_DAYS


def _week_and_day(days_elapsed: int) -> tuple[int, int]:
    days = min(days_elapsed, CHALLENGE_LENGTH_DAYS)
    return (days // 7, days % 7)


def compute_level(
    days_elapsed: int, midweek_adjective: str,
) -> tuple[int, str, bool]:
    """Returns (level_id, level_name, is_main).
    level_id: monotonic int combining week + midweek tier (0..26)."""
    if days_elapsed >= CHALLENGE_LENGTH_DAYS:
        return (26, MAIN_LEVEL_NAMES[-1], True)

    week, day_in_week = _week_and_day(days_elapsed)
    week = min(week, len(MAIN_LEVEL_NAMES) - 1)

    if day_in_week < MID_WEEK_DAY_OFFSET:
        # Main tier for this week
        level_id = week * 2
        return (level_id, MAIN_LEVEL_NAMES[week], True)
    else:
        # Mid-week tier: adjective + next main name
        next_week = min(week + 1, len(MAIN_LEVEL_NAMES) - 1)
        level_id = week * 2 + 1
        name = f"{midweek_adjective} {MAIN_LEVEL_NAMES[next_week]}"
        return (level_id, name, False)


def should_promote_main(days_elapsed: int) -> bool:
    if days_elapsed <= 0:
        return False
    _, day_in_week = _week_and_day(days_elapsed)
    return day_in_week == 0


def should_promote_midweek(days_elapsed: int) -> bool:
    if days_elapsed <= 0:
        return False
    _, day_in_week = _week_and_day(days_elapsed)
    return day_in_week == MID_WEEK_DAY_OFFSET


def is_complete(days_elapsed: int) -> bool:
    return days_elapsed >= CHALLENGE_LENGTH_DAYS
