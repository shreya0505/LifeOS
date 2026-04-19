"""Metrics computation + prose narrative generators."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date as _date

from .config import (
    RESET_HARD_WINDOW,
    RESET_SOFT_WINDOW,
    RESET_HARD_STATES,
    RESET_SOFT_STATES,
    STATE_RANK,
    STATE_LABELS,
    TRACKED_BUCKETS,
)

# Thresholds before a derived metric is meaningful
GATE_MOMENTUM = 14           # 7 prior + 7 current
GATE_CONSISTENCY = 7
GATE_RECOVERY = 10
GATE_WEEKDAY = 14
GATE_TASK_SIGNAL = 14
GATE_TIER_VELOCITY = 14


def per_task_health(entries: list[dict]) -> dict:
    """Entries chronological oldest→newest. Returns health breakdown."""
    last_hard = entries[-RESET_HARD_WINDOW:] if len(entries) >= 1 else []
    last_soft = entries[-RESET_SOFT_WINDOW:] if len(entries) >= 1 else []

    hard_count = sum(1 for e in last_hard if e["state"] in RESET_HARD_STATES)
    soft_count = sum(1 for e in last_soft if e["state"] in RESET_SOFT_STATES)

    return {
        "hard_progress": hard_count,
        "hard_window": RESET_HARD_WINDOW,
        "soft_progress": soft_count,
        "soft_window": RESET_SOFT_WINDOW,
        "hard_zone": hard_count >= RESET_HARD_WINDOW - 1,
        "soft_zone": soft_count >= RESET_SOFT_WINDOW - 1,
    }


def survival_index(health_by_task: dict[str, dict]) -> float:
    """0.0 (about to reset) to 1.0 (clean). Tracked tasks only."""
    if not health_by_task:
        return 1.0
    scores = []
    for h in health_by_task.values():
        hard_risk = h["hard_progress"] / h["hard_window"]
        soft_risk = h["soft_progress"] / h["soft_window"]
        scores.append(1.0 - (hard_risk * 0.6 + soft_risk * 0.4))
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def bucket_posture(entries_by_bucket: dict[str, list[dict]]) -> dict:
    out = {}
    for bucket, entries in entries_by_bucket.items():
        counts = Counter(e["state"] for e in entries)
        out[bucket] = dict(counts)
    return out


def detect_drift(entries: list[dict]) -> str | None:
    """Last 4 entries. Detect monotonic worsening or all low."""
    if len(entries) < 4:
        return None
    last4 = entries[-4:]
    ranks = [STATE_RANK.get(e["state"], 0) for e in last4]
    if all(ranks[i] >= ranks[i + 1] for i in range(3)) and ranks[0] > ranks[-1]:
        chain = " → ".join(STATE_LABELS.get(e["state"], e["state"]) for e in last4)
        return f"Sliding: {chain}"
    if all(r <= 2 for r in ranks):
        return "Stalled: last 4 entries at or below Started"
    return None


def pattern_callouts(entries_by_task: dict[str, list[dict]], task_names: dict[str, str]) -> list[str]:
    out = []
    for task_id, entries in entries_by_task.items():
        name = task_names.get(task_id, task_id)
        last7 = entries[-RESET_SOFT_WINDOW:]
        if len(last7) < RESET_SOFT_WINDOW:
            continue
        started_cnt = sum(1 for e in last7 if e["state"] == "STARTED")
        notdone_cnt = sum(1 for e in last7 if e["state"] == "NOT_DONE")
        if started_cnt >= 5:
            out.append(f"{name}: {started_cnt} of last 7 = Started. Motion without finish.")
        if notdone_cnt >= 4:
            out.append(f"{name}: {notdone_cnt} of last 7 = Not Done. Edge of reset.")
        drift = detect_drift(entries)
        if drift:
            out.append(f"{name}: {drift}")
    return out


def enricher_engagement(entries: list[dict], days_elapsed: int) -> dict:
    if days_elapsed == 0:
        return {"logged_pct": 0, "skipped_pct": 0, "logged": 0, "total": 0}
    logged = sum(1 for e in entries if e["state"] != "NOT_DONE")
    total = days_elapsed
    logged_pct = int((logged / total) * 100) if total else 0
    return {
        "logged_pct": logged_pct,
        "skipped_pct": 100 - logged_pct,
        "logged": logged,
        "total": total,
    }


def era_prose(
    era_name: str, days_elapsed: int, peak_level_name: str,
    reset_cause: str, trigger_task_name: str | None,
) -> str:
    """Generate narrative for archived era."""
    if reset_cause == "completed":
        return (
            f"The {era_name} stood for {days_elapsed} days. "
            f"Reached {peak_level_name}. Unbroken."
        )
    if reset_cause == "forfeit":
        return (
            f"The {era_name} ended by choice at day {days_elapsed}. "
            f"Peak: {peak_level_name}. Relinquished."
        )
    # reset: hard or soft
    cause_map = {
        "hard": "Three in a row. Not Done.",
        "soft": "Seven days of motion without finish.",
    }
    cause = cause_map.get(reset_cause, "The chain broke.")
    task = f" {trigger_task_name} broke the chain." if trigger_task_name else ""
    return (
        f"Faltered at day {days_elapsed}. {cause}{task} "
        f"{era_name} ends. Peak reached: {peak_level_name}."
    )


def build_task_health_map(
    entries_by_task: dict[str, list[dict]], tasks: list[dict],
) -> dict[str, dict]:
    """Filter to tracked buckets only."""
    bucket_by_id = {t["id"]: t["bucket"] for t in tasks}
    return {
        tid: per_task_health(entries)
        for tid, entries in entries_by_task.items()
        if bucket_by_id.get(tid) in TRACKED_BUCKETS
    }


# ── Time-series helpers ─────────────────────────────────────────────────────

def _iso(d) -> str:
    return d if isinstance(d, str) else d.isoformat()


def daily_quality_series(
    entries_by_task: dict[str, list[dict]],
    tracked_task_ids: set[str],
) -> list[dict]:
    """Per-calendar-date avg STATE_RANK across tracked tasks.
    Only days with at least one tracked entry are included. Chronological."""
    by_date: dict[str, list[int]] = defaultdict(list)
    for tid, entries in entries_by_task.items():
        if tid not in tracked_task_ids:
            continue
        for e in entries:
            by_date[_iso(e["log_date"])].append(STATE_RANK.get(e["state"], 0))
    rows = []
    for d in sorted(by_date):
        ranks = by_date[d]
        rows.append({"date": d, "avg_rank": sum(ranks) / len(ranks), "n": len(ranks)})
    return rows


def momentum(series: list[dict]) -> dict | None:
    if len(series) < GATE_MOMENTUM:
        return None
    last7 = [r["avg_rank"] for r in series[-7:]]
    prior7 = [r["avg_rank"] for r in series[-14:-7]]
    last_avg = sum(last7) / 7
    prior_avg = sum(prior7) / 7
    delta = last_avg - prior_avg
    if delta > 0.1:
        direction = "up"
    elif delta < -0.1:
        direction = "down"
    else:
        direction = "flat"
    return {
        "delta": round(delta, 2),
        "last7_avg": round(last_avg, 2),
        "prior7_avg": round(prior_avg, 2),
        "direction": direction,
    }


def consistency_index(series: list[dict]) -> dict | None:
    if len(series) < GATE_CONSISTENCY:
        return None
    vals = [r["avg_rank"] for r in series]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    stdev = math.sqrt(var)
    # Map: stdev 0 → 100, stdev 2.0+ → 0 (range of ranks is 1..5, max stdev ~2)
    index = max(0, min(100, int(round((1 - min(stdev / 2.0, 1.0)) * 100))))
    return {"stdev": round(stdev, 2), "index_0_100": index, "mean": round(mean, 2)}


def recovery_rate(series_per_task: dict[str, list[dict]]) -> dict | None:
    """Avg days from a dip (NOT_DONE/STARTED) to next COMPLETED_SATISFACTORY.
    Walks per-task state list in chronological order. Needs at least one sample."""
    samples: list[int] = []
    for entries in series_per_task.values():
        if len(entries) < 2:
            continue
        dip_idx = None
        for i, e in enumerate(entries):
            if e["state"] in ("NOT_DONE", "STARTED"):
                if dip_idx is None:
                    dip_idx = i
            elif e["state"] == "COMPLETED_SATISFACTORY":
                if dip_idx is not None:
                    samples.append(i - dip_idx)
                    dip_idx = None
    total_days = sum(len(v) for v in series_per_task.values())
    if total_days < GATE_RECOVERY or not samples:
        return None
    return {
        "avg_days": round(sum(samples) / len(samples), 1),
        "samples": len(samples),
        "best": min(samples),
        "worst": max(samples),
    }


def streak_runs(series: list[dict], threshold: float = 4.5) -> dict:
    """Longest and current runs where daily avg_rank ≥ threshold."""
    peak = 0
    current = 0
    for r in series:
        if r["avg_rank"] >= threshold:
            current += 1
            peak = max(peak, current)
        else:
            current = 0
    return {"peak": peak, "current": current}


def weekday_posture(series: list[dict]) -> list[dict] | None:
    if len(series) < GATE_WEEKDAY:
        return None
    # Monday = 0 .. Sunday = 6
    buckets: dict[int, list[float]] = defaultdict(list)
    for r in series:
        try:
            dow = _date.fromisoformat(r["date"]).weekday()
        except ValueError:
            continue
        buckets[dow].append(r["avg_rank"])
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out = []
    for i in range(7):
        vals = buckets.get(i, [])
        avg = sum(vals) / len(vals) if vals else 0.0
        out.append({"dow": i, "name": names[i], "avg": round(avg, 2), "n": len(vals)})
    return out


def keystone_task(
    series_per_task: dict[str, list[dict]],
    daily_series: list[dict],
    task_names: dict[str, str],
) -> dict | None:
    """Task whose daily rank best correlates with overall day quality."""
    if len(daily_series) < GATE_TASK_SIGNAL:
        return None
    day_rank = {r["date"]: r["avg_rank"] for r in daily_series}
    best = None
    for tid, entries in series_per_task.items():
        pairs = [
            (STATE_RANK.get(e["state"], 0), day_rank.get(_iso(e["log_date"])))
            for e in entries
        ]
        pairs = [(a, b) for a, b in pairs if b is not None]
        if len(pairs) < GATE_TASK_SIGNAL:
            continue
        corr = _pearson(pairs)
        if corr is None:
            continue
        if best is None or corr > best["correlation"]:
            best = {
                "task_id": tid,
                "name": task_names.get(tid, tid),
                "correlation": round(corr, 2),
            }
    return best


def fragile_task(
    health_map: dict[str, dict], task_names: dict[str, str],
) -> dict | None:
    """Task closest to resetting the era. Higher hard_progress wins; ties → soft."""
    if not health_map:
        return None
    best = None
    for tid, h in health_map.items():
        hard = h.get("hard_progress", 0)
        soft = h.get("soft_progress", 0)
        score = hard * 10 + soft
        if best is None or score > best["_score"]:
            best = {
                "task_id": tid,
                "name": task_names.get(tid, tid),
                "hard_progress": hard,
                "hard_window": h.get("hard_window", RESET_HARD_WINDOW),
                "soft_progress": soft,
                "soft_window": h.get("soft_window", RESET_SOFT_WINDOW),
                "window": "hard" if hard >= 2 else "soft",
                "_score": score,
            }
    if best and best["_score"] == 0:
        return None
    if best:
        best.pop("_score", None)
    return best


def tier_velocity(days_elapsed: int, peak_level: int) -> dict | None:
    """Actual days per tier vs baseline 7. peak_level = monotonic tier id."""
    if days_elapsed < GATE_TIER_VELOCITY or peak_level <= 0:
        return None
    actual = days_elapsed / peak_level
    return {
        "actual_days_per_tier": round(actual, 1),
        "baseline": 7,
        "delta": round(actual - 7, 1),
        "tiers_reached": peak_level,
    }


def engagement_curve(entries: list[dict]) -> list[dict]:
    """Per-week notes-written ratio (of tracked entries in that week)."""
    by_week: dict[str, dict] = defaultdict(lambda: {"total": 0, "noted": 0})
    for e in entries:
        try:
            d = _date.fromisoformat(_iso(e["log_date"]))
        except ValueError:
            continue
        iso_year, iso_week, _ = d.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        bucket = by_week[key]
        bucket["total"] += 1
        if (e.get("notes") or "").strip():
            bucket["noted"] += 1
    out = []
    for key in sorted(by_week):
        b = by_week[key]
        pct = int(round(b["noted"] / b["total"] * 100)) if b["total"] else 0
        out.append({"week": key, "noted": b["noted"], "total": b["total"], "pct": pct})
    return out


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    n = len(pairs)
    if n < 2:
        return None
    sx = sum(a for a, _ in pairs)
    sy = sum(b for _, b in pairs)
    mx = sx / n
    my = sy / n
    num = sum((a - mx) * (b - my) for a, b in pairs)
    dx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    dy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ── Prose generators ────────────────────────────────────────────────────────

def pulse_quote(m: dict | None) -> str:
    if m is None:
        return "The line is still being drawn."
    if m["direction"] == "up":
        return "The line rises. Pressure yields to form."
    if m["direction"] == "down":
        return "The line falls. The system notes the slip."
    return "The line holds. Neither gain nor loss this turn."


def rhythm_quote(wd: list[dict] | None) -> str:
    if wd is None:
        return "Rhythm takes shape across weeks, not days."
    ranked = [r for r in wd if r["n"] > 0]
    if not ranked:
        return "No rhythm yet visible."
    best = max(ranked, key=lambda r: r["avg"])
    worst = min(ranked, key=lambda r: r["avg"])
    if abs(best["avg"] - worst["avg"]) < 0.4:
        return "The week moves evenly. No single day carries the weight."
    return f"{best['name']}s hold. {worst['name']}s falter. The week is not uniform."


def closing_narrative(state: dict) -> str:
    """state keys: survival_pct, momentum_dir, streak_current, streak_peak, era_name."""
    era = state.get("era_name", "the era")
    pct = state.get("survival_pct", 100)
    mdir = state.get("momentum_dir")
    cur = state.get("streak_current", 0)
    peak = state.get("streak_peak", 0)

    parts = [f"The <em>{era}</em> reads its ledger."]
    if pct >= 75:
        parts.append("The chain holds. Anchors are being met.")
    elif pct >= 40:
        parts.append("Cracks have appeared. The run continues under pressure.")
    else:
        parts.append("This is the edge. One more failure severs the era.")

    if mdir == "up":
        parts.append("Momentum moves in your favour.")
    elif mdir == "down":
        parts.append("Momentum moves against you.")

    if cur and cur >= 3:
        parts.append(f"A {cur}-day clean run is active.")
    elif peak and peak >= 3:
        parts.append(f"The peak clean run reached {peak} days before breaking.")

    parts.append("The system does not flatter. It only reports.")
    return " ".join(parts)


# ── System verdict + directive (derived) ──────────────────────────────────

def system_status(survival_pct: int, health_by_task: dict[str, dict]) -> str:
    """Single-word system state. Thresholds + hard-zone short-circuit."""
    any_hard_zone = any(h.get("hard_zone") for h in health_by_task.values())
    if any_hard_zone or survival_pct < 50:
        return "Collapse"
    if survival_pct < 80:
        return "At Risk"
    return "Stable"


def system_verdict(status: str, momentum_dict: dict | None, fragile: dict | None) -> str:
    """1–2 line prose verdict selected by (status, momentum)."""
    mdir = momentum_dict["direction"] if momentum_dict else None
    if status == "Collapse":
        base = "One chain sits on the reset trigger."
        if fragile:
            base = f"{fragile['name']} sits on the reset trigger."
        tail = "A single miss ends the era." if mdir != "up" else "Reverse the slide today."
        return f"{base} {tail}"
    if status == "At Risk":
        if mdir == "down":
            return "The form is drifting and a chain is within the soft window. Hold the line."
        return "Pressure has entered the system. One task is closer to a reset than the rest."
    if mdir == "up":
        return "All chains clean. Form is consolidating."
    if mdir == "down":
        return "Chains are clean, but the pulse is slipping. Do not coast."
    return "All chains clean. The system is holding."


def _fragile_in_hard_zone(fragile: dict | None) -> bool:
    if not fragile:
        return False
    return fragile.get("hard_progress", 0) >= fragile.get("hard_window", RESET_HARD_WINDOW) - 1


def _fragile_in_soft_zone(fragile: dict | None) -> bool:
    if not fragile:
        return False
    return fragile.get("soft_progress", 0) >= fragile.get("soft_window", RESET_SOFT_WINDOW) - 1


def directive(
    fragile: dict | None,
    keystone: dict | None,
    momentum_dict: dict | None,
) -> str:
    """Single actionable sentence — what to do next."""
    if _fragile_in_hard_zone(fragile):
        return f"Hold {fragile['name']} today — one miss resets the chain."
    if _fragile_in_soft_zone(fragile):
        return f"Land a satisfactory on {fragile['name']} before the soft window closes."
    if momentum_dict and momentum_dict["direction"] == "down":
        if keystone:
            return f"Pulse is drifting. Protect {keystone['name']} for the next three days."
        return "Pulse is drifting. Tighten the anchors for the next three days."
    return "System is holding. Keep the anchors clean."
