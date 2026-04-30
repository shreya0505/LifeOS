"""Saga projection and metrics helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import html
import json
import math
import re
from statistics import mean

import aiosqlite
from markupsafe import Markup

from core.challenge import metrics_engine
from core.challenge.config import (
    EXPERIMENT_TIMEFRAME_DAYS,
    STATE_LABELS,
    STATE_RANK,
    STATE_SHORT,
    STATES,
    TRACKED_BUCKETS,
)
from core.config import USER_TZ
from core.storage.saga_backend import (
    MOOD_WORDS,
    PLEASANTNESS_COORDS,
    QUADRANT_COLORS,
    QUADRANT_LABELS,
    VALID_MOOD_COORDS,
    quadrant_for,
)
from core.utils import today_local, to_local_date


SOURCE_LABELS = {
    "saga": "Saga",
    "questlog": "Questlog",
    "hard90": "Hard 90",
}

QUADRANT_ORDER = ("yellow", "red", "green", "blue")
MOOD_ROWS = (7, 6, 5, 4, 3, 2, 1, -1, -2, -3, -4, -5, -6, -7)

QUEST_PRIORITY_WEIGHTS = {
    0: 1.70,
    1: 1.45,
    2: 1.20,
    3: 1.00,
    4: 0.75,
}
QUEST_FROG_MULTIPLIER = 1.35
CHALLENGE_BUCKET_WEIGHTS = {
    "anchor": 50,
    "improver": 35,
    "enricher": 15,
}
FIELD_REPORT_WEIGHTS = {
    "daily_execution": {
        "quest_quality": 65,
        "focus_quality": 25,
        "frog_consistency": 10,
    },
    "long_game": {
        "hard90_integrity": 85,
        "experiment_enricher_signal": 15,
    },
    "evolution": {
        "active_trial_health": 35,
        "logging_consistency": 30,
        "verdict_hygiene": 20,
        "learning_closure": 15,
    },
    "emotional_climate": {
        "adaptive_valence": 45,
        "low_acute_load": 25,
        "stability": 15,
        "pleasant_access": 15,
    },
}


def render_markdown_note(value: str | None) -> str:
    """Render a small, escaped Markdown subset for saved Saga notes."""
    text = (value or "").strip()
    if not text:
        return "<p>Moment captured.</p>"

    def inline(raw: str) -> str:
        escaped = html.escape(raw, quote=True)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", escaped)
        escaped = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", escaped)
        return escaped

    blocks: list[str] = []
    paragraph: list[str] = []
    bullet_items: list[str] = []
    ordered_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{'<br>'.join(inline(line) for line in paragraph)}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullet_items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in bullet_items) + "</ul>")
            bullet_items.clear()

    def flush_ordered() -> None:
        if ordered_items:
            blocks.append("<ol>" + "".join(f"<li>{item}</li>" for item in ordered_items) + "</ol>")
            ordered_items.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_bullets()
            flush_ordered()
            continue
        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            flush_ordered()
            bullet_items.append(inline(bullet.group(1)))
        elif ordered:
            flush_paragraph()
            flush_bullets()
            ordered_items.append(inline(ordered.group(1)))
        else:
            flush_bullets()
            flush_ordered()
            paragraph.append(stripped)

    flush_paragraph()
    flush_bullets()
    flush_ordered()
    return "".join(blocks) or "<p>Moment captured.</p>"


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


def display_labels(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        cleaned = value.strip()
        return cleaned if cleaned and cleaned not in {"[]", "{}"} else None
    if isinstance(parsed, list):
        labels = [str(item).strip() for item in parsed if str(item).strip()]
        return ", ".join(labels) if labels else None
    if parsed is None:
        return None
    cleaned = str(parsed).strip()
    return cleaned if cleaned and cleaned not in {"[]", "{}"} else None


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
        "SELECT id, timestamp, energy, pleasantness, quadrant, mood_word, note "
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
            "title": f"{row[5].title()} / E:{row[2]} P:{row[3]}",
            "summary": row[6] or "Moment captured.",
            "payload": {
                "energy": row[2],
                "pleasantness": row[3],
                "quadrant": row[4],
                "mood_word": row[5],
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
        labels = display_labels(row[4])
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
            "summary": " / ".join(summary_bits) or "Completed quest.",
            "payload": {"project": row[3], "labels": labels, "workspace": row[5]},
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
        summary = (row[4] or "").strip()
        if not summary and row[3]:
            summary = row[3].replace("_", " ").title()
        events.append({
            "id": f"hard90:{row[0]}",
            "source": "hard90",
            "source_label": SOURCE_LABELS["hard90"],
            "timestamp": timestamp,
            "time": display_time(timestamp),
            "block": block_for_timestamp(timestamp),
            "title": row[5],
            "summary": summary or "Captured note.",
            "payload": {"state": row[3], "bucket": row[6], "era": row[7], "notes": row[4]},
        })

    events.sort(key=lambda item: item["timestamp"] or "")
    return events


def _empty_timeline_day(local_date: str) -> dict:
    day = date.fromisoformat(local_date)
    return {
        "date": local_date,
        "label": day.strftime("%b %d"),
        "weekday": day.strftime("%A"),
        "granularity": "day",
        "entries": [],
        "challenge_reflections": [],
        "quests": [],
        "challenges": [],
        "challenges_signal": [],
        "challenges_done": [],
        "experiments": [],
    }


def _timeline_granularity(local_date: str, today: date) -> str:
    day = date.fromisoformat(local_date)
    age = (today - day).days
    if age < 7:
        return "day"
    if age < 31:
        return "week"
    if age < 366:
        return "month"
    return "year"


def _count_label(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def _top_counts(values: list[str | None], limit: int = 3) -> list[dict]:
    counts = Counter(value for value in values if value)
    return [
        {"label": label, "count": count}
        for label, count in counts.most_common(limit)
    ]


def _challenge_state_label(state: str | None) -> str | None:
    if not state:
        return None
    return STATE_LABELS.get(state, state.replace("_", " ").title())


def _challenge_state_short(state: str | None) -> str | None:
    if not state:
        return None
    return STATE_SHORT.get(state, state.replace("_", " ").title())


def _challenge_state_tone(state: str | None) -> str:
    rank = STATE_RANK.get(state or "", 0)
    if rank >= 5:
        return "held"
    if rank >= 3:
        return "mixed"
    if rank >= 2:
        return "started"
    return "missed"


def _quest_day_summary(quests: list[dict]) -> dict | None:
    if not quests:
        return None
    contexts = [quest.get("project") or quest.get("workspace") for quest in quests]
    return {
        "count": len(quests),
        "status": f"{len(quests)} done",
        "contexts": _top_counts(contexts, 2),
    }


def _challenge_day_summary(challenges: list[dict]) -> dict | None:
    if not challenges:
        return None
    counts = Counter(item.get("state_key") or item.get("state") for item in challenges)
    known_states = [state for state in reversed(STATES) if counts.get(state)]
    state_order = known_states + [state for state in counts if state not in STATES]
    ranks = [STATE_RANK.get(item.get("state_key") or "", 0) for item in challenges]
    score = int(round(mean(((rank - 1) / 4) * 100 for rank in ranks))) if ranks else 0
    return {
        "count": len(challenges),
        "score": score,
        "label": _band(score, (45, 70, 86), ("Frayed", "Mixed", "Held", "Clean")),
        "states": [
            {
                "key": (state or "unknown").lower(),
                "label": _challenge_state_short(state),
                "count": counts[state],
                "tone": _challenge_state_tone(state),
            }
            for state in state_order
        ],
        "buckets": _top_counts([item.get("bucket") for item in challenges], 3),
        "era": next((item.get("era") for item in challenges if item.get("era")), None),
    }


def _experiment_timeframe_days(timeframe: str | None) -> int:
    return EXPERIMENT_TIMEFRAME_DAYS.get(timeframe or "", 1)


def _experiment_days_remaining(exp: dict, local_date: str) -> int | None:
    if not exp.get("ends_at"):
        return None
    try:
        return (date.fromisoformat(exp["ends_at"]) - date.fromisoformat(local_date)).days + 1
    except ValueError:
        return None


def _experiment_needs_verdict_on(exp: dict, local_date: str) -> bool:
    if exp.get("status") != "running" or not exp.get("ends_at"):
        return False
    try:
        return date.fromisoformat(local_date) > date.fromisoformat(exp["ends_at"])
    except ValueError:
        return False


def _experiment_signal(entries: list[dict]) -> dict:
    rated_entries = [entry for entry in entries if entry.get("state") in STATE_RANK]
    if not rated_entries:
        return {"arrow": "→", "tone": "neutral", "label": "No entries"}
    ranks = [STATE_RANK[entry["state"]] for entry in rated_entries]
    avg = mean(ranks) if ranks else 0
    if avg >= 4:
        return {"arrow": "↑", "tone": "up", "label": "Signal rising"}
    if avg >= 2.8:
        return {"arrow": "→", "tone": "neutral", "label": "Signal mixed"}
    return {"arrow": "↓", "tone": "down", "label": "Signal weak"}


async def _timeline_experiments_by_day(
    db: aiosqlite.Connection,
    start: date,
    end: date,
) -> dict[str, list[dict]]:
    cursor = await db.execute(
        "SELECT e.id, e.challenge_id, e.action, e.motivation, e.timeframe, e.status, "
        "e.started_at, e.ends_at, e.verdict, e.observation_notes, e.conclusion_notes, "
        "e.created_at, c.era_name "
        "FROM challenge_experiments e "
        "LEFT JOIN challenges c ON c.id = e.challenge_id "
        "WHERE COALESCE(e.started_at, e.created_at) <= ? "
        "   OR e.id IN (SELECT experiment_id FROM challenge_experiment_entries WHERE log_date >= ?)",
        (end.isoformat(), start.isoformat()),
    )
    experiments = {}
    for row in await cursor.fetchall():
        experiments[row[0]] = {
            "id": row[0],
            "challenge_id": row[1],
            "action": row[2],
            "motivation": row[3],
            "timeframe": row[4],
            "status": row[5],
            "started_at": row[6],
            "ends_at": row[7],
            "verdict": row[8],
            "observation_notes": row[9],
            "conclusion_notes": row[10],
            "created_at": row[11],
            "era_name": row[12],
        }

    if not experiments:
        return {}

    entry_cursor = await db.execute(
        "SELECT id, experiment_id, challenge_id, log_date, state, notes, created_at "
        "FROM challenge_experiment_entries "
        "WHERE experiment_id IN ({}) "
        "ORDER BY log_date, created_at".format(",".join("?" for _ in experiments)),
        tuple(experiments.keys()),
    )
    entries_by_experiment: dict[str, list[dict]] = defaultdict(list)
    entries_by_day: dict[tuple[str, str], dict] = {}
    for row in await entry_cursor.fetchall():
        entry = {
            "id": row[0],
            "experiment_id": row[1],
            "challenge_id": row[2],
            "log_date": row[3],
            "state": row[4],
            "state_short": _challenge_state_short(row[4]),
            "state_tone": _challenge_state_tone(row[4]),
            "notes": row[5],
            "created_at": row[6],
            "time": display_time(row[6]),
        }
        entries_by_experiment[row[1]].append(entry)
        entries_by_day[(row[1], row[3])] = entry

    out: dict[str, list[dict]] = defaultdict(list)
    today = today_local()
    for exp_id, exp in experiments.items():
        exp_entries = entries_by_experiment.get(exp_id, [])
        breakdown = {state: 0 for state in STATES}
        for entry in exp_entries:
            if entry.get("state") in breakdown:
                breakdown[entry["state"]] += 1
        signal = _experiment_signal(exp_entries)
        relevant_days: set[str] = set()
        if exp.get("started_at"):
            relevant_days.add(exp["started_at"])
        if exp.get("ends_at"):
            relevant_days.add(exp["ends_at"])
        for entry in exp_entries:
            relevant_days.add(entry["log_date"])

        if exp.get("started_at"):
            try:
                active_start = max(date.fromisoformat(exp["started_at"]), start)
                active_end = min(date.fromisoformat(exp.get("ends_at") or end.isoformat()), end)
                if active_end >= active_start:
                    for offset in range((active_end - active_start).days + 1):
                        relevant_days.add((active_start + timedelta(days=offset)).isoformat())
            except ValueError:
                pass

        if _experiment_needs_verdict_on(exp, today.isoformat()):
            relevant_days.add(today.isoformat())

        recent_entries = exp_entries[-3:]
        for local_date in sorted(day for day in relevant_days if start.isoformat() <= day <= end.isoformat()):
            current_entry = entries_by_day.get((exp_id, local_date))
            days_remaining = _experiment_days_remaining(exp, local_date)
            needs_verdict = _experiment_needs_verdict_on(exp, local_date)
            events = []
            if exp.get("started_at") == local_date:
                events.append("started")
            if exp.get("ends_at") == local_date:
                events.append("ends")
            out[local_date].append({
                "id": exp_id,
                "action": exp["action"],
                "motivation": exp["motivation"],
                "status": exp["status"],
                "era": exp.get("era_name"),
                "started_at": exp.get("started_at"),
                "ends_at": exp.get("ends_at"),
                "duration_days": _experiment_timeframe_days(exp.get("timeframe")),
                "days_remaining": days_remaining,
                "needs_verdict": needs_verdict,
                "time_signal": "verdict due" if needs_verdict else (
                    f"{days_remaining}d left" if days_remaining is not None and days_remaining >= 0 else "trial window"
                ),
                "signal_arrow": signal["arrow"],
                "signal_tone": signal["tone"],
                "signal_label": signal["label"],
                "signal_breakdown": breakdown,
                "entry": current_entry,
                "recent_entries": recent_entries,
                "suggested_verdict": metrics_engine.suggest_verdict(exp_entries, _experiment_timeframe_days(exp.get("timeframe"))) if needs_verdict else None,
                "events": events,
            })
    for rows in out.values():
        rows.sort(key=lambda item: (0 if item.get("needs_verdict") else 1, item.get("ends_at") or "", item.get("action") or ""))
    return out


def _experiment_day_summary(experiments: list[dict]) -> dict | None:
    if not experiments:
        return None
    active = sum(1 for exp in experiments if exp.get("status") == "running" and not exp.get("needs_verdict"))
    verdict_due = sum(1 for exp in experiments if exp.get("needs_verdict"))
    touched = sum(1 for exp in experiments if exp.get("entry"))
    return {
        "count": len(experiments),
        "active": active,
        "verdict_due": verdict_due,
        "touched": touched,
        "status": f"{active} active · {verdict_due} verdict due" if verdict_due else f"{active} active",
    }


def _timeline_day_title_meta(day: dict) -> dict:
    entries = day["entries"]
    quests = day["quests"]
    challenges = day["challenges"]
    saga_entries = [entry for entry in entries if entry.get("type") != "challenge_reflection"]
    latest = saga_entries[-1] if saga_entries else None
    bits = [
        _count_label(len(entries), "entry", "entries"),
        _count_label(len(quests), "quest"),
        _count_label(len(challenges), "trial"),
    ]
    if day.get("experiments"):
        bits.append(_count_label(len(day["experiments"]), "experiment"))
    if latest:
        bits.insert(1, f"latest {latest['mood_word']} E:{latest['energy']} P:{latest['pleasantness']}")
    return {
        "title_meta": bits,
        "latest_mood": latest["mood_word"] if latest else None,
        "latest_energy": latest["energy"] if latest else None,
        "latest_pleasantness": latest["pleasantness"] if latest else None,
        "latest_mood_accent": latest["quadrant_accent"] if latest else "#CF9D7B",
    }


async def timeline_days(db: aiosqlite.Connection, page: int = 1, per_page: int = 14) -> dict:
    """Build populated day cards for the Saga vertical timeline."""
    today = today_local()
    start = today - timedelta(days=370)
    days: dict[str, dict] = {}

    saga_cursor = await db.execute(
        "SELECT id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note "
        "FROM saga_entries WHERE local_date >= ? ORDER BY timestamp",
        (start.isoformat(),),
    )
    for row in await saga_cursor.fetchall():
        day = days.setdefault(row[2], _empty_timeline_day(row[2]))
        energy = int(row[3] or 0)
        pleasantness = int(row[4] or 0)
        distance = math.sqrt((energy * energy) + (pleasantness * pleasantness))
        strength = min(100, int(round((distance / math.sqrt(98)) * 100)))
        day["entries"].append({
            "id": row[0],
            "type": "saga",
            "sort_at": row[1],
            "time": display_time(row[1]),
            "note_html": render_markdown_note(row[7]),
            "energy": energy,
            "pleasantness": pleasantness,
            "quadrant": row[5],
            "quadrant_label": QUADRANT_LABELS.get(row[5], str(row[5]).title()),
            "quadrant_accent": QUADRANT_COLORS.get(row[5], "#CF9D7B"),
            "mood_word": row[6],
            "mood_strength": strength,
            "mood_wash_pct": min(24, 5 + int(strength * 0.18)),
            "mood_glow_pct": min(28, 6 + int(strength * 0.20)),
            "mood_chip_pct": min(26, 7 + int(strength * 0.18)),
        })

    quest_cursor = await db.execute(
        "SELECT q.id, q.title, q.completed_at, q.project, q.labels, w.name "
        "FROM quests q LEFT JOIN workspaces w ON w.id = q.workspace_id "
        "WHERE q.status = 'done' AND q.completed_at IS NOT NULL"
    )
    for row in await quest_cursor.fetchall():
        local_date = to_local_date(row[2])
        if local_date < start.isoformat():
            continue
        day = days.setdefault(local_date, _empty_timeline_day(local_date))
        day["quests"].append({
            "id": row[0],
            "time": display_time(row[2]),
            "title": row[1],
            "status": "Done",
            "project": row[3],
            "labels": display_labels(row[4]),
            "workspace": row[5],
        })

    hard90_cursor = await db.execute(
        "SELECT e.id, e.created_at, e.log_date, e.state, e.notes, t.name, t.bucket, c.era_name "
        "FROM challenge_entries e "
        "JOIN challenge_tasks t ON t.id = e.task_id "
        "JOIN challenges c ON c.id = e.challenge_id "
        "WHERE e.log_date >= ? "
        "ORDER BY e.log_date, e.created_at, t.name",
        (start.isoformat(),),
    )
    for row in await hard90_cursor.fetchall():
        timestamp = row[1] or _date_fallback_timestamp(row[2], time(20, 0))
        state_key = row[3]
        day = days.setdefault(row[2], _empty_timeline_day(row[2]))
        note = (row[4] or "").strip()
        if note:
            reflection = {
                "id": f"challenge-reflection-{row[0]}",
                "type": "challenge_reflection",
                "sort_at": timestamp,
                "time": display_time(timestamp),
                "task_title": row[5],
                "bucket": row[6],
                "state_short": _challenge_state_short(state_key),
                "state_tone": _challenge_state_tone(state_key),
                "note_html": render_markdown_note(note),
            }
            day["challenge_reflections"].append(reflection)
            day["entries"].append(reflection)
        if state_key:
            day["challenges"].append({
                "id": row[0],
                "time": display_time(timestamp),
                "title": row[5],
                "state_key": state_key,
                "state": _challenge_state_label(state_key),
                "state_short": _challenge_state_short(state_key),
                "state_tone": _challenge_state_tone(state_key),
                "bucket": row[6],
                "era": row[7],
            })

    experiments_by_day = await _timeline_experiments_by_day(db, start, today)
    for local_date, experiments in experiments_by_day.items():
        day = days.setdefault(local_date, _empty_timeline_day(local_date))
        day["experiments"] = experiments

    ordered = []
    for local_date in sorted(days.keys(), reverse=True):
        day = days[local_date]
        day["entries"].sort(key=lambda item: item.get("sort_at") or "")
        day["challenges_signal"] = [
            item for item in day["challenges"]
            if item.get("state_key") != "COMPLETED_SATISFACTORY"
        ]
        day["challenges_done"] = [
            item for item in day["challenges"]
            if item.get("state_key") == "COMPLETED_SATISFACTORY"
        ]
        day["granularity"] = _timeline_granularity(local_date, today)
        day["quest_summary"] = _quest_day_summary(day["quests"])
        day["challenge_summary"] = _challenge_day_summary(day["challenges"])
        day["experiment_summary"] = _experiment_day_summary(day.get("experiments", []))
        day.update(_timeline_day_title_meta(day))
        ordered.append(day)

    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(30, int(per_page or 14)))
    start_index = (safe_page - 1) * safe_per_page
    end_index = start_index + safe_per_page
    return {
        "days": ordered[start_index:end_index],
        "page": safe_page,
        "per_page": safe_per_page,
        "has_prev": safe_page > 1,
        "has_next": end_index < len(ordered),
        "prev_page": safe_page - 1,
        "next_page": safe_page + 1,
        "total": len(ordered),
    }


def grouped_events(events: list[dict]) -> list[dict]:
    groups = []
    by_block: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_block[event["block"]].append(event)
    for block in ("Morning", "Afternoon", "Evening", "Night"):
        groups.append({"label": block, "events": by_block.get(block, [])})
    return groups


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _band(value: float, cuts: tuple[float, float, float], names: tuple[str, str, str, str]) -> str:
    if value < cuts[0]:
        return names[0]
    if value < cuts[1]:
        return names[1]
    if value < cuts[2]:
        return names[2]
    return names[3]


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _local_date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return parse_iso(value).date() if parse_iso(value) else None
        except ValueError:
            return None


def _quest_age_days(quest: dict) -> int:
    completed = _local_date_from_iso(quest.get("completed_at"))
    created = _local_date_from_iso(quest.get("created_at")) or _local_date_from_iso(quest.get("started_at"))
    if not completed or not created:
        return 0
    return max(0, (completed - created).days)


def _quest_age_multiplier(age_days: int) -> float:
    if age_days >= 14:
        return 1.40
    if age_days >= 7:
        return 1.25
    if age_days >= 2:
        return 1.10
    return 1.00


def _quest_weight(quest: dict) -> float:
    priority = max(0, min(4, _safe_int(quest.get("priority"), 4)))
    priority_weight = QUEST_PRIORITY_WEIGHTS.get(priority, QUEST_PRIORITY_WEIGHTS[4])
    frog_multiplier = QUEST_FROG_MULTIPLIER if quest.get("frog") else 1.00
    age_multiplier = _quest_age_multiplier(_quest_age_days(quest))
    return round(priority_weight * frog_multiplier * age_multiplier, 2)


def _challenge_state_score(state: str | None) -> int:
    rank = STATE_RANK.get(state or "", 1)
    return int(round(((rank - 1) / 4) * 100))


def _weighted_average(rows: list[tuple[float | int | None, float | int]]) -> float | None:
    weighted = [(float(score), float(weight)) for score, weight in rows if score is not None and weight]
    total_weight = sum(weight for _score, weight in weighted)
    if not total_weight:
        return None
    return sum(score * weight for score, weight in weighted) / total_weight


def _score_component(
    label: str,
    weight: int,
    score: float | int | None,
    inputs: list[str],
    rationale: str,
) -> dict:
    resolved = _clamp(score or 0)
    return {
        "label": label,
        "weight": weight,
        "score": int(round(resolved)),
        "contribution": round((resolved * weight) / 100, 1),
        "inputs": inputs,
        "rationale": rationale,
    }


def _weighted_score(components: list[dict]) -> float:
    total_weight = sum(component["weight"] for component in components)
    if not total_weight:
        return 0
    return _clamp(sum(component["score"] * component["weight"] for component in components) / total_weight)


def _challenge_integrity(challenges: list[dict]) -> dict:
    tracked = [item for item in challenges if item.get("bucket") in TRACKED_BUCKETS]
    rows = tracked or challenges
    if not rows:
        return {
            "score": None,
            "label": "No signal",
            "count": 0,
            "held": 0,
            "weak": 0,
            "bucket_rows": [],
            "raw_rows": [],
        }

    scores = [_challenge_state_score(item.get("state")) for item in rows]
    held = sum(1 for item in rows if item["state"] == "COMPLETED_SATISFACTORY")
    weak = sum(1 for item in rows if STATE_RANK.get(item["state"], 1) <= 3)
    buckets: dict[str, list[int]] = defaultdict(list)
    for item in rows:
        buckets[item["bucket"]].append(_challenge_state_score(item.get("state")))
    bucket_rows = [
        {
            "bucket": bucket,
            "label": bucket.title(),
            "score": int(round(mean(ranks))),
            "count": len(ranks),
            "weight": CHALLENGE_BUCKET_WEIGHTS.get(bucket, 0),
        }
        for bucket, ranks in sorted(buckets.items())
    ]
    weighted_score = _weighted_average([
        (row["score"], CHALLENGE_BUCKET_WEIGHTS.get(row["bucket"], 0))
        for row in bucket_rows
        if row["bucket"] in CHALLENGE_BUCKET_WEIGHTS
    ])
    score = int(round(weighted_score if weighted_score is not None else mean(scores)))
    return {
        "score": score,
        "label": _band(score, (45, 70, 86), ("Frayed", "Mixed", "Held", "Clean")),
        "count": len(rows),
        "held": held,
        "weak": weak,
        "bucket_rows": bucket_rows,
        "raw_rows": rows,
    }


def _dominant(items: list[str | None]) -> str | None:
    counts = Counter(item for item in items if item)
    return counts.most_common(1)[0][0] if counts else None


def _saga_day_profile(
    local_date: str,
    entries: list[dict],
    quests: list[dict],
    challenges: list[dict],
    quest_baseline: float,
) -> dict:
    energies = [int(entry["energy"]) for entry in entries]
    pleasantness_values = [int(entry["pleasantness"]) for entry in entries]
    avg_energy = round(mean(energies), 1) if energies else 0
    avg_pleasantness = round(mean(pleasantness_values), 1) if pleasantness_values else 0
    quadrant_distribution = {quadrant: 0 for quadrant in QUADRANT_ORDER}
    for entry in entries:
        quadrant_distribution[entry["quadrant"]] = quadrant_distribution.get(entry["quadrant"], 0) + 1
    dominant_quadrant = _dominant([entry.get("quadrant") for entry in entries])
    if entries:
        centroid_energy = mean(energies)
        centroid_pleasantness = mean(pleasantness_values)
        distances = [
            math.sqrt((entry["energy"] - centroid_energy) ** 2 + (entry["pleasantness"] - centroid_pleasantness) ** 2)
            for entry in entries
        ]
        if len(distances) > 1:
            volatility = round(math.sqrt(mean(distance ** 2 for distance in distances)), 2)
        else:
            volatility = 0
    else:
        volatility = 0
    quadrant_switches = sum(
        1
        for previous, current in zip(entries, entries[1:])
        if previous.get("quadrant") != current.get("quadrant")
    )
    entry_count = len(entries)
    if entry_count:
        red_share = quadrant_distribution.get("red", 0) / entry_count
        blue_share = quadrant_distribution.get("blue", 0) / entry_count
        green_share = quadrant_distribution.get("green", 0) / entry_count
        severe_cell_pressure = mean(
            max(0, ((-int(entry["pleasantness"]) - 4) / 3))
            for entry in entries
        ) * 18
        unpleasant_pressure = max(0, ((-avg_pleasantness - 2) / 5)) * 24
        activation_pressure = max(0, ((avg_energy - 3) / 4)) * 14
        depletion_pressure = max(0, ((-avg_energy - 3) / 4)) * 10
        volatility_pressure = min(volatility / 7, 1) * 18
        quadrant_pressure = max(0, red_share - 0.35) * 10 + max(0, blue_share - 0.45) * 8 - green_share * 4
        switch_pressure = min(quadrant_switches, 4) * 2
        mood_load = int(round(_clamp(
            unpleasant_pressure
            + activation_pressure
            + depletion_pressure
            + severe_cell_pressure
            + volatility_pressure
            + quadrant_pressure
            + switch_pressure
        )))
    else:
        mood_load = 0
    dominant_label = _dominant([entry.get("mood_word") for entry in entries])
    top_mood_words = [
        {"label": label, "count": count}
        for label, count in Counter(entry.get("mood_word") for entry in entries if entry.get("mood_word")).most_common(3)
    ]
    latest = entries[-1] if entries else None

    quest_count = len(quests)
    quest_weight = round(sum(_quest_weight(quest) for quest in quests), 1)
    baseline = max(quest_baseline, 1)
    output_index = int(round(_clamp((quest_weight / baseline) * 50))) if quest_count else 0
    output_delta = int(round(((quest_weight - quest_baseline) / baseline) * 100)) if baseline else 0
    output_label = _band(output_index, (25, 55, 80), ("Sparse", "Light", "Above Base", "Surging"))

    challenge = _challenge_integrity(challenges)
    challenge_score = challenge["score"]
    if challenge_score is None:
        alignment_score = None
    else:
        alignment_score = int(round((output_index * 0.45) + (challenge_score * 0.55)))

    relations = _day_relations(mood_load, output_index, challenge_score, quest_count, len(entries))
    archetype = _day_archetype(
        mood_load,
        output_index,
        challenge_score,
        quest_count,
        len(entries),
        dominant_quadrant,
        avg_energy,
        avg_pleasantness,
    )

    day = date.fromisoformat(local_date)
    accent = QUADRANT_COLORS.get(dominant_quadrant or "", "#CF9D7B")
    return {
        "date": local_date,
        "label": day.strftime("%b %d"),
        "weekday": day.strftime("%A"),
        "archetype": archetype,
        "verdict": _day_verdict(archetype, relations),
        "saga": {
            "entry_count": len(entries),
            "avg_energy": avg_energy,
            "avg_pleasantness": avg_pleasantness,
            "volatility": volatility,
            "quadrant_switches": quadrant_switches,
            "mood_load": mood_load,
            "load_label": _band(mood_load, (25, 50, 70), ("Settled", "Activated", "Taxed", "Overloaded")),
            "dominant_quadrant": dominant_quadrant,
            "quadrant_distribution": quadrant_distribution,
            "dominant_label": dominant_label,
            "top_mood_words": top_mood_words,
            "latest_label": latest["mood_word"] if latest else None,
            "latest_energy": latest["energy"] if latest else None,
            "latest_pleasantness": latest["pleasantness"] if latest else None,
            "accent": accent,
        },
        "quest": {
            "count": quest_count,
            "weighted": quest_weight,
            "baseline": round(quest_baseline, 1),
            "output_index": output_index,
            "delta_pct": output_delta,
            "label": output_label,
            "frog_count": sum(1 for quest in quests if quest.get("frog")),
        },
        "quest_items": quests,
        "challenge": challenge,
        "alignment": {
            "score": alignment_score,
            "label": _alignment_label(output_index, challenge_score),
        },
        "relations": relations,
    }


def _entry_emotion_mentions(entry: dict) -> list[dict]:
    if not entry.get("mood_word"):
        return []
    return [{
        "quadrant": entry.get("quadrant"),
        "label": entry.get("mood_word"),
        "energy": entry.get("energy", 0),
        "pleasantness": entry.get("pleasantness", 0),
        "timestamp": entry.get("timestamp"),
        "role": "primary",
    }]


def _day_relations(
    mood_load: int,
    output_index: int,
    challenge_score: int | None,
    quest_count: int,
    entry_count: int,
) -> dict:
    if mood_load >= 65 and output_index >= 55:
        emotion_quest = "Output held under mood load"
    elif mood_load >= 65:
        emotion_quest = "Mood load consumed execution"
    elif mood_load < 30 and output_index >= 55:
        emotion_quest = "Quiet execution"
    elif entry_count == 0 and quest_count == 0:
        emotion_quest = "Low capture, low output"
    else:
        emotion_quest = "Mood and output moved evenly"

    if challenge_score is None:
        emotion_challenge = "Challenge signal missing"
    elif mood_load >= 65 and challenge_score >= 75:
        emotion_challenge = "Discipline held under load"
    elif mood_load >= 65 and challenge_score < 65:
        emotion_challenge = "Mood load reached long-term systems"
    elif mood_load < 30 and challenge_score < 60:
        emotion_challenge = "Calm did not protect discipline"
    else:
        emotion_challenge = "Long-term posture tracked the mood field"

    quest_challenge = _alignment_label(output_index, challenge_score)
    return {
        "emotion_quest": emotion_quest,
        "emotion_challenge": emotion_challenge,
        "quest_challenge": quest_challenge,
    }


def _alignment_label(output_index: int, challenge_score: int | None) -> str:
    if challenge_score is None:
        return "Challenge signal missing"
    if output_index >= 55 and challenge_score >= 75:
        return "Aligned progress"
    if output_index >= 55 and challenge_score < 65:
        return "Busy drift"
    if output_index < 40 and challenge_score >= 75:
        return "Discipline held, output light"
    if output_index < 35 and challenge_score < 60:
        return "Systems underfed"
    return "Mixed alignment"


def _day_archetype(
    mood_load: int,
    output_index: int,
    challenge_score: int | None,
    quest_count: int,
    entry_count: int,
    dominant_quadrant: str | None,
    avg_energy: float,
    avg_pleasantness: float,
) -> str:
    if entry_count == 0 and quest_count == 0 and challenge_score is None:
        return "No Signal"
    if output_index >= 55 and challenge_score is not None and challenge_score < 65:
        return "Busy Drift"
    if mood_load < 65 and output_index >= 55 and challenge_score is not None and challenge_score >= 75:
        return "Clean Alignment"
    if mood_load >= 65:
        if dominant_quadrant == "red" and output_index >= 55 and (challenge_score is None or challenge_score >= 70):
            return "Hellfire Forge"
        if dominant_quadrant == "red" or avg_energy > 0:
            return "Hellfire Spillover"
        return "Abyss Drag"
    if dominant_quadrant == "green":
        return "Sanctuary Reset"
    if dominant_quadrant == "yellow":
        return "Radiance Spark"
    if dominant_quadrant == "blue" or avg_pleasantness < 0:
        return "Abyss Drag"
    return "Sanctuary Reset"


def _day_verdict(archetype: str, relations: dict) -> str:
    verdicts = {
        "Clean Alignment": "Mood, output, and long-term systems moved together.",
        "Hellfire Forge": "High-energy unpleasantness was converted into execution without breaking the long game.",
        "Hellfire Spillover": "Activated unpleasantness is pressing into the rest of the system.",
        "Abyss Drag": "Low-energy unpleasantness is weighing on motion and recovery.",
        "Sanctuary Reset": "The system is downshifting into steadier, more regulated territory.",
        "Radiance Spark": "Pleasant activation is available; useful momentum can be harvested.",
        "Busy Drift": "Quest motion outpaced long-term alignment.",
        "Recovery Turn": "The system downshifted after pressure while preserving long-term posture.",
        "No Signal": "Capture emotion, complete quests, or log challenge progress to begin the field report.",
    }
    return verdicts.get(archetype, f"{relations['emotion_quest']}. {relations['quest_challenge']}.")


def _apply_recovery_archetypes(day_profiles: list[dict]) -> None:
    for idx in range(1, len(day_profiles)):
        previous = day_profiles[idx - 1]
        current = day_profiles[idx]
        challenge_score = current["challenge"]["score"]
        if (
            previous["saga"]["mood_load"] >= 65
            and current["saga"]["mood_load"] < 55
            and current["quest"]["output_index"] < previous["quest"]["output_index"]
            and challenge_score is not None
            and challenge_score >= 70
        ):
            current["archetype"] = "Recovery Turn"
            current["verdict"] = _day_verdict("Recovery Turn", current["relations"])


def _saga_relationship_trends(day_profiles: list[dict]) -> dict:
    active_days = [
        day for day in day_profiles
        if day["saga"]["entry_count"] or day["quest"]["count"] or day["challenge"]["count"]
    ]
    if not active_days:
        return {
            "common_archetype": "No signal",
            "arc": [],
            "pressure_output": "More days are needed before relationships become visible.",
            "keystone_mood": None,
            "risk_mood": None,
            "recovery": "Recovery signal is still forming.",
        }

    archetype_counts = Counter(day["archetype"] for day in active_days)
    common_archetype = archetype_counts.most_common(1)[0][0]
    arc = [
        {"date": day["label"], "archetype": day["archetype"], "accent": day["saga"]["accent"]}
        for day in active_days[-5:]
    ]
    high_load = [day for day in active_days if day["saga"]["mood_load"] >= 65]
    all_quest_avg = mean(day["quest"]["count"] for day in active_days)
    if high_load:
        high_quest_avg = mean(day["quest"]["count"] for day in high_load)
        if high_quest_avg > all_quest_avg + 0.25:
            pressure_output = "High-load days are producing more Quest output than the baseline."
        elif high_quest_avg < all_quest_avg - 0.25:
            pressure_output = "High-load days are suppressing Quest output against the baseline."
        else:
            pressure_output = "High-load days are tracking close to normal Quest output."
    else:
        pressure_output = "No high-load days in this window yet."

    mood_scores: dict[str, list[float]] = defaultdict(list)
    for day in active_days:
        quadrant = day["saga"]["dominant_quadrant"]
        challenge_score = day["challenge"]["score"]
        if not quadrant or challenge_score is None:
            continue
        mood_scores[quadrant].append(day["quest"]["output_index"] * 0.45 + challenge_score * 0.55)
    resolved = [(quadrant, mean(scores), len(scores)) for quadrant, scores in mood_scores.items() if len(scores) >= 2]
    keystone = max(resolved, key=lambda item: item[1], default=None)
    risk = min(resolved, key=lambda item: item[1], default=None)

    recoveries = []
    for idx, day in enumerate(day_profiles[:-1]):
        if day["saga"]["mood_load"] < 65:
            continue
        for distance, future in enumerate(day_profiles[idx + 1: idx + 5], start=1):
            if future["saga"]["mood_load"] < 55:
                recoveries.append(distance)
                break
    if recoveries:
        recovery = f"After high-load days, mood load cools in about {round(mean(recoveries), 1)} days."
    else:
        recovery = "Recovery signal is still forming."

    return {
        "common_archetype": common_archetype,
        "arc": arc,
        "pressure_output": pressure_output,
        "keystone_mood": QUADRANT_LABELS.get(keystone[0], keystone[0].title()) if keystone else None,
        "risk_mood": QUADRANT_LABELS.get(risk[0], risk[0].title()) if risk else None,
        "recovery": recovery,
    }


async def saga_metrics(db: aiosqlite.Connection, days: int = 7) -> dict:
    bundle = await _collect_window(db, days)
    calendar_days = bundle["calendar_days"]
    saga_by_day = bundle["saga_by_day"]
    quests_by_day = bundle["quests_by_day"]
    family_counts = bundle["family_counts"]
    label_counts = bundle["label_counts"]
    day_profiles = bundle["day_profiles"]

    heatmap = []
    by_profile = {day["date"]: day for day in day_profiles}
    for key in calendar_days:
        current = date.fromisoformat(key)
        profile = by_profile[key]
        values = saga_by_day.get(key, [])
        load = profile["saga"]["mood_load"]
        if not values:
            level = "empty"
        elif load <= 25:
            level = "low"
        elif load <= 50:
            level = "mid"
        elif load <= 70:
            level = "high"
        else:
            level = "peak"
        heatmap.append({
            "date": key,
            "day": current.day,
            "count": len(values),
            "average": load,
            "variance": profile["saga"]["volatility"],
            "level": level,
        })

    day_averages = [
        profile["saga"]["mood_load"]
        for profile in day_profiles
        if profile["saga"]["entry_count"]
    ]
    if len(day_averages) > 1:
        drift = [abs(day_averages[i] - day_averages[i - 1]) for i in range(1, len(day_averages))]
        volatility = round(mean(drift), 1)
    else:
        volatility = 0
    stability = "Stable" if volatility < 1.5 else "Variable" if volatility < 3 else "Volatile"

    quest_counts = [len(quests_by_day.get(day, [])) for day in calendar_days]
    high_load_days = [
        profile["date"] for profile in day_profiles
        if profile["saga"]["mood_load"] >= 65
    ]
    if high_load_days:
        high_avg = mean(len(quests_by_day.get(day, [])) for day in high_load_days)
        all_avg = mean(quest_counts) if quest_counts else 0
        if high_avg > all_avg:
            correlation = "High-load mood days are currently paired with more Questlog completions."
        elif high_avg < all_avg:
            correlation = "High-load mood days are currently paired with fewer Questlog completions."
        else:
            correlation = "High-load mood days are tracking close to your usual Questlog completion rate."
    else:
        correlation = "Capture a few high-load moments to unlock correlation hints."

    total = sum(family_counts.values())
    distribution = [
        {
            "quadrant": quadrant,
            "label": QUADRANT_LABELS[quadrant],
            "count": family_counts.get(quadrant, 0),
            "pct": round((family_counts.get(quadrant, 0) / total) * 100) if total else 0,
        }
        for quadrant in QUADRANT_ORDER
    ]
    latest_profiles = list(reversed(day_profiles))

    return {
        "heatmap": heatmap,
        "distribution": distribution,
        "top_labels": label_counts.most_common(5),
        "stability": stability,
        "volatility": volatility,
        "correlation": correlation,
        "total_entries": len(bundle["raw_rows"]),
        "total_mood_mentions": total,
        "current": latest_profiles[0] if latest_profiles else None,
        "recent_days": latest_profiles[:7],
        "trends": _saga_relationship_trends(day_profiles),
        "range_days": days,
    }


async def _collect_window(db: aiosqlite.Connection, days: int) -> dict:
    end = today_local()
    start = end - timedelta(days=days - 1)
    cursor = await db.execute(
        "SELECT local_date, timestamp, energy, pleasantness, quadrant, mood_word "
        "FROM saga_entries WHERE local_date >= ? ORDER BY local_date, timestamp",
        (start.isoformat(),),
    )
    rows = await cursor.fetchall()
    saga_by_day: dict[str, list[dict]] = defaultdict(list)
    raw_rows: list[dict] = []
    family_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for row in rows:
        record = {
            "date": row[0],
            "timestamp": row[1],
            "energy": int(row[2] or 0),
            "pleasantness": int(row[3] or 0),
            "quadrant": row[4],
            "mood_word": row[5],
        }
        saga_by_day[row[0]].append(record)
        raw_rows.append(record)
        for mention in _entry_emotion_mentions(record):
            family_counts[mention["quadrant"]] += 1
            if mention["label"]:
                label_counts[mention["label"]] += 1

    quest_cursor = await db.execute(
        "SELECT id, title, created_at, started_at, completed_at, frog, priority, project, labels, workspace_id "
        "FROM quests WHERE status = 'done' AND completed_at IS NOT NULL"
    )
    quests_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in await quest_cursor.fetchall():
        local_date = to_local_date(row[4])
        if local_date < start.isoformat() or local_date > end.isoformat():
            continue
        quests_by_day[local_date].append({
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "frog": bool(row[5]),
            "priority": row[6] if row[6] is not None else 4,
            "project": row[7],
            "labels": display_labels(row[8]),
            "workspace": row[9],
        })

    pomo_cursor = await db.execute(
        "SELECT s.id, s.quest_id, s.quest_title, s.started_at, s.ended_at, "
        "s.actual_pomos, s.status, s.streak_peak, s.total_interruptions, "
        "sg.type, sg.completed, sg.interruptions, sg.started_at, sg.ended_at, "
        "sg.early_completion, sg.forge_type "
        "FROM pomo_sessions s "
        "LEFT JOIN pomo_segments sg ON sg.session_id = s.id "
        "WHERE COALESCE(s.started_at, sg.started_at) >= ? "
        "ORDER BY COALESCE(s.started_at, sg.started_at)",
        (start.isoformat(),),
    )
    pomo_by_day: dict[str, dict] = defaultdict(lambda: {
        "actual_pomos": 0,
        "work_segments": 0,
        "completed_work_segments": 0,
        "interruptions": 0,
        "hollow": 0,
        "berserker": 0,
        "focus_sessions": set(),
        "quest_titles": set(),
    })
    session_seen: set[str] = set()
    for row in await pomo_cursor.fetchall():
        local_date = to_local_date(row[12] or row[3])
        if local_date < start.isoformat() or local_date > end.isoformat():
            continue
        day = pomo_by_day[local_date]
        session_id = row[0]
        if session_id not in session_seen:
            session_seen.add(session_id)
            day["actual_pomos"] += int(row[5] or 0)
            if row[2]:
                day["quest_titles"].add(row[2])
            if (row[5] or 0) > 0:
                day["focus_sessions"].add(session_id)
        if row[9] == "work":
            day["work_segments"] += 1
            if row[10]:
                day["completed_work_segments"] += 1
            day["interruptions"] += int(row[11] or 0)
            if row[15] == "hollow":
                day["hollow"] += 1
            elif row[15] == "berserker":
                day["berserker"] += 1

    challenge_cursor = await db.execute(
        "SELECT e.id, e.log_date, e.state, t.bucket, t.name, c.era_name "
        "FROM challenge_entries e "
        "JOIN challenge_tasks t ON t.id = e.task_id "
        "JOIN challenges c ON c.id = e.challenge_id "
        "WHERE e.log_date >= ? AND e.log_date <= ? "
        "AND e.state IS NOT NULL "
        "ORDER BY e.log_date, e.created_at, t.name",
        (start.isoformat(), end.isoformat()),
    )
    challenges_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in await challenge_cursor.fetchall():
        challenges_by_day[row[1]].append({
            "id": row[0],
            "date": row[1],
            "state": row[2],
            "bucket": row[3],
            "name": row[4],
            "era": row[5],
        })

    exp_cursor = await db.execute(
        "SELECT e.id, e.action, e.status, e.started_at, e.ends_at, e.verdict, "
        "e.created_at, e.observation_notes, e.conclusion_notes, ee.log_date, ee.state, ee.notes "
        "FROM challenge_experiments e "
        "LEFT JOIN challenge_experiment_entries ee ON ee.experiment_id = e.id "
        "WHERE COALESCE(e.started_at, e.created_at) <= ? "
        "   OR ee.log_date >= ? "
        "ORDER BY COALESCE(e.started_at, e.created_at), ee.log_date",
        (end.isoformat(), start.isoformat()),
    )
    experiments_by_id: dict[str, dict] = {}
    experiments_by_day: dict[str, dict] = defaultdict(lambda: {
        "active": 0,
        "started": 0,
        "touched": 0,
        "verdict_due": 0,
        "judged": 0,
        "abandoned": 0,
        "logged": 0,
    })
    for row in await exp_cursor.fetchall():
        exp = experiments_by_id.setdefault(row[0], {
            "id": row[0],
            "action": row[1],
            "status": row[2],
            "started_at": row[3],
            "ends_at": row[4],
            "verdict": row[5],
            "created_at": row[6],
            "observation_notes": row[7],
            "conclusion_notes": row[8],
            "entries": [],
        })
        if row[9]:
            exp["entries"].append({
                "log_date": row[9],
                "state": row[10],
                "notes": row[11],
            })

    for exp in experiments_by_id.values():
        if exp.get("started_at") and start.isoformat() <= exp["started_at"] <= end.isoformat():
            experiments_by_day[exp["started_at"]]["started"] += 1
        if exp.get("status") == "judged" and exp.get("ends_at") and start.isoformat() <= exp["ends_at"] <= end.isoformat():
            experiments_by_day[exp["ends_at"]]["judged"] += 1
        if exp.get("status") == "abandoned" and exp.get("ends_at") and start.isoformat() <= exp["ends_at"] <= end.isoformat():
            experiments_by_day[exp["ends_at"]]["abandoned"] += 1
        if exp.get("status") == "running" and exp.get("started_at"):
            try:
                active_start = max(date.fromisoformat(exp["started_at"]), start)
                active_end = min(date.fromisoformat(exp.get("ends_at") or end.isoformat()), end)
                if active_end >= active_start:
                    for offset in range((active_end - active_start).days + 1):
                        local_date = (active_start + timedelta(days=offset)).isoformat()
                        experiments_by_day[local_date]["active"] += 1
                if exp.get("ends_at") and date.fromisoformat(exp["ends_at"]) < end:
                    experiments_by_day[end.isoformat()]["verdict_due"] += 1
            except ValueError:
                pass
        for entry in exp["entries"]:
            local_date = entry["log_date"]
            if start.isoformat() <= local_date <= end.isoformat():
                experiments_by_day[local_date]["touched"] += 1
                experiments_by_day[local_date]["logged"] += 1

    calendar_days = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]
    for day in calendar_days:
        if day in pomo_by_day:
            pomo_by_day[day]["focus_days"] = 1 if pomo_by_day[day]["actual_pomos"] or pomo_by_day[day]["completed_work_segments"] else 0
            pomo_by_day[day]["quest_titles"] = sorted(pomo_by_day[day]["quest_titles"])[:3]
            pomo_by_day[day]["focus_sessions"] = len(pomo_by_day[day]["focus_sessions"])
        else:
            pomo_by_day[day] = {
                "actual_pomos": 0,
                "work_segments": 0,
                "completed_work_segments": 0,
                "interruptions": 0,
                "hollow": 0,
                "berserker": 0,
                "focus_sessions": 0,
                "focus_days": 0,
                "quest_titles": [],
            }
        experiments_by_day[day] = dict(experiments_by_day.get(day, {
            "active": 0,
            "started": 0,
            "touched": 0,
            "verdict_due": 0,
            "judged": 0,
            "abandoned": 0,
            "logged": 0,
        }))
    quest_quality_totals = [sum(_quest_weight(quest) for quest in quests_by_day.get(day, [])) for day in calendar_days]
    quest_baseline = mean(quest_quality_totals[:-1]) if len(quest_quality_totals) > 1 else 0
    day_profiles = [
        _saga_day_profile(
            day,
            saga_by_day.get(day, []),
            quests_by_day.get(day, []),
            challenges_by_day.get(day, []),
            quest_baseline,
        )
        for day in calendar_days
    ]
    _apply_recovery_archetypes(day_profiles)
    for profile in day_profiles:
        weighted = _field_report_day_scores(
            profile,
            pomo_by_day.get(profile["date"], {}),
            experiments_by_day.get(profile["date"], {}),
        )
        profile["field_report"] = weighted
        if weighted["alignment"] is not None:
            profile["alignment"] = {
                "score": int(round(weighted["alignment"])),
                "label": _alignment_label(int(round(weighted["daily_execution"] or 0)), int(round(weighted["long_game"] or 0))),
            }
    return {
        "start": start,
        "end": end,
        "calendar_days": calendar_days,
        "saga_by_day": saga_by_day,
        "quests_by_day": quests_by_day,
        "pomo_by_day": pomo_by_day,
        "challenges_by_day": challenges_by_day,
        "experiments_by_day": experiments_by_day,
        "experiments": list(experiments_by_id.values()),
        "raw_rows": raw_rows,
        "day_profiles": day_profiles,
        "family_counts": family_counts,
        "label_counts": label_counts,
    }


def _kpi_tile(values: list[int | float | None]) -> dict:
    """Build KPI tile from a daily series. None values are gaps."""
    spark_window = values[-7:] if len(values) >= 7 else ([None] * (7 - len(values))) + values[:]
    spark = [(v if v is not None else 0) for v in spark_window]
    nums = [v for v in values if v is not None]
    if not nums:
        return {"value": None, "spark": spark, "delta_pct": 0, "trend_label": "no signal"}
    today_val = next((v for v in reversed(values) if v is not None), None)
    if today_val is None:
        return {"value": None, "spark": spark, "delta_pct": 0, "trend_label": "no signal"}
    prior = [v for v in values[:-1] if v is not None]
    baseline = mean(prior) if prior else today_val
    delta_pct = int(round(((today_val - baseline) / baseline) * 100)) if baseline else 0
    trend_label = "steady"
    if delta_pct >= 12:
        trend_label = "rising"
    elif delta_pct <= -12:
        trend_label = "falling"
    return {
        "value": int(round(today_val)),
        "spark": [round(float(v), 1) for v in spark],
        "delta_pct": delta_pct,
        "baseline": int(round(baseline)),
        "trend_label": trend_label,
    }


def _kpi_series(values: list[int | float | None], days_window: int | None = None) -> dict:
    return _kpi_tile(values)


def _streak(values: list[bool]) -> dict:
    current = 0
    for v in reversed(values):
        if v:
            current += 1
        else:
            break
    best = 0
    run = 0
    for v in values:
        if v:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return {"current": current, "best": best}


def _streaks_for(predicate, day_profiles: list[dict]) -> dict:
    return _streak([bool(predicate(day)) for day in day_profiles])


def _mean_or_none(values: list[int | float | None]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    return round(mean(nums), 1) if nums else None


def _slope(values: list[int | float | None]) -> float | None:
    points = [(idx, float(value)) for idx, value in enumerate(values) if value is not None]
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_mean = mean(xs)
    y_mean = mean(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0
    return round(sum((x - x_mean) * (y - y_mean) for x, y in points) / denom, 2)


def _correlation(xs: list[int | float | None], ys: list[int | float | None]) -> float | None:
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]
    x_mean = mean(x_vals)
    y_mean = mean(y_vals)
    x_var = sum((x - x_mean) ** 2 for x in x_vals)
    y_var = sum((y - y_mean) ** 2 for y in y_vals)
    if x_var == 0 or y_var == 0:
        return None
    corr = sum((x - x_mean) * (y - y_mean) for x, y in pairs) / math.sqrt(x_var * y_var)
    return round(corr, 2)


def _longest_run(values: list[bool], target: bool = True) -> int:
    best = 0
    run = 0
    for value in values:
        if value is target:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _recovery_distances(day_profiles: list[dict]) -> list[int]:
    recoveries: list[int] = []
    for idx, day in enumerate(day_profiles[:-1]):
        if day["saga"]["mood_load"] < 65:
            continue
        for distance, future in enumerate(day_profiles[idx + 1: idx + 5], start=1):
            if future["saga"]["mood_load"] < 55:
                recoveries.append(distance)
                break
    return recoveries


def _risk_signals(day_profiles: list[dict]) -> list[dict]:
    signals: list[dict] = []
    vols = [p["saga"]["volatility"] for p in day_profiles[-14:] if p["saga"]["entry_count"]]
    if len(vols) >= 6:
        mid = len(vols) // 2
        first_avg = mean(vols[:mid]) if vols[:mid] else 0
        second_avg = mean(vols[mid:]) if vols[mid:] else 0
        if second_avg > first_avg + 0.5:
            signals.append({
                "kind": "volatility",
                "severity": "warn",
                "headline": "Volatility rising",
                "detail": f"Mood drift averaging {round(second_avg, 1)} recently vs {round(first_avg, 1)} earlier in window.",
            })

    last7 = day_profiles[-7:]
    busy = sum(1 for p in last7 if p["archetype"] == "Busy Drift")
    if busy >= 3:
        signals.append({
            "kind": "decoupling",
            "severity": "warn",
            "headline": "Output decoupling from alignment",
            "detail": f"{busy} of last 7 days landed in Busy Drift — execution outpaced long-term posture.",
        })

    if len(day_profiles) >= 14:
        bucket_now: dict[str, list[float]] = defaultdict(list)
        bucket_prev: dict[str, list[float]] = defaultdict(list)
        for p in day_profiles[-7:]:
            for br in p["challenge"]["bucket_rows"]:
                bucket_now[br["bucket"]].append(br["score"])
        for p in day_profiles[-14:-7]:
            for br in p["challenge"]["bucket_rows"]:
                bucket_prev[br["bucket"]].append(br["score"])
        for bucket, now_scores in bucket_now.items():
            prev_scores = bucket_prev.get(bucket, [])
            if now_scores and prev_scores:
                now_rank = mean((score / 25) + 1 for score in now_scores)
                prev_rank = mean((score / 25) + 1 for score in prev_scores)
                delta = now_rank - prev_rank
                if delta <= -0.5:
                    signals.append({
                        "kind": "bucket_decline",
                        "severity": "warn",
                        "headline": f"{bucket.title()} bucket slipping",
                        "detail": f"7-day posture down {round(abs(delta), 1)} ranks vs prior week.",
                    })

    if len(day_profiles) >= 8:
        half = len(day_profiles) // 2
        early = _recovery_distances(day_profiles[:half])
        late = _recovery_distances(day_profiles[half:])
        if early and late and mean(late) > mean(early) + 0.5:
            signals.append({
                "kind": "recovery_slowing",
                "severity": "warn",
                "headline": "Recovery slowing",
                "detail": f"Recent high-load days cool in ~{round(mean(late), 1)}d vs ~{round(mean(early), 1)}d earlier.",
            })

    longest_gap = 0
    run = 0
    for p in day_profiles:
        if p["saga"]["entry_count"] == 0:
            run += 1
            longest_gap = max(longest_gap, run)
        else:
            run = 0
    if longest_gap >= 3:
        signals.append({
            "kind": "capture_gap",
            "severity": "info",
            "headline": "Capture gaps in the window",
            "detail": f"Longest stretch without a Saga entry: {longest_gap} days.",
        })
    return signals[:4]


async def _experiment_verdict_due_count(db: aiosqlite.Connection, as_of: str) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM challenge_experiments "
        "WHERE status = 'running' AND ends_at IS NOT NULL AND date(ends_at) < date(?)",
        (as_of,),
    )
    row = await cursor.fetchone()
    return int(row[0] if row else 0)


def _dashboard_narrative(
    days: int,
    today_profile: dict | None,
    kpis: dict,
    trends: dict,
    meta_analysis: dict,
    risk_signals: list[dict],
    verdict_due_count: int,
) -> dict:
    grain = {7: "week", 35: "month", 90: "quarter", 365: "year"}.get(days, f"{days}d")
    challenge_value = kpis["challenge"].get("value")
    challenge_clause = (
        f"{today_profile['challenge']['label']} challenge band ({challenge_value})"
        if today_profile and challenge_value is not None
        else "an unscored challenge band"
    )
    dominant = meta_analysis.get("emotion_load", {}).get("dominant_quadrant") or "still forming"
    output_delta = kpis["output"].get("delta_pct") or 0
    output_direction = "up" if output_delta > 0 else "down" if output_delta < 0 else "steady"
    recovery = meta_analysis.get("recovery", {}).get("mean_recovery_distance")
    recovery_clause = (
        f"Recovery after high mood-load days averages {recovery} days."
        if recovery is not None
        else trends.get("recovery", "Recovery signal is still forming.")
    )
    state_sentence = (
        f"This {grain} you are in {challenge_clause}. "
        f"Your dominant mood quadrant is {dominant}, and output is {output_direction} "
        f"{abs(output_delta)}% versus the comparison window."
    )
    trend_sentence = f"{trends.get('pressure_output')} {recovery_clause}"

    signals: list[dict] = []
    keystone = trends.get("keystone_mood")
    if keystone:
        signals.append({
            "kind": "keystone_mood",
            "tone": "strength",
            "title": "Protect the keystone mood",
            "body": f"Your best output blend happens around {keystone}. Protect the blocks where it appears.",
        })
    risk = trends.get("risk_mood")
    if risk:
        signals.append({
            "kind": "risk_mood",
            "tone": "watch",
            "title": "Watch the risk mood",
            "body": f"{risk} is least associated with useful output in this window. Lighten the load when it dominates.",
        })
    if recovery is not None:
        tone = "watch" if meta_analysis.get("recovery", {}).get("recovery_slowing") else "steady"
        signals.append({
            "kind": "recovery",
            "tone": tone,
            "title": "Recovery cadence",
            "body": recovery_clause,
        })
    if today_profile and today_profile["quest"].get("frog_count") == 0:
        signals.append({
            "kind": "frog_streak",
            "tone": "watch",
            "title": "Frog streak needs attention",
            "body": "No frog is logged today. Put one high-leverage quest back on the board.",
        })
    if verdict_due_count:
        signals.append({
            "kind": "verdict_due",
            "tone": "watch",
            "title": "Experiment verdict due",
            "body": f"{verdict_due_count} Tiny Experiment{'s' if verdict_due_count != 1 else ''} need a verdict.",
            "href": "/challenge/experiments",
        })
    for signal in risk_signals:
        signals.append({
            "kind": signal.get("kind", "risk"),
            "tone": signal.get("severity", "watch"),
            "title": signal.get("headline", "Signal"),
            "body": signal.get("detail", ""),
        })

    return {
        "grain": grain,
        "state_sentence": state_sentence,
        "trend_sentence": trend_sentence,
        "signals": signals[:5],
    }


def _pillar(
    key: str,
    name: str,
    score: float | None,
    confidence: str,
    headline: str,
    numbers: list[dict],
    explainer: dict | None = None,
    tone: str | None = None,
) -> dict:
    resolved = int(round(_clamp(score or 0)))
    return {
        "key": key,
        "name": name,
        "score": resolved,
        "confidence": confidence,
        "headline": headline,
        "numbers": numbers,
        "explainer": explainer or {},
        "tone": tone or ("strong" if resolved >= 72 else "watch" if resolved >= 45 else "risk"),
    }


def _confidence(active: int, total: int) -> str:
    if total <= 0:
        return "low"
    coverage = active / total
    if coverage >= 0.7:
        return "high"
    if coverage >= 0.35:
        return "medium"
    return "low"


def _focus_quality_score(pomo: dict) -> float:
    actual_pomos = _safe_int(pomo.get("actual_pomos"))
    completed_segments = _safe_int(pomo.get("completed_work_segments"))
    work_segments = _safe_int(pomo.get("work_segments"))
    interruptions = _safe_int(pomo.get("interruptions"))
    hollow = _safe_int(pomo.get("hollow"))
    berserker = _safe_int(pomo.get("berserker"))
    effort = min(100, actual_pomos * 24 + completed_segments * 18 + max(0, work_segments - completed_segments) * 6 + berserker * 8)
    drag = (interruptions / max(completed_segments, 1)) * 14 + hollow * 18
    return _clamp(effort - drag)


def _experiment_enricher_score(experiments: list[dict], experiments_by_day: dict[str, dict]) -> float:
    exp_total = len(experiments)
    if not exp_total:
        return 0
    exp_started = sum(1 for exp in experiments if exp.get("started_at"))
    exp_logged = sum(len(exp.get("entries") or []) for exp in experiments)
    exp_judged = sum(1 for exp in experiments if exp.get("status") == "judged")
    exp_abandoned = sum(1 for exp in experiments if exp.get("status") == "abandoned")
    exp_due = sum(day.get("verdict_due", 0) for day in experiments_by_day.values())
    return _clamp(exp_started * 18 + exp_logged * 10 + exp_judged * 14 + exp_abandoned * 6 - exp_due * 12)


def _experiment_day_score(exp: dict) -> float:
    active = _safe_int(exp.get("active"))
    started = _safe_int(exp.get("started"))
    touched = _safe_int(exp.get("touched"))
    logged = _safe_int(exp.get("logged"))
    judged = _safe_int(exp.get("judged"))
    abandoned = _safe_int(exp.get("abandoned"))
    verdict_due = _safe_int(exp.get("verdict_due"))
    active_trial = min(100, active * 55 + started * 35 + touched * 10)
    logging = min(100, (touched or logged) * 100)
    verdict = _clamp(100 - verdict_due * 35) if (active or started or touched or judged or abandoned or verdict_due) else 0
    closure = min(100, judged * 100 + abandoned * 70)
    components = [
        _score_component("Active trial health", 35, active_trial, [], ""),
        _score_component("Logging consistency", 30, logging, [], ""),
        _score_component("Verdict hygiene", 20, verdict, [], ""),
        _score_component("Learning closure", 15, closure, [], ""),
    ]
    return _weighted_score(components)


def _aggregate_experiment_metric(experiments: list[dict], experiments_by_day: dict[str, dict], days: int) -> dict:
    exp_total = len(experiments)
    exp_started = sum(1 for exp in experiments if exp.get("started_at"))
    exp_logged = sum(len(exp.get("entries") or []) for exp in experiments)
    exp_judged = sum(1 for exp in experiments if exp.get("status") == "judged")
    exp_abandoned = sum(1 for exp in experiments if exp.get("status") == "abandoned")
    exp_due = sum(day.get("verdict_due", 0) for day in experiments_by_day.values())
    experiment_days = sum(
        1 for day in experiments_by_day.values()
        if day.get("active") or day.get("started") or day.get("touched") or day.get("judged") or day.get("abandoned")
    )
    active_days = sum(1 for day in experiments_by_day.values() if day.get("active") or day.get("started"))
    logged_days = sum(1 for day in experiments_by_day.values() if day.get("touched") or day.get("logged"))
    noted_abandoned = sum(
        1 for exp in experiments
        if exp.get("status") == "abandoned" and (exp.get("observation_notes") or exp.get("conclusion_notes") or exp.get("entries"))
    )
    active_trial = _clamp((active_days / max(days, 1)) * 100 + exp_started * 8)
    logging = _clamp((logged_days / max(active_days, 1)) * 100) if exp_total else 0
    verdict = _clamp(100 - exp_due * 25) if exp_total else 0
    closure = min(100, exp_judged * 35 + noted_abandoned * 25 + max(0, exp_abandoned - noted_abandoned) * 12)
    weights = FIELD_REPORT_WEIGHTS["evolution"]
    components = [
        _score_component("Active trial health", weights["active_trial_health"], active_trial, [f"{active_days} active trial day{'s' if active_days != 1 else ''}", f"{exp_started} started"], "A trial only counts as health when it is actually running in the window."),
        _score_component("Logging consistency", weights["logging_consistency"], logging, [f"{logged_days} logged day{'s' if logged_days != 1 else ''}", f"{exp_logged} experiment log{'s' if exp_logged != 1 else ''}"], "Tiny Experiments improve the system when they create observed evidence, not just intentions."),
        _score_component("Verdict hygiene", weights["verdict_hygiene"], verdict, [f"{exp_due} verdict due"], "Verdict debt lowers health because open loops keep trial data from becoming learning."),
        _score_component("Learning closure", weights["learning_closure"], closure, [f"{exp_judged} judged", f"{noted_abandoned} abandoned with notes"], "Judged trials count most, but an abandoned trial with notes still teaches the system something."),
    ]
    return {
        "score": _weighted_score(components),
        "confidence": "high" if exp_total and experiment_days >= max(1, days // 3) else "medium" if exp_total else "low",
        "components": components,
        "counts": {
            "exp_total": exp_total,
            "exp_started": exp_started,
            "exp_logged": exp_logged,
            "exp_judged": exp_judged,
            "exp_abandoned": exp_abandoned,
            "exp_due": exp_due,
            "experiment_days": experiment_days,
        },
    }


def _emotional_day_score(day: dict) -> float | None:
    if not day["saga"]["entry_count"]:
        return None
    avg_pleasantness = day["saga"]["avg_pleasantness"]
    adaptive_valence = _clamp(
        50
        + max(avg_pleasantness, 0) / 7 * 35
        - max(-avg_pleasantness - 2, 0) / 5 * 20
    )
    low_acute_load = 100 - day["saga"]["mood_load"]
    stability = 100 - min(100, day["saga"]["volatility"] * 8.5 + day["saga"]["quadrant_switches"] * 8)
    quadrant_distribution = day["saga"].get("quadrant_distribution") or {}
    pleasant_access = 100 if quadrant_distribution.get("yellow", 0) or quadrant_distribution.get("green", 0) else 45
    weights = FIELD_REPORT_WEIGHTS["emotional_climate"]
    return _weighted_score([
        _score_component("Adaptive valence", weights["adaptive_valence"], adaptive_valence, [], ""),
        _score_component("Low acute load", weights["low_acute_load"], low_acute_load, [], ""),
        _score_component("Stability", weights["stability"], stability, [], ""),
        _score_component("Pleasant access", weights["pleasant_access"], pleasant_access, [], ""),
    ])


def _field_report_day_scores(day: dict, pomo: dict, exp: dict) -> dict:
    has_daily_signal = bool(day["quest"]["count"] or pomo.get("actual_pomos") or pomo.get("completed_work_segments"))
    focus = _focus_quality_score(pomo)
    frog = 100 if day["quest"].get("frog_count") else 0
    daily = None
    if has_daily_signal:
        weights = FIELD_REPORT_WEIGHTS["daily_execution"]
        daily = _weighted_score([
            _score_component("Quest quality", weights["quest_quality"], day["quest"]["output_index"], [], ""),
            _score_component("Focus quality", weights["focus_quality"], focus, [], ""),
            _score_component("Frog consistency", weights["frog_consistency"], frog, [], ""),
        ])

    hard90 = day["challenge"]["score"]
    exp_signal = _experiment_day_score(exp)
    long = None
    if hard90 is not None:
        weights = FIELD_REPORT_WEIGHTS["long_game"]
        long = _weighted_score([
            _score_component("Hard 90 integrity", weights["hard90_integrity"], hard90, [], ""),
            _score_component("Tiny Experiment enricher signal", weights["experiment_enricher_signal"], exp_signal, [], ""),
        ])

    has_evolution_signal = bool(exp.get("active") or exp.get("touched") or exp.get("started") or exp.get("verdict_due") or exp.get("judged") or exp.get("abandoned"))
    evolution = _experiment_day_score(exp) if has_evolution_signal else None
    emotion = _emotional_day_score(day)
    alignment = None
    if daily is not None and long is not None:
        alignment = _clamp(daily * 0.45 + long * 0.55)
    return {
        "daily_execution": daily,
        "focus_quality": focus if pomo.get("focus_days") else None,
        "long_game": long,
        "evolution": evolution,
        "emotional_climate": emotion,
        "alignment": alignment,
        "experiment_enricher_signal": exp_signal if has_evolution_signal else None,
    }


def build_pillars(
    day_profiles: list[dict],
    pomo_by_day: dict[str, dict],
    experiments: list[dict],
    experiments_by_day: dict[str, dict],
    meta_analysis: dict,
) -> tuple[list[dict], list[dict], dict]:
    days = len(day_profiles) or 1
    quest_days = sum(1 for day in day_profiles if day["quest"]["count"])
    focus_days = sum(1 for day in pomo_by_day.values() if day.get("focus_days"))
    challenge_days = sum(1 for day in day_profiles if day["challenge"]["count"])
    saga_days = sum(1 for day in day_profiles if day["saga"]["entry_count"])
    experiment_days = sum(
        1 for day in experiments_by_day.values()
        if day.get("active") or day.get("started") or day.get("touched") or day.get("judged")
    )

    output_values = [day["quest"]["output_index"] for day in day_profiles if day["quest"]["count"]]
    output_mean = _mean_or_none(output_values) or 0
    total_frogs = sum(day["quest"]["frog_count"] for day in day_profiles)
    priority_counts: Counter[int] = Counter()
    quest_ages = []
    for day in day_profiles:
        for quest in day.get("quest_items", []):
            priority_counts[max(0, min(4, _safe_int(quest.get("priority"), 4)))] += 1
            quest_ages.append(_quest_age_days(quest))
    pomo_total = sum(day.get("actual_pomos", 0) for day in pomo_by_day.values())
    interruptions = sum(day.get("interruptions", 0) for day in pomo_by_day.values())
    completed_segments = sum(day.get("completed_work_segments", 0) for day in pomo_by_day.values())
    work_segments = sum(day.get("work_segments", 0) for day in pomo_by_day.values())
    hollow = sum(day.get("hollow", 0) for day in pomo_by_day.values())
    berserker = sum(day.get("berserker", 0) for day in pomo_by_day.values())
    focus_score = _focus_quality_score({
        "actual_pomos": pomo_total,
        "completed_work_segments": completed_segments,
        "work_segments": work_segments,
        "interruptions": interruptions,
        "hollow": hollow,
        "berserker": berserker,
    })
    frog_score = _clamp((total_frogs / max(quest_days, 1)) * 100) if quest_days else 0
    daily_weights = FIELD_REPORT_WEIGHTS["daily_execution"]
    daily_components = [
        _score_component(
            "Quest quality",
            daily_weights["quest_quality"],
            output_mean,
            [
                "Priority weights: P0 1.70, P1 1.45, P2 1.20, P3 1.00, P4 0.75",
                "Priority mix: " + ", ".join(f"P{level} {priority_counts.get(level, 0)}" for level in range(5)),
                f"{sum(priority_counts.values())} completed quest{'s' if sum(priority_counts.values()) != 1 else ''}",
                f"Average age at completion {round(mean(quest_ages), 1) if quest_ages else 0}d",
            ],
            "Quest count is not scored equally. A P0 frog completed after aging carries more health signal than several low-priority completions.",
        ),
        _score_component(
            "Focus quality",
            daily_weights["focus_quality"],
            focus_score,
            [
                f"{pomo_total} actual pomo{'s' if pomo_total != 1 else ''}",
                f"{completed_segments} completed work segment{'s' if completed_segments != 1 else ''}",
                f"{interruptions} interruption{'s' if interruptions != 1 else ''}; {hollow} hollow; {berserker} berserker",
            ],
            "Completed focus raises health; interruptions and hollow sessions show quality drag that raw pomo count would hide.",
        ),
        _score_component(
            "Frog consistency",
            daily_weights["frog_consistency"],
            frog_score,
            [f"{total_frogs} frog{'s' if total_frogs != 1 else ''} across {quest_days} quest day{'s' if quest_days != 1 else ''}"],
            "Frogs are the avoided or high-leverage quests, so they get a small explicit consistency lane.",
        ),
    ]
    daily_score = _weighted_score(daily_components)
    daily_confidence = _confidence(max(quest_days, focus_days), days)

    challenge_values = [day["challenge"]["score"] for day in day_profiles if day["challenge"]["score"] is not None]
    challenge_mean = _mean_or_none(challenge_values) or 0
    priority_misses = 0
    bucket_misses: Counter[str] = Counter()
    for day in day_profiles:
        for row in day["challenge"].get("raw_rows", []):
            if row.get("bucket") in {"anchor", "improver"} and row.get("state") != "COMPLETED_SATISFACTORY":
                priority_misses += 1
                bucket_misses[row.get("bucket") or "unknown"] += 1
    experiment_enricher_score = _experiment_enricher_score(experiments, experiments_by_day)
    long_weights = FIELD_REPORT_WEIGHTS["long_game"]
    long_components = [
        _score_component(
            "Hard 90 integrity",
            long_weights["hard90_integrity"],
            challenge_mean,
            [
                "Bucket weights: Anchor 50%, Improver 35%, Enricher 15%",
                f"{bucket_misses.get('anchor', 0)} Anchor miss{'es' if bucket_misses.get('anchor', 0) != 1 else ''}",
                f"{bucket_misses.get('improver', 0)} Improver miss{'es' if bucket_misses.get('improver', 0) != 1 else ''}",
            ],
            "Anchor carries 50% of Hard 90 because it represents identity-level adherence; Enricher carries 15% because it is useful but less load-bearing.",
        ),
        _score_component(
            "Tiny Experiment enricher signal",
            long_weights["experiment_enricher_signal"],
            experiment_enricher_score,
            ["Tiny Experiments are scored as Enricher-level signal inside Long Game Integrity."],
            "Experiments can support the long game, but they cannot rescue weak Anchor or Improver adherence.",
        ),
    ]
    long_score = _weighted_score(long_components)
    long_confidence = _confidence(challenge_days, days)

    experiment_metric = _aggregate_experiment_metric(experiments, experiments_by_day, days)
    exp_total = experiment_metric["counts"]["exp_total"]
    exp_started = experiment_metric["counts"]["exp_started"]
    exp_logged = experiment_metric["counts"]["exp_logged"]
    exp_due = experiment_metric["counts"]["exp_due"]
    evolution_score = experiment_metric["score"]
    evolution_confidence = experiment_metric["confidence"]

    pleasant_ratio = meta_analysis.get("mood_map", {}).get("pleasant_ratio") or 0
    red_blue_ratio = meta_analysis.get("mood_map", {}).get("red_blue_ratio") or 0
    mean_mood_load = meta_analysis.get("emotion_load", {}).get("mean_mood_load") or 0
    if saga_days:
        adaptive_valence_values = [
            _clamp(
                50
                + max(day["saga"]["avg_pleasantness"], 0) / 7 * 35
                - max(-day["saga"]["avg_pleasantness"] - 2, 0) / 5 * 20
            )
            for day in day_profiles
            if day["saga"]["entry_count"]
        ]
        adaptive_valence = _mean_or_none(adaptive_valence_values) or 0
        low_acute_load = _clamp(100 - mean_mood_load)
        stability_values = [
            100 - min(100, day["saga"]["volatility"] * 8.5 + day["saga"]["quadrant_switches"] * 8)
            for day in day_profiles
            if day["saga"]["entry_count"]
        ]
        stability_score = _mean_or_none(stability_values) or 0
        pleasant_access = _clamp(45 + pleasant_ratio * 0.55)
    else:
        adaptive_valence = 50
        low_acute_load = 50
        stability_score = 50
        pleasant_access = 50
    emotional_weights = FIELD_REPORT_WEIGHTS["emotional_climate"]
    emotional_components = [
        _score_component(
            "Adaptive valence",
            emotional_weights["adaptive_valence"],
            adaptive_valence,
            [f"{pleasant_ratio}% pleasant-side entries", "Mild unpleasantness is normalized; pleasantness above baseline is rewarded."] if saga_days else ["No captured mood days; score held neutral and confidence lowered."],
            "This measures adaptive emotional bandwidth, not moral worth. Low-grade anxiety or heaviness is treated as baseline load.",
        ),
        _score_component(
            "Low acute load",
            emotional_weights["low_acute_load"],
            low_acute_load,
            [f"{red_blue_ratio}% red/blue pressure", f"Average mood load {mean_mood_load or 0}"] if saga_days else ["No red/blue pressure observed because no emotion was captured."],
            "Only acute pressure, severe unpleasantness, high activation, depletion, volatility, and repeated switches meaningfully lower this lane.",
        ),
        _score_component(
            "Stability",
            emotional_weights["stability"],
            stability_score,
            ["Volatility and quadrant switches reduce this component."] if saga_days else ["No volatility score without captured emotion; confidence carries the warning."],
            "Stability matters because repeated emotional whiplash consumes operational bandwidth.",
        ),
        _score_component(
            "Pleasant access",
            emotional_weights["pleasant_access"],
            pleasant_access,
            [f"{pleasant_ratio}% pleasant-side entries"] if saga_days else ["No pleasant access score without captured emotion."],
            "Even brief pleasant states count because access to relief, warmth, or steadiness is useful signal in a chronically loaded system.",
        ),
    ]
    emotional_score = _weighted_score(emotional_components)
    emotional_confidence = _confidence(saga_days, days)

    pillars = [
        _pillar(
            "daily_execution",
            "Daily Execution",
            daily_score,
            daily_confidence,
            f"Quest output averaged {round(output_mean)} with {pomo_total} focused pomo{'s' if pomo_total != 1 else ''}.",
            [
                {"label": "Output", "value": round(output_mean)},
                {"label": "Frogs", "value": total_frogs},
                {"label": "Pomos", "value": pomo_total},
                {"label": "Interruptions", "value": interruptions},
            ],
            {
                "formula": "65% Quest quality + 25% Focus quality + 10% Frog consistency",
                "rationale": "Daily Execution measures quality-adjusted traction. Raw quest count remains visible, but priority, frog status, age at completion, and focus cleanliness decide most of the score.",
                "components": daily_components,
            },
        ),
        _pillar(
            "long_game",
            "Long Game Integrity",
            long_score,
            long_confidence,
            f"Hard 90 averaged {round(challenge_mean)} with {priority_misses} Anchor/Improver miss{'es' if priority_misses != 1 else ''}.",
            [
                {"label": "Challenge", "value": round(challenge_mean)},
                {"label": "Priority misses", "value": priority_misses},
                {"label": "Anchor misses", "value": bucket_misses.get("anchor", 0)},
                {"label": "Improver misses", "value": bucket_misses.get("improver", 0)},
            ],
            {
                "formula": "85% Hard 90 integrity + 15% Tiny Experiment enricher signal",
                "rationale": "Long Game Integrity is anchored in Hard 90. Tiny Experiments help at Enricher weight, but Anchor and Improver adherence remain load-bearing.",
                "components": long_components,
            },
        ),
        _pillar(
            "evolution",
            "Evolution / Curiosity",
            evolution_score,
            evolution_confidence,
            f"{exp_started} trial{'s' if exp_started != 1 else ''} started, {exp_logged} experiment log{'s' if exp_logged != 1 else ''}, {exp_due} verdict due.",
            [
                {"label": "Trials", "value": exp_total},
                {"label": "Started", "value": exp_started},
                {"label": "Logs", "value": exp_logged},
                {"label": "Verdicts due", "value": exp_due},
            ],
            {
                "formula": "35% Active trial health + 30% Logging consistency + 20% Verdict hygiene + 15% Learning closure",
                "rationale": "Evolution rewards learning loops, not just experiment volume. Running, logging, judging, and closing trials turn curiosity into system health.",
                "components": experiment_metric["components"],
            },
        ),
        _pillar(
            "emotional_climate",
            "Emotional Climate",
            emotional_score,
            emotional_confidence,
            f"{pleasant_ratio}% pleasant-side entries; {red_blue_ratio}% red/blue pressure.",
            [
                {"label": "Pleasant", "value": f"{pleasant_ratio}%"},
                {"label": "Hellfire/Abyss", "value": f"{red_blue_ratio}%"},
                {"label": "Mood load", "value": mean_mood_load or "—"},
                {"label": "Capture days", "value": saga_days},
            ],
            {
                "formula": "60% Pleasantness health + 25% Low mood load + 15% Stability",
                "rationale": "Emotional Climate reads the operating conditions around the system. Unpleasantness and volatility reduce health; missing capture lowers confidence instead of pretending the mood was bad.",
                "components": emotional_components,
            },
        ),
    ]

    missing_data = []
    if saga_days == 0:
        missing_data.append({"kind": "saga", "title": "Capture emotional signal", "body": "No Saga entries in this grain, so mood-linked analysis is low confidence.", "href": "/saga"})
    if challenge_days == 0:
        missing_data.append({"kind": "hard90", "title": "Start or log a long-game challenge", "body": "Hard 90 is the long-game anchor for the Field Report.", "href": "/challenge"})
    if exp_total == 0:
        missing_data.append({"kind": "experiments", "title": "Start a small trial", "body": "Tiny Experiments show whether you are actively evolving.", "href": "/challenge/experiments"})
    if focus_days == 0:
        missing_data.append({"kind": "pomo", "title": "Use focus sessions for focus-quality analysis", "body": "Quest completion says what moved; Pomo says how focused the work was.", "href": "/"})

    context = {
        "quest_days": quest_days,
        "focus_days": focus_days,
        "challenge_days": challenge_days,
        "saga_days": saga_days,
        "experiment_days": experiment_days,
        "pomo_total": pomo_total,
        "interruptions": interruptions,
        "completed_segments": completed_segments,
        "priority_misses": priority_misses,
        "bucket_misses": dict(bucket_misses),
        "exp_total": exp_total,
        "exp_started": exp_started,
        "exp_logged": exp_logged,
        "exp_due": exp_due,
        "pleasant_ratio": pleasant_ratio,
        "red_blue_ratio": red_blue_ratio,
        "mean_mood_load": mean_mood_load,
        "quest_quality_score": round(output_mean),
        "focus_quality_score": round(focus_score),
        "frog_consistency_score": round(frog_score),
        "experiment_enricher_score": round(experiment_enricher_score),
    }
    return pillars, missing_data, context


def build_system_verdict(pillars: list[dict], missing_data: list[dict], grain: str) -> dict:
    by_key = {pillar["key"]: pillar for pillar in pillars}
    daily = by_key["daily_execution"]["score"]
    long_game = by_key["long_game"]["score"]
    evolution = by_key["evolution"]["score"]
    emotional = by_key["emotional_climate"]["score"]
    confidence = "low" if len(missing_data) >= 2 or by_key["emotional_climate"]["confidence"] == "low" else (
        "medium" if any(pillar["confidence"] == "low" for pillar in pillars) else "high"
    )

    if confidence == "low" and len(missing_data) >= 2:
        label, tone = "Data Thin", "muted"
        analysis = f"This {grain} does not have enough cross-system signal to make a strong diagnosis. Start by filling the missing pillars so the Field Report can separate mood, execution, and long-game drift."
    elif daily < 35 and long_game < 45 and emotional < 45:
        label, tone = "System Down", "risk"
        analysis = f"This {grain}, daily execution, long-game integrity, and emotional climate are all under strain. Treat the next step as stabilization, not optimization."
    elif daily >= 58 and long_game < 55:
        label, tone = "Long Game Neglect", "risk"
        analysis = f"You are getting things done this {grain}, but the Hard 90 signal says priority identity work is slipping. Productivity is not converting into the long game yet."
    elif daily >= 58 and (long_game < 65 or emotional < 50):
        label, tone = "Productive Drift", "watch"
        analysis = f"Execution is alive this {grain}, but it is carrying pressure or leaving long-term goals exposed. The question is not whether you worked; it is what your work protected."
    elif emotional < 45 and daily < 55:
        label, tone = "Emotional Drag", "risk"
        analysis = f"Unpleasant emotional load is paired with weaker motion this {grain}. Treat the next move as perspective and regulation first: name the pressure, choose a kinder interpretation of the circumstance, then make the task small enough to restart traction."
    elif evolution < 35 and daily >= 40:
        label, tone = "Growth Dormant", "watch"
        analysis = f"The operating system is moving, but the experimentation layer is quiet. Add a small trial so progress includes learning, not only execution."
    elif daily >= 60 and long_game >= 70 and emotional >= 60:
        label, tone = "Clean Alignment", "strong"
        analysis = f"Daily execution, long-game integrity, and emotional climate are moving together this {grain}. Protect the conditions that made this alignment possible."
    else:
        label, tone = "Productive Drift", "watch"
        analysis = f"This {grain} has usable motion, but the systems are uneven. Look at the lowest pillar first; that is where the next improvement has leverage."

    return {
        "label": label,
        "tone": tone,
        "confidence": confidence,
        "analysis": analysis,
    }


def build_recommendations(
    pillars: list[dict],
    _missing_data: list[dict],
    context: dict,
) -> list[dict]:
    recs = []
    by_key = {pillar["key"]: pillar for pillar in pillars}
    if by_key["long_game"]["score"] < 60 and context["priority_misses"]:
        recs.append({
            "title": "Protect Anchor and Improver tasks",
            "reason": f"{context['priority_misses']} priority Hard 90 item{'s' if context['priority_misses'] != 1 else ''} slipped while other systems may still look busy.",
            "action": "Log or simplify the long-game task",
            "href": "/challenge",
            "tone": "risk",
        })
    if by_key["daily_execution"]["score"] < 55 and (context["quest_days"] or context["focus_days"]):
        recs.append({
            "title": "Rebuild daily traction",
            "reason": "Quest/Pomo output is not strong enough to carry the day. One frog plus one focused session is the cleanest reset.",
            "action": "Pick one frog and run a focus block",
            "href": "/",
            "tone": "watch",
        })
    if by_key["emotional_climate"]["score"] < 55 and context["saga_days"]:
        recs.append({
            "title": "Reframe pressure before scaling output",
            "reason": f"{context['red_blue_ratio']}% of captured emotion is red/blue pressure. The Field Report reads that as difficult circumstances shaping the system, not as a personal failure.",
            "action": "Capture the next mood and choose a kinder perspective",
            "href": "/saga",
            "tone": "watch",
        })
    if by_key["evolution"]["score"] < 45 and context["exp_total"]:
        recs.append({
            "title": "Keep experiments alive through logs",
            "reason": "Tiny Experiment data exists, but participation is thin. The improvement is logging the trial, not forcing it to succeed.",
            "action": "Log the current trial",
            "href": "/challenge/experiments",
            "tone": "coach",
        })
    if context["exp_due"]:
        recs.append({
            "title": "Close open experiment loops",
            "reason": f"{context['exp_due']} experiment verdict{'s are' if context['exp_due'] != 1 else ' is'} due. Verdict hygiene turns trial data into learning.",
            "action": "Record verdicts",
            "href": "/challenge/experiments",
            "tone": "watch",
        })

    seen = set()
    unique = []
    for rec in recs:
        if rec["title"] in seen:
            continue
        seen.add(rec["title"])
        unique.append(rec)
    return unique[:5]


def build_tendencies(
    day_profiles: list[dict],
    pomo_by_day: dict[str, dict],
    experiments_by_day: dict[str, dict],
) -> list[dict]:
    tendencies = []
    unpleasant_days = [day for day in day_profiles if day["saga"]["entry_count"] and day["saga"]["avg_pleasantness"] < 0]
    productive_unpleasant = [day for day in unpleasant_days if day["quest"]["output_index"] >= 55]
    long_slip_unpleasant = [day for day in productive_unpleasant if (day["challenge"]["score"] is not None and day["challenge"]["score"] < 70)]
    if productive_unpleasant:
        tendencies.append({
            "title": "You can still produce under unpleasant mood",
            "body": f"{len(productive_unpleasant)} unpleasant day{'s' if len(productive_unpleasant) != 1 else ''} still produced output; {len(long_slip_unpleasant)} also showed long-game slippage.",
            "tone": "watch" if long_slip_unpleasant else "strength",
        })

    pleasant_low = [
        day for day in day_profiles
        if day["saga"]["entry_count"] and day["saga"]["avg_pleasantness"] > 0 and day["saga"]["avg_energy"] < 0
    ]
    preserved = [day for day in pleasant_low if day["challenge"]["score"] is not None and day["challenge"]["score"] >= 70]
    if pleasant_low:
        tendencies.append({
            "title": "Pleasant low-energy days may protect the long game",
            "body": f"{len(preserved)} of {len(pleasant_low)} low-energy pleasant days kept Hard 90 at 70+.",
            "tone": "strength" if len(preserved) >= max(1, len(pleasant_low) // 2) else "watch",
        })

    verdict_due_days = sum(1 for day in experiments_by_day.values() if day.get("verdict_due"))
    touched_days = sum(1 for day in experiments_by_day.values() if day.get("touched"))
    if touched_days or verdict_due_days:
        tendencies.append({
            "title": "Experiment loops need closure",
            "body": f"Experiments were touched on {touched_days} day{'s' if touched_days != 1 else ''}; verdicts were due on {verdict_due_days} day{'s' if verdict_due_days != 1 else ''}.",
            "tone": "watch" if verdict_due_days else "strength",
        })

    weekday_counts: dict[str, list[dict]] = defaultdict(list)
    for day in day_profiles:
        weekday_counts[day["weekday"]].append(day)
    if weekday_counts:
        worst = max(
            weekday_counts.items(),
            key=lambda item: mean([d["saga"]["mood_load"] for d in item[1]]) if item[1] else 0,
        )
        output = mean([d["quest"]["output_index"] for d in worst[1]]) if worst[1] else 0
        tendencies.append({
            "title": f"{worst[0]} carries the highest mood load",
            "body": f"Average output on that weekday is {round(output)}. Use it as a planning constraint.",
            "tone": "info",
        })

    focus_days = [day for day in pomo_by_day.values() if day.get("actual_pomos")]
    if focus_days:
        total_interruptions = sum(day.get("interruptions", 0) for day in focus_days)
        completed_segments = sum(day.get("completed_work_segments", 0) for day in focus_days)
        hollow_sessions = sum(day.get("hollow", 0) for day in focus_days)
        avg_interruptions = round(total_interruptions / max(completed_segments, 1), 1)
        if total_interruptions:
            title = "Reduce interruption drag"
            body = f"{total_interruptions} interruption{'s' if total_interruptions != 1 else ''} across {completed_segments} completed focus segment{'s' if completed_segments != 1 else ''}. Protect one cleaner block before adding more work."
            tone = "watch"
        elif hollow_sessions:
            title = "Tighten hollow focus sessions"
            body = f"{hollow_sessions} hollow focus session{'s' if hollow_sessions != 1 else ''} showed effort without real traction. Start the next block with a smaller, visible finish line."
            tone = "watch"
        else:
            title = "Protect clean focus blocks"
            body = f"Focused days averaged {avg_interruptions} interruptions per completed work segment. Keep using those blocks for frogs or Anchor tasks."
            tone = "strength"
        tendencies.append({
            "title": title,
            "body": body,
            "tone": tone,
        })

    if not tendencies:
        tendencies.append({
            "title": "Tendencies are still forming",
            "body": "Capture across Saga, QuestLog, Hard 90, Pomo, and Tiny Experiments to reveal repeated patterns.",
            "tone": "muted",
        })
    return tendencies[:5]


def _pearson_correlation(left: list[float | int | None], right: list[float | int | None]) -> tuple[float | None, int]:
    pairs = [
        (float(a), float(b))
        for a, b in zip(left, right)
        if a is not None and b is not None
    ]
    if len(pairs) < 3:
        return None, len(pairs)
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    x_mean = mean(xs)
    y_mean = mean(ys)
    x_delta = [x - x_mean for x in xs]
    y_delta = [y - y_mean for y in ys]
    x_var = sum(delta * delta for delta in x_delta)
    y_var = sum(delta * delta for delta in y_delta)
    if not x_var or not y_var:
        return None, len(pairs)
    corr = sum(x * y for x, y in zip(x_delta, y_delta)) / math.sqrt(x_var * y_var)
    return round(corr, 2), len(pairs)


def _correlation_tone(value: float | None) -> str:
    if value is None:
        return "insufficient"
    if value <= -0.5:
        return "negative"
    if value >= 0.5:
        return "positive"
    return "weak"


def build_grimoire_charts(
    day_profiles: list[dict],
    pomo_by_day: dict[str, dict],
    experiments_by_day: dict[str, dict],
) -> dict:
    labels = [day["label"] for day in day_profiles]
    dates = [day["date"] for day in day_profiles]
    daily_scores = []
    long_scores = []
    evolution_scores = []
    emotional_scores = []
    scatter = []
    mood_correlation = []
    metric_rows = []
    systems_matrix = {key: [] for key in ("Daily", "Long Game", "Evolution", "Emotion")}
    focus_quality = []
    experiment_runway = []
    mood_split = {
        "pleasant": {"days": 0, "output": [], "challenge": []},
        "unpleasant": {"days": 0, "output": [], "challenge": []},
    }
    bucket_risk = {bucket: {"pleasant": 0, "unpleasant": 0} for bucket in ("anchor", "improver", "enricher")}

    for day in day_profiles:
        pomo = pomo_by_day.get(day["date"], {})
        exp = experiments_by_day.get(day["date"], {})
        weighted = day.get("field_report") or _field_report_day_scores(day, pomo, exp)
        has_daily_signal = bool(day["quest"]["count"] or pomo.get("actual_pomos") or pomo.get("completed_work_segments"))
        has_evolution_signal = bool(exp.get("active") or exp.get("touched") or exp.get("started") or exp.get("verdict_due") or exp.get("judged") or exp.get("abandoned"))
        daily = weighted["daily_execution"]
        long = weighted["long_game"]
        evolution = weighted["evolution"]
        emotion = weighted["emotional_climate"]
        daily_value = round(daily) if daily is not None and has_daily_signal else None
        long_value = round(long) if long is not None else None
        evolution_value = round(evolution) if evolution is not None and has_evolution_signal else None
        emotion_value = round(emotion) if emotion is not None else None
        priority_misses = sum(
            1
            for row in day["challenge"].get("raw_rows", [])
            if row.get("bucket") in {"anchor", "improver"} and row.get("state") != "COMPLETED_SATISFACTORY"
        )
        daily_scores.append(round(daily) if daily is not None else 0)
        long_scores.append(round(long) if long is not None else 0)
        evolution_scores.append(round(evolution) if evolution is not None else 0)
        emotional_scores.append(round(emotion) if emotion is not None else 0)
        systems_matrix["Daily"].append(round(daily) if daily is not None and has_daily_signal else -1)
        systems_matrix["Long Game"].append(round(long) if long is not None else -1)
        systems_matrix["Evolution"].append(round(evolution) if evolution is not None and has_evolution_signal else -1)
        systems_matrix["Emotion"].append(round(emotion) if emotion is not None else -1)
        if has_daily_signal and long is not None and daily is not None:
            scatter.append({
                "label": day["label"],
                "date": day["date"],
                "x": round(daily),
                "y": round(long),
                "pleasantness": day["saga"]["avg_pleasantness"],
                "mood": "Pleasant mood" if day["saga"]["entry_count"] and day["saga"]["avg_pleasantness"] >= 0 else "Unpleasant mood" if day["saga"]["entry_count"] else "No mood captured",
                "experiment": bool(exp.get("active") or exp.get("touched")),
                "mood_load": day["saga"]["mood_load"],
            })
        if day["saga"]["entry_count"]:
            mood_correlation.append({
                "label": day["label"],
                "date": day["date"],
                "pleasantness": day["saga"]["avg_pleasantness"],
                "output": round(daily) if has_daily_signal else None,
                "integrity": round(long) if long is not None else None,
                "mood_load": day["saga"]["mood_load"],
            })
        metric_rows.append({
            "label": day["label"],
            "date": day["date"],
            "pleasantness": day["saga"]["avg_pleasantness"] if day["saga"]["entry_count"] else None,
            "mood_load": day["saga"]["mood_load"] if day["saga"]["entry_count"] else None,
            "quest_output": day["quest"]["output_index"] if day["quest"]["count"] else None,
            "daily_execution": daily_value,
            "emotional_climate": emotion_value,
            "pomos": pomo.get("actual_pomos", 0) if pomo.get("focus_days") else None,
            "interruptions": pomo.get("interruptions", 0) if pomo.get("focus_days") else None,
            "long_game": long_value,
            "priority_misses": priority_misses if day["challenge"]["raw_rows"] else None,
            "curiosity": evolution_value,
            "experiment_touches": exp.get("touched", 0) if has_evolution_signal else None,
            "verdict_debt": exp.get("verdict_due", 0) if has_evolution_signal else None,
        })
        focus_quality.append({
            "label": day["label"],
            "pomos": pomo.get("actual_pomos", 0),
            "interruptions": pomo.get("interruptions", 0),
            "hollow": pomo.get("hollow", 0),
            "berserker": pomo.get("berserker", 0),
        })
        experiment_runway.append({
            "label": day["label"],
            "active": exp.get("active", 0),
            "touched": exp.get("touched", 0),
            "verdict_due": exp.get("verdict_due", 0),
        })
        split_key = "pleasant" if day["saga"]["avg_pleasantness"] >= 0 else "unpleasant"
        if day["saga"]["entry_count"]:
            mood_split[split_key]["days"] += 1
            mood_split[split_key]["output"].append(day["quest"]["output_index"])
            if long is not None:
                mood_split[split_key]["challenge"].append(long)
            for row in day["challenge"].get("raw_rows", []):
                if row.get("state") != "COMPLETED_SATISFACTORY":
                    bucket_risk.setdefault(row.get("bucket") or "unknown", {"pleasant": 0, "unpleasant": 0})
                    bucket_risk[row.get("bucket") or "unknown"][split_key] += 1

    mood_split_rows = []
    for key, values in mood_split.items():
        mood_split_rows.append({
            "mood": key.title(),
            "days": values["days"],
            "output": _mean_or_none(values["output"]) or 0,
            "challenge": _mean_or_none(values["challenge"]) or 0,
        })

    metric_defs = [
        ("pleasantness", "Pleasantness"),
        ("mood_load", "Mood load"),
        ("quest_output", "Quest output"),
        ("daily_execution", "Daily execution"),
        ("pomos", "Pomos"),
        ("interruptions", "Interruptions"),
        ("long_game", "Long game"),
        ("priority_misses", "Priority misses"),
        ("curiosity", "Curiosity"),
        ("experiment_touches", "Experiment touches"),
        ("verdict_debt", "Verdict debt"),
    ]
    metric_values = {
        key: [row.get(key) for row in metric_rows]
        for key, _label in metric_defs
    }
    correlation_matrix = []
    for row_key, row_label in metric_defs:
        row_cells = []
        for col_key, col_label in metric_defs:
            coefficient, paired_days = _pearson_correlation(metric_values[row_key], metric_values[col_key])
            row_cells.append({
                "x": col_label,
                "y": coefficient,
                "metric_x": col_label,
                "metric_y": row_label,
                "paired_days": paired_days,
                "tone": _correlation_tone(coefficient),
            })
        correlation_matrix.append({
            "name": row_label,
            "data": row_cells,
        })

    relationships = [
        {
            "key": "mood_daily",
            "label": "Mood → Daily Execution",
            "x_label": "Mood pleasantness",
            "y_label": "Daily execution",
            "x_min": -7,
            "x_max": 7,
            "y_min": 0,
            "y_max": 100,
            "points": [
                {"x": row["pleasantness"], "y": row["daily_execution"], "label": row["label"], "date": row["date"]}
                for row in metric_rows
                if row["pleasantness"] is not None and row["daily_execution"] is not None
            ],
        },
        {
            "key": "mood_long",
            "label": "Mood → Long Game",
            "x_label": "Mood pleasantness",
            "y_label": "Long game integrity",
            "x_min": -7,
            "x_max": 7,
            "y_min": 0,
            "y_max": 100,
            "points": [
                {"x": row["pleasantness"], "y": row["long_game"], "label": row["label"], "date": row["date"]}
                for row in metric_rows
                if row["pleasantness"] is not None and row["long_game"] is not None
            ],
        },
        {
            "key": "curiosity_long",
            "label": "Curiosity → Long Game",
            "x_label": "Curiosity / evolution",
            "y_label": "Long game integrity",
            "x_min": 0,
            "x_max": 100,
            "y_min": 0,
            "y_max": 100,
            "points": [
                {"x": row["curiosity"], "y": row["long_game"], "label": row["label"], "date": row["date"]}
                for row in metric_rows
                if row["curiosity"] is not None and row["long_game"] is not None
            ],
        },
    ]

    return {
        "labels": labels,
        "dates": dates,
        "timeline_heartbeat": {
            "labels": labels,
            "dates": dates,
            "series": [
                {"name": "Emotional Climate", "data": [row["emotional_climate"] for row in metric_rows]},
                {"name": "Daily Execution", "data": [row["daily_execution"] for row in metric_rows]},
                {"name": "Curiosity", "data": [row["curiosity"] for row in metric_rows]},
                {"name": "Long Game", "data": [row["long_game"] for row in metric_rows]},
            ],
        },
        "relationships": relationships,
        "correlation_matrix": {
            "metrics": [{"key": key, "label": label} for key, label in metric_defs],
            "series": correlation_matrix,
        },
        "pillar_series": {
            "daily": daily_scores,
            "long_game": long_scores,
            "evolution": evolution_scores,
            "emotion": emotional_scores,
        },
        "systems_matrix": systems_matrix,
        "execution_long_game": scatter,
        "mood_correlation": mood_correlation,
        "mood_split": mood_split_rows,
        "focus_quality": focus_quality,
        "experiment_runway": experiment_runway,
        "bucket_risk": [
            {"bucket": bucket.title(), "pleasant": values["pleasant"], "unpleasant": values["unpleasant"]}
            for bucket, values in bucket_risk.items()
        ],
        "dow_system": [
            {
                "weekday": weekday,
                "daily": _mean_or_none([
                    score for score, day in zip(daily_scores, day_profiles)
                    if day["weekday"][:3] == weekday
                ]) or 0,
                "long_game": _mean_or_none([
                    score for score, day in zip(long_scores, day_profiles)
                    if day["weekday"][:3] == weekday
                ]) or 0,
                "emotion": _mean_or_none([
                    score for score, day in zip(emotional_scores, day_profiles)
                    if day["weekday"][:3] == weekday
                ]) or 0,
            }
            for weekday in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        ],
    }


def build_grimoire(
    days: int,
    day_profiles: list[dict],
    pomo_by_day: dict[str, dict],
    experiments: list[dict],
    experiments_by_day: dict[str, dict],
    meta_analysis: dict,
) -> dict:
    grain = {7: "week", 35: "month", 90: "quarter", 365: "year"}.get(days, f"{days}d")
    pillars, missing_data, context = build_pillars(
        day_profiles,
        pomo_by_day,
        experiments,
        experiments_by_day,
        meta_analysis,
    )
    verdict = build_system_verdict(pillars, missing_data, grain)
    recommendations = build_recommendations(pillars, missing_data, context)
    tendencies = build_tendencies(day_profiles, pomo_by_day, experiments_by_day)
    charts = build_grimoire_charts(day_profiles, pomo_by_day, experiments_by_day)
    return {
        "grain": grain,
        "verdict": verdict,
        "pillars": pillars,
        "recommendations": recommendations,
        "tendencies": tendencies,
        "charts": charts,
        "missing_data": missing_data,
        "context": context,
    }


def _scatter_points(day_profiles: list[dict], today_iso: str) -> list[dict]:
    points = []
    for p in day_profiles:
        if not (p["saga"]["entry_count"] or p["quest"]["count"]):
            continue
        points.append({
            "date": p["date"],
            "label": p["label"],
            "mood_load": p["saga"]["mood_load"],
            "output_index": p["quest"]["output_index"],
            "archetype": p["archetype"],
            "accent": p["saga"]["accent"],
            "is_today": p["date"] == today_iso,
        })
    return points


def _dow_profile(day_profiles: list[dict]) -> list[dict]:
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    buckets: dict[int, list[dict]] = defaultdict(list)
    for p in day_profiles:
        wd = date.fromisoformat(p["date"]).weekday()
        buckets[wd].append(p)
    out = []
    for wd in range(7):
        items = buckets.get(wd, [])
        if items:
            mood_avg = round(mean(p["saga"]["mood_load"] for p in items), 1)
            output_avg = round(mean(p["quest"]["output_index"] for p in items), 1)
        else:
            mood_avg = 0
            output_avg = 0
        out.append({
            "weekday": weekday_names[wd],
            "mood_load_avg": mood_avg,
            "output_avg": output_avg,
            "samples": len(items),
        })
    return out


def _block_mood_matrix(rows: list[dict]) -> dict:
    blocks = ["Morning", "Afternoon", "Evening", "Night"]
    matrix: dict[str, dict[str, int]] = {b: {q: 0 for q in QUADRANT_ORDER} for b in blocks}
    for row in rows:
        block = block_for_timestamp(row["timestamp"])
        for mention in _entry_emotion_mentions(row):
            quadrant = mention["quadrant"]
            if quadrant in matrix[block]:
                matrix[block][quadrant] += 1
    return {
        "blocks": blocks,
        "quadrants": list(QUADRANT_ORDER),
        "matrix": matrix,
        "accents": {q: QUADRANT_COLORS[q] for q in QUADRANT_ORDER},
    }


def _mood_meter_cells(rows: list[dict]) -> list[dict]:
    """196 mood-meter cells with visit counts and opacity."""
    cells: list[dict] = []
    coordinate_counts: Counter[tuple[int, int]] = Counter()
    for row in rows:
        coordinate_counts[(int(row["energy"]), int(row["pleasantness"]))] += 1
    max_count = max(coordinate_counts.values()) if coordinate_counts else 1
    for energy in MOOD_ROWS:
        for pleasantness in PLEASANTNESS_COORDS:
            if energy not in VALID_MOOD_COORDS or pleasantness not in VALID_MOOD_COORDS:
                continue
            count = coordinate_counts.get((energy, pleasantness), 0)
            opacity = 0.12 + (count / max_count) * 0.88 if count else 0.08
            quadrant = quadrant_for(energy, pleasantness)
            cells.append({
                "energy": energy,
                "pleasantness": pleasantness,
                "quadrant": quadrant,
                "label": MOOD_WORDS.get((energy, pleasantness), "neutral"),
                "count": count,
                "accent": QUADRANT_COLORS[quadrant],
                "opacity": round(opacity, 2),
            })
    return cells


def _meta_analysis(
    day_profiles: list[dict],
    raw_rows: list[dict],
    family_counts: Counter[str],
    streaks: dict,
    best_day: dict | None,
    top_moods: list[dict],
) -> dict:
    window_days = len(day_profiles) or 1
    active_days = sum(1 for p in day_profiles if p["saga"]["entry_count"] > 0)
    capture_flags = [p["saga"]["entry_count"] > 0 for p in day_profiles]
    coverage_pct = round((active_days / window_days) * 100)
    entries_per_active = round(len(raw_rows) / active_days, 1) if active_days else 0
    capture_confidence = "high" if coverage_pct >= 70 else "medium" if coverage_pct >= 35 else "low"

    mood_values = [p["saga"]["mood_load"] if p["saga"]["entry_count"] else None for p in day_profiles]
    output_values = [p["quest"]["output_index"] if p["quest"]["count"] else None for p in day_profiles]
    volatility_values = [p["saga"]["volatility"] if p["saga"]["entry_count"] else None for p in day_profiles]
    challenge_values = [p["challenge"]["score"] for p in day_profiles]
    alignment_values = [p["alignment"]["score"] for p in day_profiles]

    family_total = sum(family_counts.values())
    entropy = 0.0
    for count in family_counts.values():
        if count <= 0 or family_total <= 0:
            continue
        share = count / family_total
        entropy -= share * math.log2(share)
    max_entropy = math.log2(len(QUADRANT_ORDER))
    diversity_pct = round((entropy / max_entropy) * 100) if family_total and max_entropy else 0
    dominant_family, dominant_count = family_counts.most_common(1)[0] if family_counts else (None, 0)
    dominant_pct = round((dominant_count / family_total) * 100) if family_total else 0
    dominant_label = QUADRANT_LABELS.get(dominant_family, dominant_family.title()) if dominant_family else None
    overrepresented = dominant_label if dominant_family and dominant_pct >= 40 else None

    high_pressure_days = [p for p in day_profiles if p["saga"]["mood_load"] >= 65]
    high_pressure_productive = [p for p in high_pressure_days if p["quest"]["output_index"] >= 55]
    lagged_outputs = [
        day_profiles[idx + 1]["quest"]["output_index"]
        for idx, p in enumerate(day_profiles[:-1])
        if p["saga"]["mood_load"] >= 65 and day_profiles[idx + 1]["quest"]["count"]
    ]
    busy_drift_count = sum(1 for p in day_profiles if p["archetype"] == "Busy Drift")
    corr = _correlation(mood_values, output_values)

    bucket_scores: dict[str, list[int]] = {bucket: [] for bucket in ("anchor", "improver", "enricher")}
    bucket_slopes: dict[str, float | None] = {}
    for bucket in bucket_scores:
        series: list[int | None] = []
        for p in day_profiles:
            score = next((br["score"] for br in p["challenge"]["bucket_rows"] if br["bucket"] == bucket), None)
            if score is not None:
                bucket_scores[bucket].append(score)
            series.append(score)
        bucket_slopes[bucket] = _slope(series)
    bucket_means = {
        bucket: round(mean(scores), 1) if scores else None
        for bucket, scores in bucket_scores.items()
    }
    resolved_buckets = [(bucket, score) for bucket, score in bucket_means.items() if score is not None]
    strongest_bucket = max(resolved_buckets, key=lambda item: item[1], default=(None, None))[0]
    weakest_bucket = min(resolved_buckets, key=lambda item: item[1], default=(None, None))[0]
    bucket_declines = [
        bucket for bucket, slope in bucket_slopes.items()
        if slope is not None and slope <= -1.8
    ]

    aligned_days = sum(1 for p in day_profiles if (p["alignment"]["score"] or 0) >= 70)
    alignment_samples = sum(1 for p in day_profiles if p["alignment"]["score"] is not None)
    alignment_consistency = round((aligned_days / alignment_samples) * 100) if alignment_samples else 0

    recoveries = _recovery_distances(day_profiles)
    unresolved_high_load = 0
    for idx, p in enumerate(day_profiles):
        if p["saga"]["mood_load"] < 65:
            continue
        window = day_profiles[idx + 1: idx + 5]
        if window and not any(future["saga"]["mood_load"] < 55 for future in window):
            unresolved_high_load += 1
    post_pressure_challenge_days = [
        p for p in high_pressure_days
        if p["challenge"]["score"] is not None
    ]
    post_pressure_hold = [
        p for p in post_pressure_challenge_days
        if (p["challenge"]["score"] or 0) >= 75
    ]

    dow_buckets: dict[int, list[dict]] = defaultdict(list)
    for p in day_profiles:
        dow_buckets[date.fromisoformat(p["date"]).weekday()].append(p)
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    best_weekday = None
    best_weekday_score = None
    worst_weekday = None
    worst_weekday_load = None
    weekday_volatility = []
    for wd, items in dow_buckets.items():
        alignments = [p["alignment"]["score"] for p in items if p["alignment"]["score"] is not None]
        loads = [p["saga"]["mood_load"] for p in items if p["saga"]["entry_count"]]
        vols = [p["saga"]["volatility"] for p in items if p["saga"]["entry_count"]]
        if alignments:
            score = mean(alignments)
            if best_weekday_score is None or score > best_weekday_score:
                best_weekday_score = score
                best_weekday = weekday_names[wd]
        if loads:
            load = mean(loads)
            if worst_weekday_load is None or load > worst_weekday_load:
                worst_weekday_load = load
                worst_weekday = weekday_names[wd]
        if vols:
            weekday_volatility.append(mean(vols))

    steady_blocks = Counter()
    quadrant_block_counts: Counter[tuple[str, str]] = Counter()
    for row in raw_rows:
        block = block_for_timestamp(row["timestamp"])
        for mention in _entry_emotion_mentions(row):
            quadrant = mention["quadrant"]
            quadrant_block_counts[(block, quadrant)] += 1
            if quadrant in {"yellow", "green"}:
                steady_blocks[block] += 1
    best_time_block = steady_blocks.most_common(1)[0][0] if steady_blocks else None
    block_quadrant_concentration = None
    if quadrant_block_counts:
        (block, quadrant), count = quadrant_block_counts.most_common(1)[0]
        block_quadrant_concentration = {
            "block": block,
            "quadrant": QUADRANT_LABELS.get(quadrant, quadrant.title()),
            "count": count,
        }

    archetype_counts = Counter(p["archetype"] for p in day_profiles)
    risky_names = {"Busy Drift", "Hellfire Spillover", "Abyss Drag"}
    positive_names = {"Clean Alignment", "Hellfire Forge", "Sanctuary Reset", "Radiance Spark", "Recovery Turn"}
    transitions = Counter()
    for prev, current in zip(day_profiles, day_profiles[1:]):
        if prev["archetype"] != current["archetype"]:
            transitions[f"{prev['archetype']} -> {current['archetype']}"] += 1

    red_blue_count = sum(1 for row in raw_rows if row.get("quadrant") in {"red", "blue"})
    pleasant_count = sum(1 for row in raw_rows if row.get("pleasantness", 0) > 0)

    return {
        "capture": {
            "active_days": active_days,
            "window_days": window_days,
            "coverage_pct": coverage_pct,
            "current_streak": streaks["capture"]["current"],
            "best_streak": streaks["capture"]["best"],
            "longest_gap": _longest_run([not flag for flag in capture_flags]),
            "entries_per_active_day": entries_per_active,
            "confidence": capture_confidence,
            "low_confidence": capture_confidence == "low",
        },
        "emotion_load": {
            "mean_mood_load": _mean_or_none(mood_values),
            "mood_load_slope": _slope(mood_values),
            "average_volatility": _mean_or_none(volatility_values),
            "volatility_slope": _slope(volatility_values),
            "peak_load_days": len(high_pressure_days),
            "dominant_quadrant": dominant_label,
            "dominant_quadrant_pct": dominant_pct,
            "quadrant_diversity": diversity_pct,
            "overrepresented_quadrant": overrepresented,
        },
        "output_coupling": {
            "mood_output_correlation": corr,
            "lagged_output_after_high_load": round(mean(lagged_outputs), 1) if lagged_outputs else None,
            "high_pressure_productivity_rate": round((len(high_pressure_productive) / len(high_pressure_days)) * 100) if high_pressure_days else None,
            "busy_drift_frequency": busy_drift_count,
            "output_decoupling": (corr is not None and corr <= 0) or busy_drift_count >= 3,
        },
        "challenge_integrity": {
            "mean_challenge_score": _mean_or_none(challenge_values),
            "bucket_means": bucket_means,
            "bucket_slopes": bucket_slopes,
            "strongest_bucket": strongest_bucket.title() if strongest_bucket else None,
            "weakest_bucket": weakest_bucket.title() if weakest_bucket else None,
            "bucket_decline_flags": bucket_declines,
        },
        "alignment": {
            "mean_alignment_score": _mean_or_none(alignment_values),
            "aligned_day_count": aligned_days,
            "aligned_streak": streaks["aligned"]["current"],
            "best_aligned_day": best_day,
            "alignment_slope": _slope(alignment_values),
            "alignment_consistency": alignment_consistency,
        },
        "recovery": {
            "mean_recovery_distance": round(mean(recoveries), 1) if recoveries else None,
            "unresolved_high_load_days": unresolved_high_load,
            "recovery_slowing": any(signal["kind"] == "recovery_slowing" for signal in _risk_signals(day_profiles)),
            "post_pressure_challenge_hold_rate": round((len(post_pressure_hold) / len(post_pressure_challenge_days)) * 100) if post_pressure_challenge_days else None,
        },
        "rhythm": {
            "best_weekday_by_alignment": best_weekday,
            "worst_weekday_by_mood_load": worst_weekday,
            "best_time_block_for_steady_emotions": best_time_block,
            "block_quadrant_concentration": block_quadrant_concentration,
            "weekday_volatility": round(mean(weekday_volatility), 1) if weekday_volatility else None,
        },
        "archetypes": {
            "distribution": dict(archetype_counts),
            "dominant_archetype": archetype_counts.most_common(1)[0][0] if archetype_counts else "No Signal",
            "risky_archetype_count": sum(count for name, count in archetype_counts.items() if name in risky_names),
            "positive_archetype_count": sum(count for name, count in archetype_counts.items() if name in positive_names),
            "pressure_recovery_transitions": transitions.get("Hellfire Forge -> Recovery Turn", 0) + transitions.get("Hellfire Spillover -> Recovery Turn", 0),
            "key_transitions": [{"transition": key, "count": count} for key, count in transitions.most_common(5)],
        },
        "mood_map": {
            "top_moods": top_moods,
            "red_blue_count": red_blue_count,
            "red_blue_ratio": round((red_blue_count / len(raw_rows)) * 100) if raw_rows else 0,
            "pleasant_ratio": round((pleasant_count / len(raw_rows)) * 100) if raw_rows else 0,
        },
        "summary_flags": [],
    }


def _meta_summary(meta: dict, risk_signals: list[dict], trends: dict) -> dict:
    confidence = meta["capture"]["confidence"]
    dominant = meta["archetypes"]["dominant_archetype"]
    mean_alignment = meta["alignment"]["mean_alignment_score"]
    busy_count = meta["output_coupling"]["busy_drift_frequency"]
    high_pressure_rate = meta["output_coupling"]["high_pressure_productivity_rate"]

    if mean_alignment is not None and mean_alignment >= 70:
        dominant_pattern = f"{dominant} is the main pattern, with alignment holding across the window."
    elif high_pressure_rate is not None and high_pressure_rate >= 60:
        dominant_pattern = "High pressure is still producing output, but alignment needs watching."
    elif busy_count >= 3:
        dominant_pattern = "Execution is moving, but some of it is drifting away from long-term posture."
    else:
        dominant_pattern = f"{dominant} is the main pattern, with the signal still resolving."

    if risk_signals:
        primary_risk = risk_signals[0]["headline"]
        watchpoint = risk_signals[0]["detail"]
    elif meta["capture"]["low_confidence"]:
        primary_risk = "Thin capture signal"
        watchpoint = "Capture coverage is too sparse to trust every trend."
    else:
        primary_risk = "No major risk signal"
        watchpoint = trends.get("pressure_output") or "Keep watching pressure and output together."

    if meta["capture"]["coverage_pct"] >= 70:
        primary_strength = "Capture consistency is strong enough to trust the trend."
    elif meta["alignment"]["aligned_streak"] >= 3:
        primary_strength = "Alignment has a live streak worth protecting."
    elif meta["challenge_integrity"]["strongest_bucket"]:
        primary_strength = f"{meta['challenge_integrity']['strongest_bucket']} is the strongest challenge bucket."
    else:
        primary_strength = "The dashboard has enough structure to show what to log next."

    return {
        "confidence": confidence,
        "dominant_pattern": dominant_pattern,
        "primary_risk": primary_risk,
        "primary_strength": primary_strength,
        "watchpoint": watchpoint,
    }


def saga_mood_meter_svg(cells: list[dict]) -> Markup:
    by_key = {(cell["energy"], cell["pleasantness"]): cell for cell in cells}
    rows = MOOD_ROWS
    cols = tuple(PLEASANTNESS_COORDS)
    size = 22
    gap = 2
    width = len(cols) * size + (len(cols) - 1) * gap
    height = len(rows) * size + (len(rows) - 1) * gap
    parts = [
        f'<svg class="saga-meter-atlas" viewBox="0 0 {width} {height}" role="img" aria-label="Mood meter visit atlas">',
    ]
    for y, energy in enumerate(rows):
        for x, pleasantness in enumerate(cols):
            cell = by_key.get((energy, pleasantness), {})
            label = str(cell.get("label") or "neutral")
            count = int(cell.get("count") or 0)
            quadrant = str(cell.get("quadrant") or quadrant_for(energy, pleasantness))
            accent = html.escape(str(cell.get("accent") or QUADRANT_COLORS[quadrant]), quote=True)
            opacity = float(cell.get("opacity") or 0.08)
            tooltip = html.escape(
                f"{label.title()} · E:{energy} P:{pleasantness} · {QUADRANT_LABELS.get(quadrant, quadrant)} · {count} visit{'s' if count != 1 else ''}",
                quote=True,
            )
            parts.append(
                f'<rect class="saga-meter-cell" x="{x * (size + gap)}" y="{y * (size + gap)}" width="{size}" height="{size}" rx="3" '
                f'fill="{accent}" fill-opacity="{opacity:.2f}" stroke="rgba(12,21,25,0.72)" stroke-width="1">'
                f'<title>{tooltip}</title></rect>'
            )
    parts.append("</svg>")
    return Markup("".join(parts))


async def saga_dashboard(db: aiosqlite.Connection, days: int = 7) -> dict:
    if days not in {7, 35, 90, 365}:
        days = 7
    bundle = await _collect_window(db, days)
    day_profiles = bundle["day_profiles"]
    calendar_days = bundle["calendar_days"]
    raw_rows = bundle["raw_rows"]
    family_counts = bundle["family_counts"]
    label_counts = bundle["label_counts"]
    today_iso = today_local().isoformat()

    mood_series = [p["saga"]["mood_load"] if p["saga"]["entry_count"] else None for p in day_profiles]
    output_series = [p["quest"]["output_index"] if p["quest"]["count"] else None for p in day_profiles]
    challenge_series = [p["challenge"]["score"] for p in day_profiles]
    alignment_series = [p["alignment"]["score"] for p in day_profiles]
    energy_series = [p["saga"]["avg_energy"] if p["saga"]["entry_count"] else None for p in day_profiles]
    pleasantness_series = [p["saga"]["avg_pleasantness"] if p["saga"]["entry_count"] else None for p in day_profiles]

    today_profile = day_profiles[-1] if day_profiles else None
    archetype = today_profile["archetype"] if today_profile else "No Signal"
    verdict = today_profile["verdict"] if today_profile else "Capture an entry to begin the field report."

    kpis = {
        "mood_load": _kpi_tile(mood_series),
        "output": _kpi_tile(output_series),
        "challenge": _kpi_tile(challenge_series),
        "alignment": _kpi_tile(alignment_series),
    }
    kpis["mood_load"]["label"] = "Mood Load"
    kpis["output"]["label"] = "Output Index"
    kpis["challenge"]["label"] = "Challenge Hold"
    kpis["alignment"]["label"] = "Alignment"

    recent_arc = []
    for p in day_profiles[-7:]:
        recent_arc.append({
            "date": p["date"],
            "label": p["label"],
            "weekday": p["weekday"][:3],
            "archetype": p["archetype"],
            "accent": p["saga"]["accent"],
            "mood_load": p["saga"]["mood_load"],
            "output_index": p["quest"]["output_index"],
            "is_today": p["date"] == today_iso,
        })

    today_emotion_stack = []
    if today_profile:
        for entry in bundle["saga_by_day"].get(today_profile["date"], []):
            for mention in _entry_emotion_mentions(entry):
                distance_pct = int(round(
                    min(100, (math.sqrt((mention["energy"] ** 2) + (mention["pleasantness"] ** 2)) / math.sqrt(98)) * 100)
                ))
                today_emotion_stack.append({
                    "label": mention["label"],
                    "quadrant": mention["quadrant"],
                    "energy": mention["energy"],
                    "pleasantness": mention["pleasantness"],
                    "distance_pct": distance_pct,
                    "accent": QUADRANT_COLORS.get(mention["quadrant"], "#CF9D7B"),
                    "time": display_time(entry["timestamp"]),
                    "role": mention["role"],
                })

    today_quests_list = []
    if today_profile:
        for q in bundle["quests_by_day"].get(today_profile["date"], []):
            today_quests_list.append({
                "id": q["id"],
                "project": q.get("project"),
                "labels": q.get("labels"),
                "frog": q.get("frog"),
            })

    today_challenge_buckets = today_profile["challenge"]["bucket_rows"] if today_profile else []

    quadrant_stream = {quadrant: [0] * len(calendar_days) for quadrant in QUADRANT_ORDER}
    for idx, day in enumerate(calendar_days):
        for entry in bundle["saga_by_day"].get(day, []):
            for mention in _entry_emotion_mentions(entry):
                if mention["quadrant"] in quadrant_stream:
                    quadrant_stream[mention["quadrant"]][idx] += 1

    bucket_series: dict[str, list[float | None]] = {"anchor": [], "improver": [], "enricher": [], "composite": []}
    for p in day_profiles:
        composite = p["challenge"]["score"]
        bucket_series["composite"].append(composite)
        per_bucket = {br["bucket"]: br["score"] for br in p["challenge"]["bucket_rows"]}
        for bucket in ("anchor", "improver", "enricher"):
            bucket_series[bucket].append(per_bucket.get(bucket))

    heatmap = []
    for p in day_profiles:
        avg = p["saga"]["mood_load"]
        count = p["saga"]["entry_count"]
        if not count:
            level = "empty"
        elif avg <= 25:
            level = "low"
        elif avg <= 50:
            level = "mid"
        elif avg <= 70:
            level = "high"
        else:
            level = "peak"
        heatmap.append({
            "date": p["date"],
            "day": date.fromisoformat(p["date"]).day,
            "weekday": date.fromisoformat(p["date"]).weekday(),
            "count": count,
            "average": round(avg, 1),
            "level": level,
        })

    archetype_counts = Counter(p["archetype"] for p in day_profiles)
    total_active = sum(archetype_counts.values()) or 1
    archetype_distribution = [
        {
            "archetype": archetype_name,
            "count": count,
            "pct": round((count / total_active) * 100),
        }
        for archetype_name, count in archetype_counts.most_common()
    ]

    streaks = {
        "capture": _streaks_for(lambda p: p["saga"]["entry_count"] > 0, day_profiles),
        "aligned": _streaks_for(lambda p: (p["alignment"]["score"] or 0) >= 70, day_profiles),
        "challenge": _streaks_for(lambda p: (p["challenge"]["score"] or 0) >= 75, day_profiles),
        "frog": _streaks_for(lambda p: p["quest"]["frog_count"] > 0, day_profiles),
    }

    best_day = None
    best_score = -1
    for p in day_profiles:
        score = p["alignment"]["score"]
        if score is not None and score > best_score:
            best_score = score
            best_day = {
                "date": p["date"],
                "label": p["label"],
                "weekday": p["weekday"],
                "archetype": p["archetype"],
                "verdict": p["verdict"],
                "alignment_score": score,
                "accent": p["saga"]["accent"],
            }

    trends = _saga_relationship_trends(day_profiles)

    recoveries = _recovery_distances(day_profiles)
    recovery_mean = round(mean(recoveries), 1) if recoveries else None

    distribution_total = sum(family_counts.values())
    distribution = [
        {
            "quadrant": quadrant,
            "label": QUADRANT_LABELS[quadrant],
            "count": family_counts.get(quadrant, 0),
            "pct": round((family_counts.get(quadrant, 0) / distribution_total) * 100) if distribution_total else 0,
            "accent": QUADRANT_COLORS[quadrant],
        }
        for quadrant in QUADRANT_ORDER
    ]

    top_labels = [
        {"label": lbl, "count": count}
        for lbl, count in label_counts.most_common(5)
    ]

    risk_signals = _risk_signals(day_profiles)
    scatter = _scatter_points(day_profiles, today_iso)
    top_moods = [
        {"label": lbl, "count": count}
        for lbl, count in label_counts.most_common(5)
    ]
    mood_grid = _mood_meter_cells(raw_rows)
    meta_analysis = _meta_analysis(
        day_profiles,
        raw_rows,
        family_counts,
        streaks,
        best_day,
        top_moods,
    )
    meta_summary = _meta_summary(meta_analysis, risk_signals, trends)
    verdict_due_count = await _experiment_verdict_due_count(db, today_iso)
    narrative = _dashboard_narrative(
        days,
        today_profile,
        kpis,
        trends,
        meta_analysis,
        risk_signals,
        verdict_due_count,
    )
    grimoire = build_grimoire(
        days,
        day_profiles,
        bundle["pomo_by_day"],
        bundle["experiments"],
        bundle["experiments_by_day"],
        meta_analysis,
    )

    return {
        "window_days": days,
        "grain_label": narrative["grain"],
        "today": today_iso,
        "headline": {
            "archetype": archetype,
            "verdict": verdict,
            "kpis": kpis,
            "relations": today_profile["relations"] if today_profile else {},
        },
        "recent_arc": recent_arc,
        "today_card": {
            "emotion_stack": today_emotion_stack,
            "quest_count": today_profile["quest"]["count"] if today_profile else 0,
            "quest_baseline": today_profile["quest"]["baseline"] if today_profile else 0,
            "frog_count": today_profile["quest"]["frog_count"] if today_profile else 0,
            "quests": today_quests_list,
            "challenge_buckets": today_challenge_buckets,
            "challenge_score": today_profile["challenge"]["score"] if today_profile else None,
            "challenge_label": today_profile["challenge"]["label"] if today_profile else "No signal",
        } if today_profile else None,
        "timeseries": {
            "dates": calendar_days,
            "labels": [date.fromisoformat(d).strftime("%b %d") for d in calendar_days],
            "mood_load": mood_series,
            "output_index": output_series,
            "challenge_score": challenge_series,
            "alignment": alignment_series,
            "avg_energy": energy_series,
            "avg_pleasantness": pleasantness_series,
        },
        "quadrant_stream": {
            "dates": calendar_days,
            "series": [
                {"quadrant": quadrant, "label": QUADRANT_LABELS[quadrant], "accent": QUADRANT_COLORS[quadrant], "data": values}
                for quadrant, values in quadrant_stream.items()
            ],
        },
        "heatmap": heatmap,
        "challenge_bucket_series": bucket_series,
        "risk_signals": risk_signals,
        "narrative": narrative,
        "grimoire": grimoire,
        "experiment_verdict_due_count": verdict_due_count,
        "scatter": scatter,
        "archetype_distribution": archetype_distribution,
        "streaks": streaks,
        "best_day": best_day,
        "keystone_mood": trends.get("keystone_mood"),
        "risk_mood": trends.get("risk_mood"),
        "recovery": {
            "prose": trends.get("recovery"),
            "mean_days": recovery_mean,
        },
        "common_archetype": trends.get("common_archetype"),
        "pressure_output": trends.get("pressure_output"),
        "dow_profile": _dow_profile(day_profiles),
        "block_mood": _block_mood_matrix(raw_rows),
        "top_moods": top_moods,
        "distribution": distribution,
        "top_labels": top_labels,
        "mood_grid": mood_grid,
        "total_entries": len(raw_rows),
        "total_mood_mentions": distribution_total,
        "meta_analysis": meta_analysis,
        "meta_summary": meta_summary,
    }
