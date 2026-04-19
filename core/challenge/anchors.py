"""Anchor derivation for the History timeline.

Pure functions. Anchors are derived from existing tracked metrics —
no synthetic events. Used by web/challenge/routes.py history_page.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as _date, timedelta

from .config import (
    CHALLENGE_LENGTH_DAYS,
    MAIN_LEVEL_NAMES,
    RESET_HARD_WINDOW,
    RESET_SOFT_WINDOW,
    RESET_HARD_STATES,
    RESET_SOFT_STATES,
    STATE_RANK,
    TRACKED_BUCKETS,
)


FALSE_START_THRESHOLD = 3        # eras of ≤ N days = false start
ANCHOR_CAP = 8                   # density cap per era
PROMOTION_CLUSTER_MIN = 3        # ≥ N adjacent promotions cluster
PROMOTION_CLUSTER_WINDOW = 10    # within N days
STREAK_THRESHOLD = 4.5
STREAK_MIN_LENGTH = 3
PEAK_WINDOW = 7
SHORT_ERA_PEAK_FALLBACK = 14


def _iso(d) -> str:
    return d if isinstance(d, str) else d.isoformat()


def _day_to_date(start_date: str, day_num: int) -> str:
    """day_num is 1-indexed; day 1 = start_date."""
    start = _date.fromisoformat(start_date)
    return (start + timedelta(days=day_num - 1)).isoformat()


def _date_to_day(start_date: str, iso_date: str) -> int:
    start = _date.fromisoformat(start_date)
    d = _date.fromisoformat(iso_date)
    return (d - start).days + 1


def _entries_to_series_per_task(
    entries: list[dict], tasks: list[dict],
) -> dict[str, list[dict]]:
    """Group entries by task_id, chronological."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_task[e["task_id"]].append(e)
    for tid in by_task:
        by_task[tid].sort(key=lambda e: _iso(e["log_date"]))
    return by_task


def _daily_quality(
    entries: list[dict], tracked_ids: set[str],
) -> dict[str, float]:
    """date_iso → avg STATE_RANK across tracked tasks for that date."""
    by_date: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        if e["task_id"] not in tracked_ids:
            continue
        by_date[_iso(e["log_date"])].append(STATE_RANK.get(e["state"], 0))
    return {d: sum(v) / len(v) for d, v in by_date.items()}


# ── Individual anchor extractors ────────────────────────────────────────────

def _anchor_start(start_date: str) -> dict:
    return {
        "kind": "start",
        "day": 1,
        "date": start_date,
        "label": "START",
        "detail": None,
    }


def _anchor_collapse(
    end_date: str, duration_days: int, reset_cause: str,
    trigger_task_name: str | None,
) -> dict:
    if reset_cause == "completed":
        label = "COMPLETED"
        detail = f"Day {duration_days}. Unbroken."
    elif reset_cause == "forfeit":
        label = "RELINQUISHED"
        detail = f"Day {duration_days}."
    else:
        label = "COLLAPSE"
        cause_word = "hard" if reset_cause == "hard" else "soft"
        if trigger_task_name:
            detail = f"{cause_word} reset · {trigger_task_name}"
        else:
            detail = f"{cause_word} reset"
    return {
        "kind": "collapse",
        "day": duration_days,
        "date": end_date,
        "label": label,
        "detail": detail,
    }


def _anchor_first_streak(
    quality_by_date: dict[str, float], start_date: str,
) -> dict | None:
    sorted_dates = sorted(quality_by_date)
    run_start = None
    for d in sorted_dates:
        if quality_by_date[d] >= STREAK_THRESHOLD:
            if run_start is None:
                run_start = d
            run_end = d
            run_len = _date_to_day(run_start, run_end) if run_start else 0
            if run_len >= STREAK_MIN_LENGTH:
                day = _date_to_day(start_date, run_start)
                return {
                    "kind": "first_streak",
                    "day": day,
                    "date": run_start,
                    "label": "First stable streak",
                    "detail": f"{STREAK_MIN_LENGTH}+ days clean",
                }
        else:
            run_start = None
    return None


