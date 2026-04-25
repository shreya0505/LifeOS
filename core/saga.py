"""Saga projection and metrics helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean

import aiosqlite

from core.config import USER_TZ
from core.storage.saga_backend import EMOTION_FAMILIES, MIXED_EMOTIONS
from core.utils import today_local, to_local_date


SOURCE_LABELS = {
    "saga": "Saga",
    "questlog": "Questlog",
    "hard90": "Hard 90",
}


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(USER_TZ)


def display_time(value: str | None) -> str:
    dt = parse_iso(value)
    return dt.strftime("%H:%M") if dt else ""


def block_for_timestamp(value: str | None) -> str:
    dt = parse_iso(value)
    if dt is None:
        return "Night"
    hour = dt.hour
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 22:
        return "Evening"
    return "Night"


def _date_fallback_timestamp(local_date: str, at: time) -> str:
    dt = datetime.combine(date.fromisoformat(local_date), at, tzinfo=USER_TZ)
    return dt.isoformat()


async def unified_events(db: aiosqlite.Connection, local_date: str | None = None) -> list[dict]:
    """Build a chronological, read-only story for one local day."""
    day = local_date or today_local().isoformat()
    events: list[dict] = []

    saga_cursor = await db.execute(
        "SELECT id, timestamp, emotion_family, emotion_label, intensity, note "
        "FROM saga_entries WHERE local_date = ? ORDER BY timestamp",
        (day,),
    )
    for row in await saga_cursor.fetchall():
        events.append({
            "id": f"saga:{row[0]}",
            "source": "saga",
            "source_label": SOURCE_LABELS["saga"],
            "timestamp": row[1],
            "time": display_time(row[1]),
            "block": block_for_timestamp(row[1]),
            "title": f"{row[4].title()} · {row[5]}/10",
            "summary": row[6] or "Moment captured.",
            "payload": {
                "family": row[2],
                "emotion": row[4],
                "intensity": row[5],
                "note": row[6],
            },
        })

    quest_cursor = await db.execute(
        "SELECT q.id, q.title, q.completed_at, q.project, q.labels, w.name "
        "FROM quests q LEFT JOIN workspaces w ON w.id = q.workspace_id "
        "WHERE q.status = 'done' AND q.completed_at IS NOT NULL"
    )
    for row in await quest_cursor.fetchall():
        if to_local_date(row[2]) != day:
            continue
        summary_bits = []
        if row[3]:
            summary_bits.append(row[3])
        if row[5]:
            summary_bits.append(row[5])
        events.append({
            "id": f"questlog:{row[0]}",
            "source": "questlog",
            "source_label": SOURCE_LABELS["questlog"],
            "timestamp": row[2],
            "time": display_time(row[2]),
            "block": block_for_timestamp(row[2]),
            "title": row[1],
            "summary": " · ".join(summary_bits) or "Completed quest.",
            "payload": {"project": row[3], "labels": row[4], "workspace": row[5]},
        })

    hard90_cursor = await db.execute(
        "SELECT e.id, e.created_at, e.log_date, e.state, e.notes, t.name, t.bucket, c.era_name "
        "FROM challenge_entries e "
        "JOIN challenge_tasks t ON t.id = e.task_id "
        "JOIN challenges c ON c.id = e.challenge_id "
        "WHERE e.log_date = ? "
        "ORDER BY e.created_at, t.name",
        (day,),
    )
    for row in await hard90_cursor.fetchall():
        timestamp = row[1] or _date_fallback_timestamp(row[2], time(20, 0))
        events.append({
            "id": f"hard90:{row[0]}",
            "source": "hard90",
            "source_label": SOURCE_LABELS["hard90"],
            "timestamp": timestamp,
            "time": display_time(timestamp),
            "block": block_for_timestamp(timestamp),
            "title": row[5],
            "summary": row[4] or row[3].replace("_", " ").title(),
            "payload": {"state": row[3], "bucket": row[6], "era": row[7]},
        })

    events.sort(key=lambda item: item["timestamp"] or "")
    return events


def grouped_events(events: list[dict]) -> list[dict]:
    groups = []
    by_block: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_block[event["block"]].append(event)
    for block in ("Morning", "Afternoon", "Evening", "Night"):
        groups.append({"label": block, "events": by_block.get(block, [])})
    return groups


async def saga_metrics(db: aiosqlite.Connection, days: int = 35) -> dict:
    end = today_local()
    start = end - timedelta(days=days - 1)
    cursor = await db.execute(
        "SELECT local_date, emotion_family, emotion_label, intensity "
        "FROM saga_entries WHERE local_date >= ? ORDER BY local_date, timestamp",
        (start.isoformat(),),
    )
    rows = await cursor.fetchall()
    by_day: dict[str, list[int]] = defaultdict(list)
    family_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for local_date, family, label, intensity in rows:
        by_day[local_date].append(intensity)
        family_counts[family] += 1
        label_counts[label] += 1

    heatmap = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        key = current.isoformat()
        values = by_day.get(key, [])
        avg = mean(values) if values else 0
        variance = max(values) - min(values) if len(values) > 1 else 0
        if not values:
            level = "empty"
        elif avg <= 3:
            level = "low"
        elif avg <= 6:
            level = "mid"
        elif avg <= 8:
            level = "high"
        else:
            level = "peak"
        heatmap.append({
            "date": key,
            "day": current.day,
            "count": len(values),
            "average": round(avg, 1),
            "variance": variance,
            "level": level,
        })

    day_averages = [mean(values) for _, values in sorted(by_day.items()) if values]
    if len(day_averages) > 1:
        drift = [abs(day_averages[i] - day_averages[i - 1]) for i in range(1, len(day_averages))]
        volatility = round(mean(drift), 1)
    else:
        volatility = 0
    stability = "Stable" if volatility < 1.5 else "Variable" if volatility < 3 else "Volatile"

    quest_cursor = await db.execute(
        "SELECT completed_at FROM quests WHERE status = 'done' AND completed_at IS NOT NULL"
    )
    completions_by_day: Counter[str] = Counter()
    for (completed_at,) in await quest_cursor.fetchall():
        completions_by_day[to_local_date(completed_at)] += 1
    high_intensity_days = [
        day for day, values in by_day.items()
        if values and mean(values) >= 7
    ]
    if high_intensity_days:
        high_avg = mean(completions_by_day.get(day, 0) for day in high_intensity_days)
        all_avg = mean(completions_by_day.get((start + timedelta(days=i)).isoformat(), 0) for i in range(days))
        if high_avg > all_avg:
            correlation = "High intensity days are currently paired with more Questlog completions."
        elif high_avg < all_avg:
            correlation = "High intensity days are currently paired with fewer Questlog completions."
        else:
            correlation = "High intensity days are tracking close to your usual Questlog completion rate."
    else:
        correlation = "Capture a few higher-intensity moments to unlock correlation hints."

    total = sum(family_counts.values())
    distribution = [
        {
            "family": family,
            "label": family.title(),
            "count": family_counts.get(family, 0),
            "pct": round((family_counts.get(family, 0) / total) * 100) if total else 0,
        }
        for family in EMOTION_FAMILIES
    ]

    return {
        "heatmap": heatmap,
        "distribution": distribution,
        "top_labels": label_counts.most_common(5),
        "stability": stability,
        "volatility": volatility,
        "correlation": correlation,
        "total_entries": total,
    }


def emotion_catalog() -> list[dict]:
    return [
        {
            "family": family,
            "label": family.title(),
            "words": words,
            "mix": MIXED_EMOTIONS.get(family),
        }
        for family, words in EMOTION_FAMILIES.items()
    ]
