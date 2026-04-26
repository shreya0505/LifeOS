"""SQLite storage backend for Saga emotion entries."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import aiosqlite

from core import clock
from core.config import USER_TZ


EMOTION_FAMILIES = {
    "joy": ("serenity", "joy", "ecstasy"),
    "trust": ("acceptance", "trust", "admiration"),
    "fear": ("apprehension", "fear", "terror"),
    "surprise": ("distraction", "surprise", "amazement"),
    "sadness": ("pensiveness", "sadness", "grief"),
    "disgust": ("boredom", "disgust", "loathing"),
    "anger": ("annoyance", "anger", "rage"),
    "anticipation": ("interest", "anticipation", "vigilance"),
}

EMOTION_ACCENTS = {
    "joy": "#F6D365",
    "trust": "#61D394",
    "fear": "#7C9CFF",
    "surprise": "#D58BFF",
    "sadness": "#6FB7D8",
    "disgust": "#9DBA5A",
    "anger": "#FF6B5F",
    "anticipation": "#F4A261",
}

MIXED_EMOTIONS = {
    "anticipation": {"with": "joy", "label": "optimism"},
    "joy": {"with": "trust", "label": "love"},
    "trust": {"with": "fear", "label": "submission"},
    "fear": {"with": "surprise", "label": "awe"},
    "surprise": {"with": "sadness", "label": "disapproval"},
    "sadness": {"with": "disgust", "label": "remorse"},
    "disgust": {"with": "anger", "label": "contempt"},
    "anger": {"with": "anticipation", "label": "aggression"},
}

DYAD_PAIRS = {
    frozenset(("joy", "trust")): {"label": "love", "type": "primary"},
    frozenset(("trust", "fear")): {"label": "submission", "type": "primary"},
    frozenset(("fear", "surprise")): {"label": "awe", "type": "primary"},
    frozenset(("surprise", "sadness")): {"label": "disapproval", "type": "primary"},
    frozenset(("sadness", "disgust")): {"label": "remorse", "type": "primary"},
    frozenset(("disgust", "anger")): {"label": "contempt", "type": "primary"},
    frozenset(("anger", "anticipation")): {"label": "aggression", "type": "primary"},
    frozenset(("anticipation", "joy")): {"label": "optimism", "type": "primary"},
    frozenset(("joy", "fear")): {"label": "guilt", "type": "secondary"},
    frozenset(("trust", "surprise")): {"label": "curiosity", "type": "secondary"},
    frozenset(("fear", "sadness")): {"label": "despair", "type": "secondary"},
    frozenset(("surprise", "disgust")): {"label": "unbelief", "type": "secondary"},
    frozenset(("sadness", "anger")): {"label": "envy", "type": "secondary"},
    frozenset(("disgust", "anticipation")): {"label": "cynicism", "type": "secondary"},
    frozenset(("anger", "joy")): {"label": "pride", "type": "secondary"},
    frozenset(("anticipation", "trust")): {"label": "hope", "type": "secondary"},
    frozenset(("joy", "surprise")): {"label": "delight", "type": "tertiary"},
    frozenset(("trust", "sadness")): {"label": "sentimentality", "type": "tertiary"},
    frozenset(("fear", "disgust")): {"label": "shame", "type": "tertiary"},
    frozenset(("surprise", "anger")): {"label": "outrage", "type": "tertiary"},
    frozenset(("sadness", "anticipation")): {"label": "pessimism", "type": "tertiary"},
    frozenset(("disgust", "joy")): {"label": "morbidness", "type": "tertiary"},
    frozenset(("anger", "trust")): {"label": "dominance", "type": "tertiary"},
    frozenset(("anticipation", "fear")): {"label": "anxiety", "type": "tertiary"},
}

OPPOSITE_PAIRS = {
    frozenset(("joy", "sadness")),
    frozenset(("trust", "disgust")),
    frozenset(("fear", "anger")),
    frozenset(("surprise", "anticipation")),
}

DYAD_ACCENTS = {
    "love": "#FF7BA7",
    "submission": "#65CFA6",
    "awe": "#8DA2FF",
    "disapproval": "#A7A0B8",
    "remorse": "#7FB69A",
    "contempt": "#B5A64E",
    "aggression": "#FF7043",
    "optimism": "#FFC857",
    "guilt": "#BFA2DB",
    "curiosity": "#4ECDC4",
    "despair": "#5A7BA8",
    "unbelief": "#C084FC",
    "envy": "#87B957",
    "cynicism": "#9A9E53",
    "pride": "#F08A5D",
    "hope": "#6AD7A7",
    "delight": "#FFB86B",
    "sentimentality": "#D9A7C7",
    "shame": "#8C7AA9",
    "outrage": "#FF5A76",
    "pessimism": "#6F8191",
    "morbidness": "#A77F63",
    "dominance": "#D9824B",
    "anxiety": "#7DA0D6",
    "opposite": "#E4E7EC",
}


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


def derive_dyad(primary_family: str, secondary_family: str | None) -> dict | None:
    first = (primary_family or "").strip().lower()
    second = (secondary_family or "").strip().lower()
    if not first or not second or first == second:
        return None
    pair = frozenset((first, second))
    if pair in OPPOSITE_PAIRS:
        return {"label": None, "type": "opposite"}
    found = DYAD_PAIRS.get(pair)
    if found is None:
        return None
    return {"label": found["label"], "type": found["type"]}


def _row_to_entry(row: tuple) -> dict:
    dyad_label = row[10]
    dyad_type = row[11]
    return {
        "id": row[0],
        "timestamp": row[1],
        "local_date": row[2],
        "emotion_family": row[3],
        "emotion_label": row[4],
        "intensity": row[5],
        "note": row[6],
        "created_at": row[7],
        "secondary_emotion_family": row[8],
        "secondary_emotion_label": row[9],
        "dyad_label": dyad_label,
        "dyad_type": dyad_type,
        "dyad_accent": DYAD_ACCENTS.get(dyad_label or dyad_type or "", DYAD_ACCENTS["opposite"]),
    }


class SqliteSagaRepo:
    """Saga entries backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self,
        emotion_family: str,
        emotion_label: str,
        intensity: int,
        note: str | None = None,
        timestamp: str | None = None,
        secondary_emotion_family: str | None = None,
        secondary_emotion_label: str | None = None,
    ) -> dict:
        family = emotion_family.strip().lower()
        if family not in EMOTION_FAMILIES:
            raise ValueError("Unknown emotion family.")
        label = emotion_label.strip().lower()
        if not label:
            raise ValueError("Emotion label is required.")
        secondary_family = (secondary_emotion_family or "").strip().lower() or None
        secondary_label = (secondary_emotion_label or "").strip().lower() or None
        if secondary_family:
            if secondary_family not in EMOTION_FAMILIES:
                raise ValueError("Unknown secondary emotion family.")
            if secondary_family == family:
                secondary_family = None
                secondary_label = None
            elif not secondary_label:
                raise ValueError("Secondary emotion label is required.")
        else:
            secondary_label = None
        dyad = derive_dyad(family, secondary_family)
        value = max(1, min(10, int(intensity)))
        ts = timestamp or _now_iso()
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO saga_entries "
            "(id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at, "
            "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                ts,
                _local_date(ts),
                family,
                label,
                value,
                _clean_note(note),
                now,
                secondary_family,
                secondary_label,
                dyad["label"] if dyad else None,
                dyad["type"] if dyad else None,
            ),
        )
        await self._db.commit()
        return await self.get(eid) or {
            "id": eid,
            "timestamp": ts,
            "local_date": _local_date(ts),
            "emotion_family": family,
            "emotion_label": label,
            "intensity": value,
            "note": _clean_note(note),
            "created_at": now,
            "secondary_emotion_family": secondary_family,
            "secondary_emotion_label": secondary_label,
            "dyad_label": dyad["label"] if dyad else None,
            "dyad_type": dyad["type"] if dyad else None,
            "dyad_accent": DYAD_ACCENTS.get((dyad or {}).get("label") or (dyad or {}).get("type") or "", DYAD_ACCENTS["opposite"]),
        }

    async def get(self, entry_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at, "
            "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
            "FROM saga_entries WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        return _row_to_entry(row) if row else None

    async def update(
        self,
        entry_id: str,
        emotion_family: str,
        emotion_label: str,
        intensity: int,
        note: str | None = None,
        secondary_emotion_family: str | None = None,
        secondary_emotion_label: str | None = None,
    ) -> dict | None:
        family = emotion_family.strip().lower()
        if family not in EMOTION_FAMILIES:
            return None
        label = emotion_label.strip().lower()
        if not label:
            return None
        secondary_family = (secondary_emotion_family or "").strip().lower() or None
        secondary_label = (secondary_emotion_label or "").strip().lower() or None
        if secondary_family:
            if secondary_family not in EMOTION_FAMILIES:
                return None
            if secondary_family == family:
                secondary_family = None
                secondary_label = None
            elif not secondary_label:
                return None
        else:
            secondary_label = None
        dyad = derive_dyad(family, secondary_family)
        value = max(1, min(10, int(intensity)))
        await self._db.execute(
            "UPDATE saga_entries SET emotion_family = ?, emotion_label = ?, intensity = ?, note = ?, "
            "secondary_emotion_family = ?, secondary_emotion_label = ?, dyad_label = ?, dyad_type = ? "
            "WHERE id = ?",
            (
                family,
                label,
                value,
                _clean_note(note),
                secondary_family,
                secondary_label,
                dyad["label"] if dyad else None,
                dyad["type"] if dyad else None,
                entry_id,
            ),
        )
        await self._db.commit()
        return await self.get(entry_id)

    async def delete(self, entry_id: str) -> None:
        await self._db.execute("DELETE FROM saga_entries WHERE id = ?", (entry_id,))
        await self._db.commit()

    async def list_recent(self, limit: int = 8) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at, "
            "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
            "FROM saga_entries ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_by_date(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at, "
            "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
            "FROM saga_entries WHERE local_date = ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_since(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at, "
            "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
            "FROM saga_entries WHERE local_date >= ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]
