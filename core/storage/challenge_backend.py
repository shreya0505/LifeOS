"""SQLite storage backend for Hard 90 Challenge."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from core import clock

import aiosqlite

from core.challenge import config as C


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


def _experiment_row_to_dict(r: tuple) -> dict:
    return {
        "id": r[0],
        "challenge_id": r[1],
        "action": r[2],
        "motivation": r[3],
        "timeframe": r[4],
        "status": r[5],
        "started_at": r[6],
        "ends_at": r[7],
        "verdict": r[8],
        "observation_notes": r[9],
        "conclusion_notes": r[10],
        "created_at": r[11],
        "era_name": r[12] if len(r) > 12 else None,
    }


_EXPERIMENT_COLS = (
    "e.id, e.challenge_id, e.action, e.motivation, e.timeframe, e.status, "
    "e.started_at, e.ends_at, e.verdict, e.observation_notes, e.conclusion_notes, "
    "e.created_at, c.era_name"
)


def _experiment_entry_row_to_dict(r: tuple) -> dict:
    return {
        "id": r[0],
        "experiment_id": r[1],
        "challenge_id": r[2],
        "log_date": r[3],
        "state": r[4],
        "notes": r[5],
        "created_at": r[6],
    }


_EXPERIMENT_ENTRY_COLS = "id, experiment_id, challenge_id, log_date, state, notes, created_at"


class SqliteChallengeExperimentRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, challenge_id: str, action: str, motivation: str, timeframe: str) -> dict:
        eid = _gen_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO challenge_experiments "
            "(id, challenge_id, action, motivation, timeframe, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (eid, challenge_id, action, motivation, timeframe, now),
        )
        await self._db.commit()
        exp = await self.get_by_id(eid)
        return exp or {
            "id": eid,
            "challenge_id": challenge_id,
            "action": action,
            "motivation": motivation,
            "timeframe": timeframe,
            "status": "draft",
            "started_at": None,
            "ends_at": None,
            "verdict": None,
            "observation_notes": None,
            "conclusion_notes": None,
            "created_at": now,
            "era_name": None,
        }

    async def get_by_id(self, experiment_id: str) -> dict | None:
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_COLS} "
            "FROM challenge_experiments e "
            "LEFT JOIN challenges c ON c.id = e.challenge_id "
            "WHERE e.id = ?",
            (experiment_id,),
        )
        row = await cursor.fetchone()
        return _experiment_row_to_dict(row) if row else None

    async def get_all(self) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_COLS} "
            "FROM challenge_experiments e "
            "LEFT JOIN challenges c ON c.id = e.challenge_id "
            "ORDER BY CASE e.status WHEN 'running' THEN 1 WHEN 'draft' THEN 2 ELSE 3 END, "
            "COALESCE(e.started_at, e.created_at) DESC, e.created_at DESC"
        )
        rows = await cursor.fetchall()
        return [_experiment_row_to_dict(r) for r in rows]

    async def get_for_today(self, log_date: str) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_COLS}, ee.state, ee.notes "
            "FROM challenge_experiments e "
            "LEFT JOIN challenges c ON c.id = e.challenge_id "
            "LEFT JOIN challenge_experiment_entries ee "
            "  ON ee.experiment_id = e.id AND ee.log_date = ? "
            "WHERE e.status IN ('draft','running') "
            "ORDER BY CASE e.status WHEN 'running' THEN 1 ELSE 2 END, "
            "COALESCE(e.started_at, e.created_at), e.created_at",
            (log_date,),
        )
        rows = await cursor.fetchall()
        out = []
        for row in rows:
            exp = _experiment_row_to_dict(row[:13])
            exp["current_state"] = row[13]
            exp["current_notes"] = row[14] or ""
            out.append(exp)
        return out

    async def running_count(self) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM challenge_experiments WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        return int(row[0] if row else 0)

    async def start(self, experiment_id: str, start_date: str) -> dict | None:
        exp = await self.get_by_id(experiment_id)
        if exp is None or exp["status"] != "draft":
            return None
        if await self.running_count() >= 3:
            return None
        duration = C.EXPERIMENT_TIMEFRAME_DAYS[exp["timeframe"]]
        ends_at = (date.fromisoformat(start_date) + timedelta(days=duration - 1)).isoformat()
        await self._db.execute(
            "UPDATE challenge_experiments "
            "SET status = 'running', started_at = ?, ends_at = ? "
            "WHERE id = ? AND status = 'draft'",
            (start_date, ends_at, experiment_id),
        )
        await self._db.commit()
        return await self.get_by_id(experiment_id)

    async def judge(
        self,
        experiment_id: str,
        verdict: str,
        observation_notes: str | None,
        conclusion_notes: str | None,
    ) -> dict | None:
        exp = await self.get_by_id(experiment_id)
        if exp is None or exp["status"] != "running":
            return None
        await self._db.execute(
            "UPDATE challenge_experiments "
            "SET status = 'judged', verdict = ?, observation_notes = ?, conclusion_notes = ? "
            "WHERE id = ? AND status = 'running'",
            (verdict, observation_notes, conclusion_notes, experiment_id),
        )
        await self._db.commit()
        return await self.get_by_id(experiment_id)

    async def abandon(self, experiment_id: str) -> dict | None:
        exp = await self.get_by_id(experiment_id)
        if exp is None or exp["status"] != "running":
            return None
        await self._db.execute(
            "UPDATE challenge_experiments SET status = 'abandoned' "
            "WHERE id = ? AND status = 'running'",
            (experiment_id,),
        )
        await self._db.commit()
        return await self.get_by_id(experiment_id)

    async def trash_draft(self, experiment_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM challenge_experiments WHERE id = ? AND status = 'draft'",
            (experiment_id,),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def upsert_entry(
        self,
        experiment_id: str,
        challenge_id: str,
        log_date: str,
        state: str,
        notes: str | None,
    ) -> dict:
        cursor = await self._db.execute(
            "SELECT id FROM challenge_experiment_entries "
            "WHERE experiment_id = ? AND log_date = ?",
            (experiment_id, log_date),
        )
        existing = await cursor.fetchone()
        if existing:
            entry_id = existing[0]
            await self._db.execute(
                "UPDATE challenge_experiment_entries SET state = ?, notes = ? "
                "WHERE experiment_id = ? AND log_date = ?",
                (state, notes, experiment_id, log_date),
            )
        else:
            entry_id = _gen_id()
            now = _now_iso()
            await self._db.execute(
                f"INSERT INTO challenge_experiment_entries ({_EXPERIMENT_ENTRY_COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry_id, experiment_id, challenge_id, log_date, state, notes, now),
            )
        await self._db.commit()
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_ENTRY_COLS} FROM challenge_experiment_entries WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        return _experiment_entry_row_to_dict(row)

    async def get_entries_for_experiment(self, experiment_id: str) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_ENTRY_COLS} FROM challenge_experiment_entries "
            "WHERE experiment_id = ? ORDER BY log_date",
            (experiment_id,),
        )
        rows = await cursor.fetchall()
        return [_experiment_entry_row_to_dict(r) for r in rows]

    async def get_all_entries(self) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT {_EXPERIMENT_ENTRY_COLS} FROM challenge_experiment_entries "
            "ORDER BY log_date, experiment_id"
        )
        rows = await cursor.fetchall()
        return [_experiment_entry_row_to_dict(r) for r in rows]
