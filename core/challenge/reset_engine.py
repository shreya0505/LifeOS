"""Rolling-window reset detection. Pure functions."""

from __future__ import annotations

from .config import (
    RESET_HARD_WINDOW,
    RESET_SOFT_WINDOW,
    RESET_HARD_STATES,
    RESET_SOFT_STATES,
    TRACKED_BUCKETS,
)


def check_hard(entries: list[dict]) -> bool:
    if len(entries) < RESET_HARD_WINDOW:
        return False
    window = entries[-RESET_HARD_WINDOW:]
    return all(e["state"] in RESET_HARD_STATES for e in window)


def check_soft(entries: list[dict]) -> bool:
    if len(entries) < RESET_SOFT_WINDOW:
        return False
    window = entries[-RESET_SOFT_WINDOW:]
    return all(e["state"] in RESET_SOFT_STATES for e in window)


def check_reset(
    task_entries: list[dict], bucket: str, new_state: str,
) -> tuple[bool, bool]:
    """task_entries = existing entries (chronological, oldest→newest). new_state = incoming.
    Returns (hard_triggered, soft_triggered)."""
    if bucket not in TRACKED_BUCKETS:
        return (False, False)
    combined = task_entries + [{"state": new_state}]
    return (check_hard(combined), check_soft(combined))


def evaluate_backfill(
    all_entries: list[dict], bucket: str,
) -> tuple[bool, bool, str | None]:
    """Scan all windows. Return (hard, soft, trigger_entry_id) for earliest trigger."""
    if bucket not in TRACKED_BUCKETS:
        return (False, False, None)
    for i in range(RESET_HARD_WINDOW, len(all_entries) + 1):
        window = all_entries[i - RESET_HARD_WINDOW:i]
        if all(e["state"] in RESET_HARD_STATES for e in window):
            return (True, False, window[-1].get("id"))
    for i in range(RESET_SOFT_WINDOW, len(all_entries) + 1):
        window = all_entries[i - RESET_SOFT_WINDOW:i]
        if all(e["state"] in RESET_SOFT_STATES for e in window):
            return (False, True, window[-1].get("id"))
    return (False, False, None)
