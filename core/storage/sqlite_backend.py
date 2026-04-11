"""SQLite storage backend — implements repository protocols using aiosqlite.

Returns the same dict shapes as the JSON backend so core query functions
work identically against either storage layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


class SqliteQuestRepo:
    """Quest repository backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def load_all(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "frog": bool(r[3]),
                "created_at": r[4],
                "started_at": r[5],
                "completed_at": r[6],
            }
            for r in rows
        ]

    async def add(self, title: str) -> dict:
        qid = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO quests (id, title, status, frog, created_at) "
            "VALUES (?, ?, 'log', 0, ?)",
            (qid, title, now),
        )
        await self._db.commit()
        return {
            "id": qid,
            "title": title,
            "status": "log",
            "frog": False,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }

    async def update_status(self, quest_id: str, status: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ?",
            (quest_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        started_at = row[5]
        completed_at = row[6]

        if status == "active" and not started_at:
            started_at = now
        elif status == "done":
            completed_at = now

        await self._db.execute(
            "UPDATE quests SET status = ?, started_at = ?, completed_at = ? "
            "WHERE id = ?",
            (status, started_at, completed_at, quest_id),
        )
        await self._db.commit()
        return {
            "id": quest_id,
            "title": row[1],
            "status": status,
            "frog": bool(row[3]),
            "created_at": row[4],
            "started_at": started_at,
            "completed_at": completed_at,
        }

    async def delete(self, quest_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ?",
            (quest_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        # Remove child records first to satisfy FK constraints
        session_cursor = await self._db.execute(
            "SELECT id FROM pomo_sessions WHERE quest_id = ?", (quest_id,)
        )
        session_ids = [r[0] for r in await session_cursor.fetchall()]
        for sid in session_ids:
            await self._db.execute("DELETE FROM pomo_segments WHERE session_id = ?", (sid,))
        await self._db.execute("DELETE FROM pomo_sessions WHERE quest_id = ?", (quest_id,))
        await self._db.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
        await self._db.commit()
        return {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "frog": bool(row[3]),
            "created_at": row[4],
            "started_at": row[5],
            "completed_at": row[6],
        }

    async def toggle_frog(self, quest_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ?",
            (quest_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        new_frog = not bool(row[3])
        await self._db.execute(
            "UPDATE quests SET frog = ? WHERE id = ?",
            (int(new_frog), quest_id),
        )
        await self._db.commit()
        return {
            "id": quest_id,
            "title": row[1],
            "status": row[2],
            "frog": new_frog,
            "created_at": row[4],
            "started_at": row[5],
            "completed_at": row[6],
        }


class SqlitePomoRepo:
    """Pomo session repository backed by SQLite.

    load_all() returns nested dicts with segments lists, matching the
    JSON backend structure so core query functions work unchanged.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def load_all(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions "
            "FROM pomo_sessions ORDER BY started_at"
        )
        sessions = []
        for r in await cursor.fetchall():
            session = {
                "id": r[0],
                "quest_id": r[1],
                "quest_title": r[2],
                "started_at": r[3],
                "ended_at": r[4],
                "actual_pomos": r[5],
                "status": r[6],
                "streak_peak": r[7],
                "total_interruptions": r[8],
                "segments": [],
            }
            seg_cursor = await self._db.execute(
                "SELECT type, lap, cycle, completed, interruptions, started_at, "
                "ended_at, charge, deed, break_size, interruption_reason, "
                "early_completion, forge_type "
                "FROM pomo_segments WHERE session_id = ? ORDER BY id",
                (r[0],),
            )
            for s in await seg_cursor.fetchall():
                session["segments"].append({
                    "type": s[0],
                    "lap": s[1],
                    "cycle": s[2],
                    "completed": bool(s[3]),
                    "interruptions": s[4],
                    "started_at": s[5],
                    "ended_at": s[6],
                    "charge": s[7],
                    "deed": s[8],
                    "break_size": s[9],
                    "interruption_reason": s[10],
                    "early_completion": bool(s[11]),
                    "forge_type": s[12],
                })
            sessions.append(session)
        return sessions

    async def start_session(self, quest_id: str, quest_title: str) -> dict:
        sid = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO pomo_sessions "
            "(id, quest_id, quest_title, started_at, status, actual_pomos, "
            "streak_peak, total_interruptions) "
            "VALUES (?, ?, ?, ?, 'running', 0, 0, 0)",
            (sid, quest_id, quest_title, now),
        )
        await self._db.commit()
        return {
            "id": sid,
            "quest_id": quest_id,
            "quest_title": quest_title,
            "started_at": now,
            "ended_at": None,
            "segments": [],
            "actual_pomos": 0,
            "status": "running",
            "streak_peak": 0,
            "total_interruptions": 0,
        }

    async def get_session(self, session_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions "
            "FROM pomo_sessions WHERE id = ?",
            (session_id,),
        )
        r = await cursor.fetchone()
        if r is None:
            return None
        session = {
            "id": r[0], "quest_id": r[1], "quest_title": r[2],
            "started_at": r[3], "ended_at": r[4], "actual_pomos": r[5],
            "status": r[6], "streak_peak": r[7], "total_interruptions": r[8],
            "segments": [],
        }
        seg_cursor = await self._db.execute(
            "SELECT type, lap, cycle, completed, interruptions, started_at, "
            "ended_at, charge, deed, break_size, interruption_reason, "
            "early_completion, forge_type "
            "FROM pomo_segments WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        for s in await seg_cursor.fetchall():
            session["segments"].append({
                "type": s[0], "lap": s[1], "cycle": s[2],
                "completed": bool(s[3]), "interruptions": s[4],
                "started_at": s[5], "ended_at": s[6], "charge": s[7],
                "deed": s[8], "break_size": s[9],
                "interruption_reason": s[10],
                "early_completion": bool(s[11]), "forge_type": s[12],
            })
        return session

    async def add_segment(
        self,
        session_id: str,
        seg_type: str,
        lap: int,
        cycle: int,
        completed: bool,
        interruptions: int,
        started_at: str,
        ended_at: str,
        charge: str | None = None,
        deed: str | None = None,
        break_size: str | None = None,
        interruption_reason: str | None = None,
        early_completion: bool = False,
        forge_type: str | None = None,
    ) -> dict | None:
        # Verify session exists
        cursor = await self._db.execute(
            "SELECT id FROM pomo_sessions WHERE id = ?", (session_id,)
        )
        if await cursor.fetchone() is None:
            return None

        await self._db.execute(
            "INSERT INTO pomo_segments "
            "(session_id, type, lap, cycle, completed, interruptions, "
            "started_at, ended_at, charge, deed, break_size, "
            "interruption_reason, early_completion, forge_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, seg_type, lap, cycle, int(completed), interruptions,
             started_at, ended_at, charge, deed, break_size,
             interruption_reason, int(early_completion), forge_type),
        )

        # Update actual_pomos count (hollow forges don't count)
        if seg_type == "work" and completed and forge_type != "hollow":
            await self._db.execute(
                "UPDATE pomo_sessions SET actual_pomos = actual_pomos + 1 "
                "WHERE id = ?",
                (session_id,),
            )

        await self._db.commit()
        return await self.get_session(session_id)

    async def update_segment_deed(
        self, session_id: str, lap: int, deed: str,
        forge_type: str | None = None,
    ) -> None:
        # Find the matching work segment (latest completed work at this lap)
        cursor = await self._db.execute(
            "SELECT id, forge_type FROM pomo_segments "
            "WHERE session_id = ? AND type = 'work' AND lap = ? AND completed = 1 "
            "ORDER BY id DESC LIMIT 1",
            (session_id, lap),
        )
        row = await cursor.fetchone()
        if row is None:
            return

        seg_id = row[0]
        was_hollow = row[1] == "hollow"

        await self._db.execute(
            "UPDATE pomo_segments SET deed = ?, forge_type = ? WHERE id = ?",
            (deed, forge_type, seg_id),
        )

        # If marking as hollow, decrement actual_pomos
        if forge_type == "hollow" and not was_hollow:
            await self._db.execute(
                "UPDATE pomo_sessions SET actual_pomos = MAX(0, actual_pomos - 1) "
                "WHERE id = ?",
                (session_id,),
            )

        await self._db.commit()

    async def end_session(self, session_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT actual_pomos FROM pomo_sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        status = "completed" if row[0] > 0 else "stopped"
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE pomo_sessions SET status = ?, ended_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        await self._db.commit()
        return await self.get_session(session_id)


class SqliteTrophyPRRepo:
    """Trophy personal records backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def load_prs(self) -> dict:
        cursor = await self._db.execute(
            "SELECT trophy_id, best, date, detail FROM trophy_records"
        )
        prs = {}
        for r in await cursor.fetchall():
            tid = r[0]
            if tid.startswith("_"):
                import json
                try:
                    prs[tid] = json.loads(r[3])
                except (json.JSONDecodeError, TypeError):
                    prs[tid] = {"date": r[2]}
            else:
                best = r[1]
                # SQLite stores everything as TEXT; coerce numeric bests back
                try:
                    best = int(best)
                except (ValueError, TypeError):
                    pass
                prs[tid] = {"best": best, "date": r[2], "detail": r[3]}
        return prs

    async def save_prs(self, prs: dict) -> None:
        await self._db.execute("DELETE FROM trophy_records")
        for tid, data in prs.items():
            if tid.startswith("_"):
                # Meta entries like _best_day — store as JSON in detail
                import json
                await self._db.execute(
                    "INSERT INTO trophy_records (trophy_id, best, date, detail) "
                    "VALUES (?, ?, ?, ?)",
                    (tid, "", data.get("date", ""), json.dumps(data)),
                )
            else:
                await self._db.execute(
                    "INSERT INTO trophy_records (trophy_id, best, date, detail) "
                    "VALUES (?, ?, ?, ?)",
                    (tid, str(data["best"]), data["date"], data.get("detail")),
                )
        await self._db.commit()