def _anchor_peak(
    quality_by_date: dict[str, float], start_date: str, duration_days: int,
) -> dict | None:
    if not quality_by_date:
        return None
    sorted_dates = sorted(quality_by_date)
    if duration_days >= SHORT_ERA_PEAK_FALLBACK and len(sorted_dates) >= PEAK_WINDOW:
        # Highest 7-day rolling avg; anchor at center day
        best_avg = -1.0
        best_center = None
        for i in range(len(sorted_dates) - PEAK_WINDOW + 1):
            window = sorted_dates[i:i + PEAK_WINDOW]
            avg = sum(quality_by_date[d] for d in window) / PEAK_WINDOW
            if avg > best_avg:
                best_avg = avg
                best_center = window[PEAK_WINDOW // 2]
        if best_center is None:
            return None
        return {
            "kind": "peak",
            "day": _date_to_day(start_date, best_center),
            "date": best_center,
            "label": "Peak window",
            "detail": f"7-day avg {best_avg:.1f}/5",
        }
    # Short era: pick best single day
    best_day = max(sorted_dates, key=lambda d: quality_by_date[d])
    if quality_by_date[best_day] < STREAK_THRESHOLD:
        return None
    return {
        "kind": "peak",
        "day": _date_to_day(start_date, best_day),
        "date": best_day,
        "label": "Peak day",
        "detail": f"avg {quality_by_date[best_day]:.1f}/5",
    }


def _anchor_momentum_reversal(
    quality_by_date: dict[str, float], start_date: str,
) -> dict | None:
    """First day 7d-avg flips from up to down (delta crosses zero negative)."""
    sorted_dates = sorted(quality_by_date)
    if len(sorted_dates) < 14:
        return None
    prev_dir = None
    saw_up = False
    for i in range(14, len(sorted_dates) + 1):
        last7 = [quality_by_date[d] for d in sorted_dates[i - 7:i]]
        prior7 = [quality_by_date[d] for d in sorted_dates[i - 14:i - 7]]
        delta = sum(last7) / 7 - sum(prior7) / 7
        if delta > 0.1:
            cur_dir = "up"
            saw_up = True
        elif delta < -0.1:
            cur_dir = "down"
        else:
            cur_dir = "flat"
        if saw_up and prev_dir == "up" and cur_dir == "down":
            d = sorted_dates[i - 1]
            return {
                "kind": "momentum_reversal",
                "day": _date_to_day(start_date, d),
                "date": d,
                "label": "Momentum reversal",
                "detail": "7-day pulse turns down",
            }
        prev_dir = cur_dir
    return None


def _anchor_degradation(
    series_per_task: dict[str, list[dict]],
    tasks: list[dict],
    start_date: str,
) -> dict | None:
    """First day any tracked task entered hard or soft danger zone."""
    bucket_by_id = {t["id"]: t["bucket"] for t in tasks}
    name_by_id = {t["id"]: t["name"] for t in tasks}
    earliest = None  # (date_iso, task_name, zone)
    for tid, entries in series_per_task.items():
        if bucket_by_id.get(tid) not in TRACKED_BUCKETS:
            continue
        # Walk forward; flag first index where rolling window is in zone
        for i in range(len(entries)):
            hard_window = entries[max(0, i - RESET_HARD_WINDOW + 1):i + 1]
            soft_window = entries[max(0, i - RESET_SOFT_WINDOW + 1):i + 1]
            hard_count = sum(1 for e in hard_window if e["state"] in RESET_HARD_STATES)
            soft_count = sum(1 for e in soft_window if e["state"] in RESET_SOFT_STATES)
            in_hard = (len(hard_window) >= RESET_HARD_WINDOW
                       and hard_count >= RESET_HARD_WINDOW - 1)
            in_soft = (len(soft_window) >= RESET_SOFT_WINDOW
                       and soft_count >= RESET_SOFT_WINDOW - 1)
            if in_hard or in_soft:
                d = _iso(entries[i]["log_date"])
                zone = "hard" if in_hard else "soft"
                if earliest is None or d < earliest[0]:
                    earliest = (d, name_by_id.get(tid, tid), zone)
                break
    if earliest is None:
        return None
    return {
        "kind": "degradation",
        "day": _date_to_day(start_date, earliest[0]),
        "date": earliest[0],
        "label": "Degradation",
        "detail": f"{earliest[1]} entered {earliest[2]} zone",
    }


def _anchors_promotions(
    start_date: str, duration_days: int,
) -> list[dict]:
    """Main-tier promotions. Day 8 = Acolyte, day 15 = Wanderer, etc."""
    out: list[dict] = []
    # Main tier transitions occur at day 7*week + 1 for week >= 1
    for week in range(1, len(MAIN_LEVEL_NAMES)):
        promo_day = week * 7 + 1
        if promo_day > duration_days:
            break
        if promo_day > CHALLENGE_LENGTH_DAYS:
            break
        out.append({
            "kind": "promotion",
            "day": promo_day,
            "date": _day_to_date(start_date, promo_day),
            "label": "Promotion",
            "detail": MAIN_LEVEL_NAMES[week],
        })
    return out


def _cluster_promotions(promos: list[dict]) -> list[dict]:
    """Cluster ≥3 adjacent promotions within ≤10 days into one anchor."""
    if len(promos) < PROMOTION_CLUSTER_MIN:
        return promos
    clusters: list[list[dict]] = []
    cur = [promos[0]]
    for p in promos[1:]:
        if p["day"] - cur[-1]["day"] <= PROMOTION_CLUSTER_WINDOW:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    out: list[dict] = []
    for c in clusters:
        if len(c) >= PROMOTION_CLUSTER_MIN:
            names = " → ".join(p["detail"] for p in c)
            out.append({
                "kind": "promotion_cluster",
                "day": c[0]["day"],
                "date": c[0]["date"],
                "label": "Promotion run",
                "detail": f"{names} (days {c[0]['day']}–{c[-1]['day']})",
            })
        else:
            out.extend(c)
    return out


# ── Public API ──────────────────────────────────────────────────────────────

def compute_era_anchors(
    *,
    start_date: str,
    end_date: str,
    duration_days: int,
    entries: list[dict],
    tasks: list[dict],
    reset_cause: str | None,
    trigger_task_name: str | None,
    is_active: bool = False,
    today_iso: str | None = None,
    today_day_num: int | None = None,
) -> list[dict]:
    """Return chronologically ordered anchor list for one era.

    Always includes Start. For archived eras, always includes Collapse.
    For active eras, includes a Now marker at the end.
    Other anchors are best-effort given available data; capped at ANCHOR_CAP.
    """
    anchors: list[dict] = [_anchor_start(start_date)]

    tracked_ids = {t["id"] for t in tasks if t["bucket"] in TRACKED_BUCKETS}
    series_per_task = _entries_to_series_per_task(entries, tasks)
    quality = _daily_quality(entries, tracked_ids)

    streak = _anchor_first_streak(quality, start_date)
    if streak:
        anchors.append(streak)

    promos = _anchors_promotions(start_date, duration_days)
    promos = _cluster_promotions(promos)
    anchors.extend(promos)

    peak = _anchor_peak(quality, start_date, duration_days)
    if peak:
        anchors.append(peak)

    rev = _anchor_momentum_reversal(quality, start_date)
    if rev:
        anchors.append(rev)

    deg = _anchor_degradation(series_per_task, tasks, start_date)
    if deg:
        anchors.append(deg)

    if is_active:
        if today_iso and today_day_num and today_day_num >= 1:
            anchors.append({
                "kind": "now",
                "day": today_day_num,
                "date": today_iso,
                "label": "NOW",
                "detail": f"Day {today_day_num}",
            })
    elif reset_cause:
        anchors.append(_anchor_collapse(
            end_date, duration_days, reset_cause, trigger_task_name,
        ))

    # Sort chronologically
    anchors.sort(key=lambda a: (a["day"], 0 if a["kind"] == "start" else 1))

    # Cap density: preserve start, collapse/now (terminal), then trim middle
    if len(anchors) > ANCHOR_CAP:
        terminal = anchors[-1]
        first = anchors[0]
        middle = anchors[1:-1]
        # Priority: peak > collapse > degradation > momentum_reversal > first_streak
        # > promotion_cluster > promotion. Keep top (ANCHOR_CAP - 2) by priority.
        priority = {
            "peak": 1,
            "degradation": 2,
            "momentum_reversal": 3,
            "first_streak": 4,
            "promotion_cluster": 5,
            "promotion": 6,
        }
        middle.sort(key=lambda a: (priority.get(a["kind"], 99), a["day"]))
        keep = middle[:ANCHOR_CAP - 2]
        keep.sort(key=lambda a: a["day"])
        anchors = [first] + keep + [terminal]

    return anchors


def cluster_false_starts(eras: list[dict]) -> list[dict]:
    """Group consecutive sub-FALSE_START_THRESHOLD eras into cluster blocks.

    Input: archived eras, newest-first.
    Output: list of items each tagged either:
      {"kind": "era", "era": <era dict>}
      {"kind": "false_starts", "eras": [<era dicts>], "count": N}
    """
    out: list[dict] = []
    buf: list[dict] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        if len(buf) >= 2:
            out.append({"kind": "false_starts", "eras": list(buf), "count": len(buf)})
        else:
            out.append({"kind": "era", "era": buf[0]})
        buf = []

    for e in eras:
        dur = e.get("duration_days") or 0
        if dur <= FALSE_START_THRESHOLD:
            buf.append(e)
        else:
            flush()
            out.append({"kind": "era", "era": e})
    flush()
    return out
