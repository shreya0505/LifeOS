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

MIXED_EMOTIONS = {
    "anticipation": {"with": "joy", "label": "optimism"},
    "joy": {"with": "trust", "label": "love"},
    "trust": {"with": "fear", "label": "submission"},
    "fear": {"with": "surprise", "label": "awe"},
    "surprise": {"with": "sadness", "label": "disapproval"},
    "sadness": {"with": "disgust", "label": "remorse"},
    "disgust": {"with": "anger", "label": "contempt"},
    "anger": {"with": "anticipation", "label": "aggressiveness"},
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
    return cleaned[:200] or None


def _row_to_entry(row: tuple) -> dict:
    return {
        "id": row[0],
        "timestamp": row[1],
        "local_date": row[2],
        "emotion_family": row[3],
        "emotion_label": row[4],
        "intensity": row[5],
        "note": row[6],
        "created_at": row[7],
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
    ) -> dict:
        family = emotion_family.strip().lower()
        if family not in EMOTION_FAMILIES:
            raise ValueError("Unknown emotion family.")
        label = emotion_label.strip().lower()
        if not label:
            raise ValueError("Emotion label is required.")
        value = max(1, min(10, int(intensity)))
        ts = timestamp or _now_iso()
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO saga_entries "
            "(id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, ts, _local_date(ts), family, label, value, _clean_note(note), now),
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
        }

    async def get(self, entry_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at "
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
    ) -> dict | None:
        family = emotion_family.strip().lower()
        if family not in EMOTION_FAMILIES:
            return None
        label = emotion_label.strip().lower()
        if not label:
            return None
        value = max(1, min(10, int(intensity)))
        await self._db.execute(
            "UPDATE saga_entries SET emotion_family = ?, emotion_label = ?, intensity = ?, note = ? "
            "WHERE id = ?",
            (family, label, value, _clean_note(note), entry_id),
        )
        await self._db.commit()
        return await self.get(entry_id)

    async def delete(self, entry_id: str) -> None:
        await self._db.execute("DELETE FROM saga_entries WHERE id = ?", (entry_id,))
        await self._db.commit()

    async def list_recent(self, limit: int = 8) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at "
            "FROM saga_entries ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_by_date(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at "
            "FROM saga_entries WHERE local_date = ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]

    async def list_since(self, local_date: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, timestamp, local_date, emotion_family, emotion_label, intensity, note, created_at "
            "FROM saga_entries WHERE local_date >= ? ORDER BY timestamp",
            (local_date,),
        )
        return [_row_to_entry(row) for row in await cursor.fetchall()]
