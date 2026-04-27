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

from core.challenge.config import STATE_LABELS, STATE_RANK, STATE_SHORT, STATES, TRACKED_BUCKETS
from core.config import USER_TZ
from core.storage.saga_backend import (
    MOOD_WORDS,
    PLEASANTNESS_COORDS,
    QUADRANT_COLORS,
    VALID_MOOD_COORDS,
    quadrant_for,
)
from core.utils import today_local, to_local_date


SOURCE_LABELS = {
    "saga": "Saga",
    "questlog": "Questlog",
    "hard90": "Hard 90",
}

QUADRANT_LABELS = {
    "yellow": "High energy pleasant",
    "red": "High energy unpleasant",
    "green": "Low energy pleasant",
    "blue": "Low energy unpleasant",
}

QUADRANT_ORDER = ("yellow", "red", "green", "blue")
MOOD_ROWS = (5, 4, 3, 2, 1, -1, -2, -3, -4, -5)


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
        events.append({
            "id": f"hard90:{row[0]}",
            "source": "hard90",
            "source_label": SOURCE_LABELS["hard90"],
            "timestamp": timestamp,
            "time": display_time(timestamp),
            "block": block_for_timestamp(timestamp),
            "title": row[5],
            "summary": row[4] or row[3].replace("_", " ").title(),
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
        "quests": [],
        "challenges": [],
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


def _timeline_day_title_meta(day: dict) -> dict:
    entries = day["entries"]
    quests = day["quests"]
    challenges = day["challenges"]
    latest = entries[-1] if entries else None
    bits = [
        _count_label(len(entries), "entry", "entries"),
        _count_label(len(quests), "quest"),
        _count_label(len(challenges), "trial"),
    ]
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
        strength = min(100, int(round((distance / math.sqrt(50)) * 100)))
        day["entries"].append({
            "id": row[0],
            "time": display_time(row[1]),
            "note_html": render_markdown_note(row[7]),
            "energy": energy,
            "pleasantness": pleasantness,
            "quadrant": row[5],
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
            "notes": row[4],
        })

    ordered = []
    for local_date in sorted(days.keys(), reverse=True):
        day = days[local_date]
        day["granularity"] = _timeline_granularity(local_date, today)
        day["quest_summary"] = _quest_day_summary(day["quests"])
        day["challenge_summary"] = _challenge_day_summary(day["challenges"])
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


def _quest_weight(quest: dict) -> float:
    priority = int(quest.get("priority") if quest.get("priority") is not None else 4)
    return 1 + (0.35 if quest.get("frog") else 0) + max(0, 4 - priority) * 0.12


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
        }

    scores = [((STATE_RANK.get(item["state"], 1) - 1) / 4) * 100 for item in rows]
    score = int(round(mean(scores)))
    held = sum(1 for item in rows if item["state"] == "COMPLETED_SATISFACTORY")
    weak = sum(1 for item in rows if STATE_RANK.get(item["state"], 1) <= 3)
    buckets: dict[str, list[int]] = defaultdict(list)
    for item in rows:
        buckets[item["bucket"]].append(STATE_RANK.get(item["state"], 1))
    bucket_rows = [
        {
            "bucket": bucket,
            "label": bucket.title(),
            "score": int(round(mean(((rank - 1) / 4) * 100 for rank in ranks))),
            "count": len(ranks),
        }
        for bucket, ranks in sorted(buckets.items())
    ]
    return {
        "score": score,
        "label": _band(score, (45, 70, 86), ("Frayed", "Mixed", "Held", "Clean")),
        "count": len(rows),
        "held": held,
        "weak": weak,
        "bucket_rows": bucket_rows,
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
        unpleasant_pressure = ((5 - avg_pleasantness) / 10) * 34
        activation_pressure = (max(avg_energy, 0) / 5) * 16
        depletion_pressure = (max(-avg_energy, 0) / 5) * 12
        volatility_pressure = min(volatility / 5, 1) * 24
        quadrant_pressure = red_share * 14 + blue_share * 10 - green_share * 6
        capture_pressure = min(entry_count, 6) * 3
        switch_pressure = min(quadrant_switches, 4) * 2
        mood_load = int(round(_clamp(
            unpleasant_pressure
            + activation_pressure
            + depletion_pressure
            + volatility_pressure
            + quadrant_pressure
            + capture_pressure
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
    output_delta = int(round(((quest_count - quest_baseline) / baseline) * 100)) if baseline else 0
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
            return "Red Forge"
        if dominant_quadrant == "red" or avg_energy > 0:
            return "Red Spillover"
        return "Blue Drag"
    if dominant_quadrant == "green":
        return "Green Reset"
    if dominant_quadrant == "yellow":
        return "Yellow Spark"
    if dominant_quadrant == "blue" or avg_pleasantness < 0:
        return "Blue Drag"
    return "Green Reset"


def _day_verdict(archetype: str, relations: dict) -> str:
    verdicts = {
        "Clean Alignment": "Mood, output, and long-term systems moved together.",
        "Red Forge": "High-energy unpleasantness was converted into execution without breaking the long game.",
        "Red Spillover": "Activated unpleasantness is pressing into the rest of the system.",
        "Blue Drag": "Low-energy unpleasantness is weighing on motion and recovery.",
        "Green Reset": "The system is downshifting into steadier, more regulated territory.",
        "Yellow Spark": "Pleasant activation is available; useful momentum can be harvested.",
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
        "SELECT id, completed_at, frog, priority, project, labels, workspace_id "
        "FROM quests WHERE status = 'done' AND completed_at IS NOT NULL"
    )
    quests_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in await quest_cursor.fetchall():
        local_date = to_local_date(row[1])
        if local_date < start.isoformat() or local_date > end.isoformat():
            continue
        quests_by_day[local_date].append({
            "id": row[0],
            "completed_at": row[1],
            "frog": bool(row[2]),
            "priority": row[3] if row[3] is not None else 4,
            "project": row[4],
            "labels": display_labels(row[5]),
            "workspace": row[6],
        })

    challenge_cursor = await db.execute(
        "SELECT e.id, e.log_date, e.state, t.bucket, t.name, c.era_name "
        "FROM challenge_entries e "
        "JOIN challenge_tasks t ON t.id = e.task_id "
        "JOIN challenges c ON c.id = e.challenge_id "
        "WHERE e.log_date >= ? AND e.log_date <= ? "
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

    calendar_days = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]
    quest_counts = [len(quests_by_day.get(day, [])) for day in calendar_days]
    quest_baseline = mean(quest_counts[:-1]) if len(quest_counts) > 1 else 0
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
    return {
        "start": start,
        "end": end,
        "calendar_days": calendar_days,
        "saga_by_day": saga_by_day,
        "quests_by_day": quests_by_day,
        "challenges_by_day": challenges_by_day,
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
    """100 mood-meter cells with visit counts and opacity."""
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
    risky_names = {"Busy Drift", "Red Spillover", "Blue Drag"}
    positive_names = {"Clean Alignment", "Red Forge", "Green Reset", "Yellow Spark", "Recovery Turn"}
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
            "pressure_recovery_transitions": transitions.get("Red Forge -> Recovery Turn", 0) + transitions.get("Red Spillover -> Recovery Turn", 0),
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
    rows = (5, 4, 3, 2, 1, -1, -2, -3, -4, -5)
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
                    min(100, (math.sqrt((mention["energy"] ** 2) + (mention["pleasantness"] ** 2)) / math.sqrt(50)) * 100)
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

    return {
        "window_days": days,
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
