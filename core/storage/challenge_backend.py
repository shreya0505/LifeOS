"""SQLite storage backend for Hard 90 Challenge."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from core import clock

import aiosqlite


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    return clock.utcnow().isoformat()


def _challenge_cols() -> str:
    return (
        "id, era_name, status, start_date, current_level, current_level_name, "
        "midweek_adjective, days_elapsed, days_remaining, peak_level, is_completed, created_at"
    )


def _challenge_row_to_dict(r: tuple) -> dict:
    return {
        "id": r[0],
        "era_name": r[1],
        "status": r[2],
        "start_date": r[3],
        "current_level": r[4],
        "current_level_name": r[5],
        "midweek_adjective": r[6],
        "days_elapsed": r[7],
        "days_remaining": r[8],
        "peak_level": r[9],
        "is_completed": bool(r[10]),
        "created_at": r[11],
    }


class SqliteChallengeRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, era_name: str, start_date: str, midweek_adjective: str) -> dict:
        cid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO challenges (id, era_name, status, start_date, current_level, "
            "current_level_name, midweek_adjective, days_elapsed, days_remaining, peak_level, "
            "is_completed, created_at) "
            "VALUES (?, ?, 'active', ?, 0, NULL, ?, 0, 90, 0, 0, ?)",
            (cid, era_name, start_date, midweek_adjective, now),
        )
        await self._db.commit()
        return {
            "id": cid, "era_name": era_name, "status": "active",
            "start_date": start_date, "current_level": 0, "current_level_name": None,
            "midweek_adjective": midweek_adjective, "days_elapsed": 0,
            "days_remaining": 90, "peak_level": 0, "is_completed": False,
            "created_at": now,
        }

    async def get_active(self) -> dict | None:
        cursor = await self._db.execute(
            f"SELECT {_challenge_cols()} FROM challenges WHERE status = 'active' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return _challenge_row_to_dict(row) if row else None

    async def get_by_id(self, challenge_id: str) -> dict | None:
        cursor = await self._db.execute(
            f"SELECT {_challenge_cols()} FROM challenges WHERE id = ?",
            (challenge_id,),
        )
        row = await cursor.fetchone()
        return _challenge_row_to_dict(row) if row else None

    async def get_by_start_date(self, start_date: str) -> dict | None:
        cursor = await self._db.execute(
            f"SELECT {_challenge_cols()} FROM challenges WHERE start_date = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (start_date,),
        )
        row = await cursor.fetchone()
        return _challenge_row_to_dict(row) if row else None

    async def update_level(self, challenge_id: str, level: int, level_name: str) -> None:
        await self._db.execute(
            "UPDATE challenges SET current_level = ?, current_level_name = ? WHERE id = ?",
            (level, level_name, challenge_id),
        )
        await self._db.commit()

    async def update_days(self, challenge_id: str, days_elapsed: int) -> None:
        remaining = max(0, 90 - days_elapsed)
        await self._db.execute(
            "UPDATE challenges SET days_elapsed = ?, days_remaining = ? WHERE id = ?",
            (days_elapsed, remaining, challenge_id),
        )
        await self._db.commit()

    async def update_peak_level(self, challenge_id: str, peak: int) -> None:
        await self._db.execute(
            "UPDATE challenges SET peak_level = MAX(peak_level, ?) WHERE id = ?",
            (peak, challenge_id),
        )
        await self._db.commit()

    async def mark_completed(self, challenge_id: str) -> None:
        await self._db.execute(
            "UPDATE challenges SET is_completed = 1, status = 'completed' WHERE id = ?",
            (challenge_id,),
        )
        await self._db.commit()

    async def mark_reset(self, challenge_id: str) -> None:
        await self._db.execute(
            "UPDATE challenges SET status = 'reset' WHERE id = ?", (challenge_id,),
        )
        await self._db.commit()


def _task_row_to_dict(r: tuple) -> dict:
    return {"id": r[0], "challenge_id": r[1], "name": r[2], "bucket": r[3], "created_at": r[4]}


class SqliteChallengeTaskRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create_batch(self, challenge_id: str, tasks: list[dict]) -> list[dict]:
        now = _now_iso()
        out = []
        for t in tasks:
            tid = _gen_id()
            await self._db.execute(
                "INSERT INTO challenge_tasks (id, challenge_id, name, bucket, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (tid, challenge_id, t["name"], t["bucket"], now),
            )
            out.append({"id": tid, "challenge_id": challenge_id,
                        "name": t["name"], "bucket": t["bucket"], "created_at": now})
        await self._db.commit()
        return out

    async def get_by_challenge(self, challenge_id: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, challenge_id, name, bucket, created_at "
            "FROM challenge_tasks WHERE challenge_id = ? "
            "ORDER BY CASE bucket WHEN 'anchor' THEN 1 WHEN 'improver' THEN 2 ELSE 3 END, created_at",
            (challenge_id,),
        )
        rows = await cursor.fetchall()
        return [_task_row_to_dict(r) for r in rows]

    async def get_by_id(self, task_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, challenge_id, name, bucket, created_at "
            "FROM challenge_tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        return _task_row_to_dict(row) if row else None


def _entry_row_to_dict(r: tuple) -> dict:
    return {
        "id": r[0], "task_id": r[1], "challenge_id": r[2], "log_date": r[3],
        "state": r[4], "notes": r[5],
        "hard_fail_triggered": bool(r[6]), "soft_fail_triggered": bool(r[7]),
        "created_at": r[8],
    }


_ENTRY_COLS = "id, task_id, challenge_id, log_date, state, notes, hard_fail_triggered, soft_fail_triggered, created_at"


class SqliteChallengeEntryRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, task_id: str, challenge_id: str, log_date: str,
                     state: str, notes: str | None) -> dict:
        # Check existing
        cursor = await self._db.execute(
            "SELECT id FROM challenge_entries WHERE task_id = ? AND log_date = ?",
            (task_id, log_date),
        )
        existing = await cursor.fetchone()
        if existing:
            eid = existing[0]
            await self._db.execute(
                "UPDATE challenge_entries SET state = ?, notes = ? "
                "WHERE task_id = ? AND log_date = ?",
                (state, notes, task_id, log_date),
            )
        else:
            eid = _gen_id()
            now = _now_iso()
            await self._db.execute(
                f"INSERT INTO challenge_entries ({_ENTRY_COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)",
                (eid, task_id, challenge_id, log_date, state, notes, now),
            )
        await self._db.commit()

        cursor = await self._db.execute(
            f"SELECT {_ENTRY_COLS} FROM challenge_entries WHERE id = ?", (eid,),
        )
        row = await cursor.fetchone()
        return _entry_row_to_dict(row)

    async def get_by_date(self, challenge_id: str, log_date: str) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_ENTRY_COLS} FROM challenge_entries "
            "WHERE challenge_id = ? AND log_date = ?",
            (challenge_id, log_date),
        )
        rows = await cursor.fetchall()
        return [_entry_row_to_dict(r) for r in rows]

    async def get_last_n_for_task(self, task_id: str, n: int) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_ENTRY_COLS} FROM challenge_entries "
            "WHERE task_id = ? ORDER BY log_date DESC LIMIT ?",
            (task_id, n),
        )
        rows = await cursor.fetchall()
        # Return chronological (oldest → newest)
        return list(reversed([_entry_row_to_dict(r) for r in rows]))

    async def get_all_for_task(self, task_id: str) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_ENTRY_COLS} FROM challenge_entries "
            "WHERE task_id = ? ORDER BY log_date",
            (task_id,),
        )
        rows = await cursor.fetchall()
        return [_entry_row_to_dict(r) for r in rows]

    async def get_all_for_challenge(self, challenge_id: str) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_ENTRY_COLS} FROM challenge_entries "
            "WHERE challenge_id = ? ORDER BY log_date, task_id",
            (challenge_id,),
        )
        rows = await cursor.fetchall()
        return [_entry_row_to_dict(r) for r in rows]

    async def mark_fail_triggered(self, entry_id: str, is_hard: bool) -> None:
        col = "hard_fail_triggered" if is_hard else "soft_fail_triggered"
        await self._db.execute(
            f"UPDATE challenge_entries SET {col} = 1 WHERE id = ?", (entry_id,),
        )
        await self._db.commit()


def _era_row_to_dict(r: tuple) -> dict:
    return {
        "id": r[0], "era_name": r[1], "start_date": r[2], "end_date": r[3],
        "duration_days": r[4], "peak_level": r[5], "reset_cause": r[6],
        "reset_trigger_task_id": r[7], "summary_prose": r[8], "created_at": r[9],
    }


_ERA_COLS = "id, era_name, start_date, end_date, duration_days, peak_level, reset_cause, reset_trigger_task_id, summary_prose, created_at"


class SqliteChallengeEraRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, era_name: str, start_date: str, end_date: str,
                     duration_days: int, peak_level: int, reset_cause: str,
                     reset_trigger_task_id: str | None, summary_prose: str) -> dict:
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            f"INSERT INTO challenge_eras ({_ERA_COLS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, era_name, start_date, end_date, duration_days, peak_level,
             reset_cause, reset_trigger_task_id, summary_prose, now),
        )
        await self._db.commit()
        return {
            "id": eid, "era_name": era_name, "start_date": start_date,
            "end_date": end_date, "duration_days": duration_days,
            "peak_level": peak_level, "reset_cause": reset_cause,
            "reset_trigger_task_id": reset_trigger_task_id,
            "summary_prose": summary_prose, "created_at": now,
        }

    async def get_all(self) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_ERA_COLS} FROM challenge_eras ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [_era_row_to_dict(r) for r in rows]

    async def used_names(self) -> set[str]:
        cursor = await self._db.execute("SELECT DISTINCT era_name FROM challenge_eras")
        rows = await cursor.fetchall()
        return {r[0] for r in rows}
