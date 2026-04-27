"""SQLite storage backend for Saga mood-meter entries."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid

import aiosqlite

from core import clock
from core.config import USER_TZ


QUADRANT_COLORS = {
    "yellow": "#F4C430",
    "red": "#E25555",
    "green": "#5BB97C",
    "blue": "#3F7CCB",
}

VALID_MOOD_COORDS = {-5, -4, -3, -2, -1, 1, 2, 3, 4, 5}

MOOD_WORDS: dict[tuple[int, int], str] = {
    (5, -5): "enraged", (5, -4): "panicked", (5, -3): "furious", (5, -2): "alarmed", (5, -1): "tense",
    (5, 1): "energized", (5, 2): "excited", (5, 3): "thrilled", (5, 4): "elated", (5, 5): "ecstatic",
    (4, -5): "livid", (4, -4): "terrified", (4, -3): "anxious", (4, -2): "agitated", (4, -1): "stressed",
    (4, 1): "upbeat", (4, 2): "eager", (4, 3): "inspired", (4, 4): "joyful", (4, 5): "radiant",
    (3, -5): "resentful", (3, -4): "frantic", (3, -3): "overwhelmed", (3, -2): "nervous", (3, -1): "restless",
    (3, 1): "alert", (3, 2): "motivated", (3, 3): "optimistic", (3, 4): "cheerful", (3, 5): "delighted",
    (2, -5): "irritated", (2, -4): "worried", (2, -3): "uneasy", (2, -2): "pressured", (2, -1): "impatient",
    (2, 1): "interested", (2, 2): "hopeful", (2, 3): "pleased", (2, 4): "happy", (2, 5): "playful",
    (1, -5): "annoyed", (1, -4): "concerned", (1, -3): "frustrated", (1, -2): "edgy", (1, -1): "unsettled",
    (1, 1): "engaged", (1, 2): "open", (1, 3): "warm", (1, 4): "grateful", (1, 5): "lighthearted",
    (-1, -5): "hurt", (-1, -4): "disappointed", (-1, -3): "discouraged", (-1, -2): "lonely", (-1, -1): "down",
    (-1, 1): "at ease", (-1, 2): "mellow", (-1, 3): "content", (-1, 4): "tender", (-1, 5): "peaceful",
    (-2, -5): "sad", (-2, -4): "gloomy", (-2, -3): "weary", (-2, -2): "drained", (-2, -1): "flat",
    (-2, 1): "settled", (-2, 2): "calm", (-2, 3): "relieved", (-2, 4): "balanced", (-2, 5): "serene",
    (-3, -5): "desolate", (-3, -4): "heavy", (-3, -3): "exhausted", (-3, -2): "detached", (-3, -1): "numb",
    (-3, 1): "quiet", (-3, 2): "restful", (-3, 3): "secure", (-3, 4): "comforted", (-3, 5): "tranquil",
    (-4, -5): "miserable", (-4, -4): "hopeless", (-4, -3): "depleted", (-4, -2): "isolated", (-4, -1): "apathetic",
    (-4, 1): "still", (-4, 2): "patient", (-4, 3): "safe", (-4, 4): "grounded", (-4, 5): "restored",
    (-5, -5): "despondent", (-5, -4): "grieving", (-5, -3): "burned out", (-5, -2): "empty", (-5, -1): "shut down",
    (-5, 1): "sleepy", (-5, 2): "soft", (-5, 3): "unhurried", (-5, 4): "placid", (-5, 5): "blissful",
}

MOOD_COORDS = [5, 4, 3, 2, 1, -1, -2, -3, -4, -5]
PLEASANTNESS_COORDS = [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]


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


def _validate_coord(value: int | str, axis: str) -> int:
    try:
        coord = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{axis.title()} must be an integer mood-meter coordinate.") from exc
    if coord not in VALID_MOOD_COORDS:
        raise ValueError(f"{axis.title()} must be one of -5..-1 or 1..5.")
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
    return round(min(1.0, distance / math.sqrt(50)), 3)


def _cell_axis_intensity(energy: int, pleasantness: int) -> float:
    return round((abs(energy) * abs(pleasantness)) / 25, 3)


def mood_catalog() -> list[dict]:
    """Return the serializable 100-cell mood meter catalog for templates."""
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
        "mood_word": row[6],
        "note": row[7],
        "created_at": row[8],
        "quadrant_accent": QUADRANT_COLORS.get(quadrant, "#CF9D7B"),
    }


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
