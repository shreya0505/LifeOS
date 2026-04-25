"""Saga projection and metrics helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import html
import json
import re
from statistics import mean

import aiosqlite

from core.challenge.config import STATE_RANK, TRACKED_BUCKETS
from core.config import USER_TZ
from core.storage.saga_backend import (
    DYAD_ACCENTS,
    DYAD_PAIRS,
    EMOTION_ACCENTS,
    EMOTION_FAMILIES,
    MIXED_EMOTIONS,
    OPPOSITE_PAIRS,
)
from core.utils import today_local, to_local_date


SOURCE_LABELS = {
    "saga": "Saga",
    "questlog": "Questlog",
    "hard90": "Hard 90",
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
        "SELECT id, timestamp, emotion_family, emotion_label, intensity, note, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
        "FROM saga_entries WHERE local_date = ? ORDER BY timestamp",
        (day,),
    )
    for row in await saga_cursor.fetchall():
        dyad_title = None
        if row[9] == "opposite":
            dyad_title = "Opposites"
        elif row[8]:
            dyad_title = row[8].title()
        events.append({
            "id": f"saga:{row[0]}",
            "source": "saga",
            "source_label": SOURCE_LABELS["saga"],
            "timestamp": row[1],
            "time": display_time(row[1]),
            "block": block_for_timestamp(row[1]),
            "title": f"{row[3].title()} / {row[4]}/10" + (f" / {dyad_title}" if dyad_title else ""),
            "summary": row[5] or "Moment captured.",
            "payload": {
                "family": row[2],
                "emotion": row[3],
                "intensity": row[4],
                "note": row[5],
                "secondary_family": row[6],
                "secondary_emotion": row[7],
                "dyad": row[8],
                "dyad_type": row[9],
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
        bits.insert(1, f"latest {latest['emotion']} {latest['intensity']}/10")
    return {
        "title_meta": bits,
        "latest_mood": latest["emotion"] if latest else None,
        "latest_intensity": latest["intensity"] if latest else None,
        "latest_mood_accent": latest["emotion_accent"] if latest else "#CF9D7B",
    }


async def timeline_days(db: aiosqlite.Connection, page: int = 1, per_page: int = 14) -> dict:
    """Build populated day cards for the Saga vertical timeline."""
    today = today_local()
    start = today - timedelta(days=370)
    days: dict[str, dict] = {}

    saga_cursor = await db.execute(
        "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
        "FROM saga_entries WHERE local_date >= ? ORDER BY timestamp",
        (start.isoformat(),),
    )
    for row in await saga_cursor.fetchall():
        day = days.setdefault(row[2], _empty_timeline_day(row[2]))
        intensity = max(1, min(10, int(row[5] or 1)))
        dyad_key = row[9] or row[10] or ""
        day["entries"].append({
            "id": row[0],
            "time": display_time(row[1]),
            "note_html": render_markdown_note(row[6]),
            "emotion_family": row[3],
            "emotion": row[4],
            "emotion_accent": EMOTION_ACCENTS.get(row[3], "#CF9D7B"),
            "intensity": intensity,
            "intensity_pct": min(92, 12 + intensity * 8),
            "mood_wash_pct": min(24, 3 + intensity * 2),
            "mood_glow_pct": min(28, 4 + intensity * 2),
            "mood_chip_pct": min(26, 5 + intensity * 2),
            "secondary_emotion": row[8],
            "dyad_label": row[9],
            "dyad_type": row[10],
            "dyad_accent": DYAD_ACCENTS.get(dyad_key, DYAD_ACCENTS["opposite"]),
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
        day = days.setdefault(row[2], _empty_timeline_day(row[2]))
        day["challenges"].append({
            "id": row[0],
            "time": display_time(timestamp),
            "title": row[5],
            "state": row[3].replace("_", " ").title() if row[3] else None,
            "bucket": row[6],
            "era": row[7],
            "notes": row[4],
        })

    ordered = []
    for local_date in sorted(days.keys(), reverse=True):
        day = days[local_date]
        day["granularity"] = _timeline_granularity(local_date, today)
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
    intensities = [entry["intensity"] for entry in entries]
    avg_intensity = round(mean(intensities), 1) if intensities else 0
    peak_intensity = max(intensities) if intensities else 0
    intensity_range = max(intensities) - min(intensities) if len(intensities) > 1 else 0
    if len(intensities) > 1:
        volatility = round(mean(abs(intensities[i] - intensities[i - 1]) for i in range(1, len(intensities))), 1)
    else:
        volatility = 0
    dyad_count = sum(1 for entry in entries if entry.get("dyad_label") or entry.get("dyad_type"))
    opposite_count = sum(1 for entry in entries if entry.get("dyad_type") == "opposite")
    mood_load = int(round(_clamp(
        avg_intensity * 7
        + min(len(entries), 8) * 3
        + volatility * 5
        + dyad_count * 4
        + opposite_count * 5
    )))
    dominant_family = _dominant([entry["family"] for entry in entries])
    dominant_label = _dominant([entry["label"] for entry in entries])
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
    archetype = _day_archetype(mood_load, output_index, challenge_score, quest_count, len(entries))

    day = date.fromisoformat(local_date)
    return {
        "date": local_date,
        "label": day.strftime("%b %d"),
        "weekday": day.strftime("%A"),
        "archetype": archetype,
        "verdict": _day_verdict(archetype, relations),
        "saga": {
            "entry_count": len(entries),
            "avg_intensity": avg_intensity,
            "peak_intensity": peak_intensity,
            "intensity_range": intensity_range,
            "volatility": volatility,
            "mood_load": mood_load,
            "load_label": _band(mood_load, (25, 50, 70), ("Quiet", "Textured", "Charged", "Heavy")),
            "dominant_family": dominant_family,
            "dominant_label": dominant_label,
            "latest_label": latest["label"] if latest else None,
            "latest_intensity": latest["intensity"] if latest else None,
            "accent": EMOTION_ACCENTS.get(dominant_family, "#CF9D7B"),
            "dyad_count": dyad_count,
            "opposite_count": opposite_count,
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


def _day_relations(
    mood_load: int,
    output_index: int,
    challenge_score: int | None,
    quest_count: int,
    entry_count: int,
) -> dict:
    if mood_load >= 65 and output_index >= 55:
        emotion_quest = "Output held under pressure"
    elif mood_load >= 65:
        emotion_quest = "Load consumed execution"
    elif mood_load < 30 and output_index >= 55:
        emotion_quest = "Quiet execution"
    elif entry_count == 0 and quest_count == 0:
        emotion_quest = "Low capture, low output"
    else:
        emotion_quest = "Emotion and output moved evenly"

    if challenge_score is None:
        emotion_challenge = "Challenge signal missing"
    elif mood_load >= 65 and challenge_score >= 75:
        emotion_challenge = "Discipline held under pressure"
    elif mood_load >= 65 and challenge_score < 65:
        emotion_challenge = "Pressure reached long-term systems"
    elif mood_load < 30 and challenge_score < 60:
        emotion_challenge = "Calm did not protect discipline"
    else:
        emotion_challenge = "Long-term posture tracked normally"

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
) -> str:
    if entry_count == 0 and quest_count == 0 and challenge_score is None:
        return "No Signal"
    if entry_count <= 1 and quest_count == 0 and challenge_score is not None and challenge_score < 60:
        return "False Calm"
    if mood_load >= 65 and output_index < 45 and (challenge_score is None or challenge_score < 70):
        return "Emotional Debt"
    if output_index >= 55 and challenge_score is not None and challenge_score < 65:
        return "Busy Drift"
    if mood_load >= 65 and output_index >= 55 and (challenge_score is None or challenge_score >= 70):
        return "Storm Forge"
    if mood_load >= 65 and output_index >= 55:
        return "Expensive Victory"
    if mood_load < 35 and output_index < 50 and challenge_score is not None and challenge_score >= 75:
        return "Quiet Hold"
    if mood_load < 65 and output_index >= 55 and challenge_score is not None and challenge_score >= 75:
        return "Clean Alignment"
    return "Mixed Field"


def _day_verdict(archetype: str, relations: dict) -> str:
    verdicts = {
        "Clean Alignment": "Emotion, output, and long-term systems moved together.",
        "Storm Forge": "High emotional pressure was converted into execution without breaking the long game.",
        "Expensive Victory": "Output was real, but the day cost more than it looked like from tasks alone.",
        "Busy Drift": "Quest motion outpaced long-term alignment.",
        "Quiet Hold": "The day stayed quiet while the long-term system held.",
        "False Calm": "Low capture paired with weak output and weak discipline; the calm may be under-recorded.",
        "Emotional Debt": "Emotional load rose while execution and long-term posture weakened.",
        "Recovery Day": "The system downshifted after pressure while preserving long-term posture.",
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
            current["archetype"] = "Recovery Day"
            current["verdict"] = _day_verdict("Recovery Day", current["relations"])


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
        family = day["saga"]["dominant_family"]
        challenge_score = day["challenge"]["score"]
        if not family or challenge_score is None:
            continue
        mood_scores[family].append(day["quest"]["output_index"] * 0.45 + challenge_score * 0.55)
    resolved = [(family, mean(scores), len(scores)) for family, scores in mood_scores.items() if len(scores) >= 2]
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
        "keystone_mood": keystone[0].title() if keystone else None,
        "risk_mood": risk[0].title() if risk else None,
        "recovery": recovery,
    }


async def saga_metrics(db: aiosqlite.Connection, days: int = 35) -> dict:
    end = today_local()
    start = end - timedelta(days=days - 1)
    cursor = await db.execute(
        "SELECT local_date, timestamp, emotion_family, emotion_label, intensity, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
        "FROM saga_entries WHERE local_date >= ? ORDER BY local_date, timestamp",
        (start.isoformat(),),
    )
    rows = await cursor.fetchall()
    saga_by_day: dict[str, list[dict]] = defaultdict(list)
    family_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for row in rows:
        intensity = max(1, min(10, int(row[4] or 1)))
        saga_by_day[row[0]].append({
            "date": row[0],
            "timestamp": row[1],
            "family": row[2],
            "label": row[3],
            "intensity": intensity,
            "secondary_family": row[5],
            "secondary_label": row[6],
            "dyad_label": row[7],
            "dyad_type": row[8],
        })
        family_counts[row[2]] += 1
        label_counts[row[3]] += 1

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

    heatmap = []
    by_profile = {day["date"]: day for day in day_profiles}
    for key in calendar_days:
        current = date.fromisoformat(key)
        profile = by_profile[key]
        values = [entry["intensity"] for entry in saga_by_day.get(key, [])]
        avg = profile["saga"]["avg_intensity"]
        variance = profile["saga"]["intensity_range"]
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

    day_averages = [
        profile["saga"]["avg_intensity"]
        for profile in day_profiles
        if profile["saga"]["entry_count"]
    ]
    if len(day_averages) > 1:
        drift = [abs(day_averages[i] - day_averages[i - 1]) for i in range(1, len(day_averages))]
        volatility = round(mean(drift), 1)
    else:
        volatility = 0
    stability = "Stable" if volatility < 1.5 else "Variable" if volatility < 3 else "Volatile"

    high_intensity_days = [
        profile["date"] for profile in day_profiles
        if profile["saga"]["avg_intensity"] >= 7
    ]
    if high_intensity_days:
        high_avg = mean(len(quests_by_day.get(day, [])) for day in high_intensity_days)
        all_avg = mean(quest_counts) if quest_counts else 0
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
    latest_profiles = list(reversed(day_profiles))

    return {
        "heatmap": heatmap,
        "distribution": distribution,
        "top_labels": label_counts.most_common(5),
        "stability": stability,
        "volatility": volatility,
        "correlation": correlation,
        "total_entries": total,
        "current": latest_profiles[0] if latest_profiles else None,
        "recent_days": latest_profiles[:7],
        "trends": _saga_relationship_trends(day_profiles),
        "range_days": days,
    }


def emotion_catalog() -> list[dict]:
    return [
        {
            "family": family,
            "label": family.title(),
            "words": words,
            "accent": EMOTION_ACCENTS[family],
            "mix": MIXED_EMOTIONS.get(family),
        }
        for family, words in EMOTION_FAMILIES.items()
    ]


def dyad_catalog() -> dict:
    dyads = {}
    for pair, data in DYAD_PAIRS.items():
        key = "|".join(sorted(pair))
        dyads[key] = {
            "label": data["label"],
            "type": data["type"],
            "accent": DYAD_ACCENTS[data["label"]],
        }
    for pair in OPPOSITE_PAIRS:
        dyads["|".join(sorted(pair))] = {
            "label": None,
            "type": "opposite",
            "accent": DYAD_ACCENTS["opposite"],
        }
    return dyads
