"""SQLite storage backend for Saga mood-meter entries."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from urllib.parse import urlparse
import uuid

import aiosqlite

from core import clock
from core.config import USER_TZ


QUADRANT_COLORS = {
    "yellow": "#F4C430",
    "red": "#8F1F17",
    "green": "#2F7D4A",
    "blue": "#252A33",
}

QUADRANT_LABELS = {
    "yellow": "Radiance",
    "red": "Hellfire",
    "green": "Sanctuary",
    "blue": "Abyss",
}

VALID_MOOD_COORDS = {-7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7}

MOOD_WORDS: dict[tuple[int, int], str] = {
    (7, -7): "uncontainable", (7, -6): "frenzied", (7, -5): "incensed", (7, -4): "unraveling", (7, -3): "spinning", (7, -2): "overwrought", (7, -1): "overstimulated",
    (7, 1): "fervent", (7, 2): "exuberant", (7, 3): "impassioned", (7, 4): "euphoric", (7, 5): "rapturous", (7, 6): "transcendent", (7, 7): "exultant",
    (6, -7): "humiliated", (6, -6): "seething", (6, -5): "enflamed", (6, -4): "desperate", (6, -3): "obsessed", (6, -2): "hypervigilant", (6, -1): "keyed up",
    (6, 1): "vigorous", (6, 2): "animated", (6, 3): "exhilarated", (6, 4): "jubilant", (6, 5): "overjoyed", (6, 6): "glowing", (6, 7): "soaring",
    (5, -7): "vengeful", (5, -6): "mortified", (5, -5): "enraged", (5, -4): "panicked", (5, -3): "furious", (5, -2): "on edge", (5, -1): "tense",
    (5, 1): "energized", (5, 2): "excited", (5, 3): "thrilled", (5, 4): "elated", (5, 5): "ecstatic", (5, 6): "triumphant", (5, 7): "exalted",
    (4, -7): "guilt-ridden", (4, -6): "exposed", (4, -5): "livid", (4, -4): "terrified", (4, -3): "anxious", (4, -2): "agitated", (4, -1): "stressed",
    (4, 1): "upbeat", (4, 2): "eager", (4, 3): "inspired", (4, 4): "joyful", (4, 5): "radiant", (4, 6): "proud", (4, 7): "magnificent",
    (3, -7): "tormented", (3, -6): "degraded", (3, -5): "resentful", (3, -4): "frantic", (3, -3): "overwhelmed", (3, -2): "nervous", (3, -1): "restless",
    (3, 1): "alert", (3, 2): "motivated", (3, 3): "optimistic", (3, 4): "cheerful", (3, 5): "delighted", (3, 6): "accomplished", (3, 7): "luminous",
    (2, -7): "racked", (2, -6): "ashamed", (2, -5): "dread-filled", (2, -4): "worried", (2, -3): "apprehensive", (2, -2): "pressured", (2, -1): "impatient",
    (2, 1): "interested", (2, 2): "hopeful", (2, 3): "pleased", (2, 4): "happy", (2, 5): "playful", (2, 6): "loving", (2, 7): "affectionate",
    (1, -7): "bitter", (1, -6): "embarrassed", (1, -5): "annoyed", (1, -4): "concerned", (1, -3): "frustrated", (1, -2): "edgy", (1, -1): "unsettled",
    (1, 1): "engaged", (1, 2): "open", (1, 3): "warm", (1, 4): "grateful", (1, 5): "lighthearted", (1, 6): "moved", (1, 7): "touched",
    (-1, -7): "cringey", (-1, -6): "self-conscious", (-1, -5): "awkward", (-1, -4): "second-guessing", (-1, -3): "uneasy", (-1, -2): "lonely", (-1, -1): "down",
    (-1, 1): "at ease", (-1, 2): "mellow", (-1, 3): "content", (-1, 4): "tender", (-1, 5): "peaceful", (-1, 6): "nurtured", (-1, 7): "cherished",
    (-2, -7): "regretful", (-2, -6): "self-critical", (-2, -5): "embarrassed", (-2, -4): "ruminating", (-2, -3): "worried", (-2, -2): "drained", (-2, -1): "flat",
    (-2, 1): "settled", (-2, 2): "calm", (-2, 3): "relieved", (-2, 4): "balanced", (-2, 5): "serene", (-2, 6): "cozy", (-2, 7): "embraced",
    (-3, -7): "inadequate", (-3, -6): "self-loathing", (-3, -5): "cringe-sick", (-3, -4): "dread-heavy", (-3, -3): "exhausted", (-3, -2): "detached", (-3, -1): "numb",
    (-3, 1): "quiet", (-3, 2): "restful", (-3, 3): "secure", (-3, 4): "comforted", (-3, 5): "tranquil", (-3, 6): "nourished", (-3, 7): "cradled",
    (-4, -7): "crushed", (-4, -6): "unworthy", (-4, -5): "mortified", (-4, -4): "hopeless", (-4, -3): "depleted", (-4, -2): "isolated", (-4, -1): "apathetic",
    (-4, 1): "still", (-4, 2): "patient", (-4, 3): "safe", (-4, 4): "grounded", (-4, 5): "restored", (-4, 6): "replenished", (-4, 7): "whole",
    (-5, -7): "self-disgusted", (-5, -6): "hollowed out", (-5, -5): "despondent", (-5, -4): "dread-soaked", (-5, -3): "burned out", (-5, -2): "empty", (-5, -1): "shut down",
    (-5, 1): "sleepy", (-5, 2): "soft", (-5, 3): "unhurried", (-5, 4): "placid", (-5, 5): "blissful", (-5, 6): "drowsy", (-5, 7): "boundless",
    (-6, -7): "shame-spiraling", (-6, -6): "wretched", (-6, -5): "devastated", (-6, -4): "forsaken", (-6, -3): "broken", (-6, -2): "hollow", (-6, -1): "lifeless",
    (-6, 1): "dormant", (-6, 2): "languid", (-6, 3): "lulled", (-6, 4): "absorbed", (-6, 5): "at peace", (-6, 6): "soothed", (-6, 7): "beatific",
    (-7, -7): "self-obliterating", (-7, -6): "collapsed", (-7, -5): "void", (-7, -4): "dissociated", (-7, -3): "frozen", (-7, -2): "inert", (-7, -1): "absent",
    (-7, 1): "suspended", (-7, 2): "meditative", (-7, 3): "floating", (-7, 4): "surrendered", (-7, 5): "dissolved", (-7, 6): "timeless", (-7, 7): "sublime",
}

MOOD_COORDS = [7, 6, 5, 4, 3, 2, 1, -1, -2, -3, -4, -5, -6, -7]
PLEASANTNESS_COORDS = [-7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7]


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    return clock.utcnow().isoformat()


def _local_date(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        dt = clock.utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(USER_TZ).date().isoformat()


def _clean_note(note: str | None) -> str | None:
    cleaned = (note or "").strip()
    return cleaned or None


def _clean_markdown(markdown: str | None) -> str:
    return (markdown or "").strip()


def _clean_source_url(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Legacy source link must be a valid http(s) URL.")
    return cleaned


def source_kind_for(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return "none"
    parsed = urlparse(cleaned)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if re.search(r"\.(png|jpe?g|gif|webp|avif|bmp|svg)(\?.*)?$", path):
        return "image"
    return "article"


def _clean_labels(labels: str | list[str] | None) -> list[str]:
    if isinstance(labels, str):
        raw = labels.split(",")
    else:
        raw = labels or []
    cleaned = []
    seen = set()
    for item in raw:
        label = str(item).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label[:48])
    return cleaned[:24]


def _labels_json(labels: str | list[str] | None) -> str:
    return json.dumps(_clean_labels(labels), separators=(",", ":"))


def _parse_labels(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return _clean_labels(parsed)


def _validate_coord(value: int | str, axis: str) -> int:
    try:
        coord = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{axis.title()} must be an integer mood-meter coordinate.") from exc
    if coord not in VALID_MOOD_COORDS:
        raise ValueError(f"{axis.title()} must be one of -7..-1 or 1..7.")
    return coord


def quadrant_for(energy: int, pleasantness: int) -> str:
    if energy > 0 and pleasantness > 0:
        return "yellow"
    if energy > 0 and pleasantness <= 0:
        return "red"
    if energy <= 0 and pleasantness > 0:
        return "green"
    if energy < 0 and pleasantness <= 0:
        return "blue"
    return "green"


def _mood_word(energy: int, pleasantness: int, supplied: str | None = None) -> str:
    cleaned = (supplied or "").strip().lower()
    if cleaned:
        return cleaned
    return MOOD_WORDS.get((energy, pleasantness), "neutral")


def _cell_saturation(energy: int, pleasantness: int) -> float:
    distance = math.sqrt((energy * energy) + (pleasantness * pleasantness))
    return round(min(1.0, distance / math.sqrt(98)), 3)


def _cell_axis_intensity(energy: int, pleasantness: int) -> float:
    return round((abs(energy) * abs(pleasantness)) / 49, 3)


def mood_catalog() -> list[dict]:
    """Return the serializable 196-cell mood meter catalog for templates."""
    cells = []
    for energy in MOOD_COORDS:
        for pleasantness in PLEASANTNESS_COORDS:
            quadrant = quadrant_for(energy, pleasantness)
            cells.append({
                "energy": energy,
                "pleasantness": pleasantness,
                "word": MOOD_WORDS[(energy, pleasantness)],
                "quadrant": quadrant,
                "accent": QUADRANT_COLORS[quadrant],
                "saturation": _cell_saturation(energy, pleasantness),
                "axis_intensity": _cell_axis_intensity(energy, pleasantness),
            })
    return cells


def _row_to_entry(row: tuple) -> dict:
    quadrant = row[5]
    return {
        "id": row[0],
        "timestamp": row[1],
        "local_date": row[2],
        "energy": row[3],
        "pleasantness": row[4],
        "quadrant": quadrant,
        "quadrant_label": QUADRANT_LABELS.get(quadrant, quadrant.title()),
        "mood_word": row[6],
        "note": row[7],
        "created_at": row[8],
        "quadrant_accent": QUADRANT_COLORS.get(quadrant, "#CF9D7B"),
    }


def _row_to_legacy(row: tuple) -> dict:
    return {
        "id": row[0],
        "timestamp": row[1],
        "local_date": row[2],
        "source_url": row[3],
        "source_kind": row[4] or "none",
        "labels": _parse_labels(row[5]),
        "markdown": row[6],
        "created_at": row[7],
    }


def _legacy_heading_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "heading"


def _legacy_headings(markdown: str | None) -> list[dict]:
    headings = []
    seen: dict[str, int] = {}
    for line in (markdown or "").splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = match.group(2).strip(" #")
        if not title:
            continue
        base = _legacy_heading_slug(title)
        seen[base] = seen.get(base, 0) + 1
        slug = base if seen[base] == 1 else f"{base}-{seen[base]}"
        headings.append({"title": title, "slug": slug, "level": len(match.group(1))})
    return headings


class SqliteSagaRepo:
    """Saga entries backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self,
        energy: int,
        pleasantness: int,
        mood_word: str,
        note: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        e = _validate_coord(energy, "energy")
        p = _validate_coord(pleasantness, "pleasantness")
        word = _mood_word(e, p, mood_word)
        quadrant = quadrant_for(e, p)
        ts = timestamp or _now_iso()
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO saga_entries "
            "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, ts, _local_date(ts), e, p, quadrant, word, _clean_note(note), now),
        )
        await self._db.commit()
        return await self.get(eid) or {
            "id": eid,
            "timestamp": ts,
            "local_date": _local_date(ts),
            "energy": e,
            "pleasantness": p,
            "quadrant": quadrant,
            "quadrant_label": QUADRANT_LABELS.get(quadrant, quadrant.title()),
            "mood_word": word,
            "note": _clean_note(note),
            "created_at": now,
            "quadrant_accent": QUADRANT_COLORS[quadrant],
        }

    async def get(self, entry_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note, created_at "
            "FROM saga_entries WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        return _row_to_entry(row) if row else None

    async def update(
        self,
        entry_id: str,
        energy: int,
        pleasantness: int,
        mood_word: str,
        note: str | None = None,
    ) -> dict | None:
        e = _validate_coord(energy, "energy")
        p = _validate_coord(pleasantness, "pleasantness")
        word = _mood_word(e, p, mood_word)
        quadrant = quadrant_for(e, p)
        await self._db.execute(
            "UPDATE saga_entries SET energy = ?, pleasantness = ?, quadrant = ?, mood_word = ?, note = ? "
            "WHERE id = ?",
            (e, p, quadrant, word, _clean_note(note), entry_id),
        )
        await self._db.commit()
        return await self.get(entry_id)

    async def delete(self, entry_id: str) -> None:
        await self._db.execute("DELETE FROM saga_entries WHERE id = ?", (entry_id,))
        await self._db.commit()

    async def list_recent(self, limit: int = 8) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note, created_at "
            "FROM saga_entries ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_by_date(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note, created_at "
            "FROM saga_entries WHERE local_date = ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_since(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note, created_at "
            "FROM saga_entries WHERE local_date >= ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]


class SqliteSagaLegacyRepo:
    """Saga Legacy entries backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self,
        source_url: str | None,
        labels: str | list[str] | None,
        markdown: str,
        timestamp: str | None = None,
    ) -> dict:
        body = _clean_markdown(markdown)
        if not body:
            raise ValueError("Legacy markdown note cannot be empty.")
        url = _clean_source_url(source_url)
        ts = timestamp or _now_iso()
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO saga_legacy_entries "
            "(id, timestamp, local_date, source_url, source_kind, labels, markdown, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, ts, _local_date(ts), url, source_kind_for(url), _labels_json(labels), body, now),
        )
        await self._db.commit()
        return await self.get(eid) or {
            "id": eid,
            "timestamp": ts,
            "local_date": _local_date(ts),
            "source_url": url,
            "source_kind": source_kind_for(url),
            "labels": _clean_labels(labels),
            "markdown": body,
            "created_at": now,
        }

    async def get(self, entry_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, source_url, source_kind, labels, markdown, created_at "
            "FROM saga_legacy_entries WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        return _row_to_legacy(row) if row else None

    async def list_since(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, source_url, source_kind, labels, markdown, created_at "
            "FROM saga_legacy_entries WHERE local_date >= ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_legacy(row) for row in await cursor.fetchall()]

    async def list_all(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, source_url, source_kind, labels, markdown, created_at "
            "FROM saga_legacy_entries ORDER BY timestamp DESC"
        )
        return [_row_to_legacy(row) for row in await cursor.fetchall()]

    async def search_headings(self, query: str, limit: int = 8) -> list[dict]:
        needle = (query or "").strip().casefold()
        if not needle:
            return []
        matches = []
        for entry in await self.list_all():
            for heading in _legacy_headings(entry.get("markdown")):
                if needle not in heading["title"].casefold():
                    continue
                matches.append({
                    "entry_id": entry["id"],
                    "title": heading["title"],
                    "slug": heading["slug"],
                    "local_date": entry["local_date"],
                    "href": f"/saga/legacy/{entry['id']}#{heading['slug']}",
                })
                if len(matches) >= limit:
                    return matches
        return matches

    async def list_by_label(self, label: str) -> list[dict]:
        needle = (label or "").strip().casefold()
        if not needle:
            return []
        return [
            entry for entry in await self.list_all()
            if needle in {item.casefold() for item in entry.get("labels", [])}
        ]
