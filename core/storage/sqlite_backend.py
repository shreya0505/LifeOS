"""SQLite storage backend — implements repository protocols using aiosqlite.

Returns the same dict shapes as the JSON backend so core query functions
work identically against either storage layer.
"""

from __future__ import annotations

import json
import uuid
from core import clock

import aiosqlite

DEFAULT_WORKSPACE_ID = "work"


class SqliteWorkspaceRepo:
    """Workspace registry backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_workspaces(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, icon, color, sort_order "
            "FROM workspaces WHERE deleted_at IS NULL ORDER BY sort_order, name"
        )
        return [
            {"id": r[0], "name": r[1], "icon": r[2], "color": r[3], "sort_order": r[4]}
            for r in await cursor.fetchall()
        ]

    async def get(self, workspace_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, name, icon, color, sort_order FROM workspaces "
            "WHERE id = ? AND deleted_at IS NULL",
            (workspace_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "icon": row[2], "color": row[3], "sort_order": row[4]}

    async def create(self, name: str, icon: str, color: str) -> dict:
        name = name.strip()
        wid = uuid.uuid4().hex[:8]
        cursor = await self._db.execute("SELECT MAX(sort_order) FROM workspaces")
        row = await cursor.fetchone()
        sort_order = (row[0] or 0) + 10
        await self._db.execute(
            "INSERT OR IGNORE INTO workspaces (id, name, icon, color, sort_order) VALUES (?, ?, ?, ?, ?)",
            (wid, name, icon, color, sort_order),
        )
        await self._db.commit()
        cursor = await self._db.execute(
            "SELECT id, name, icon, color, sort_order FROM workspaces WHERE name = ? AND deleted_at IS NULL",
            (name,),
        )
        row = await cursor.fetchone()
        return {"id": row[0], "name": row[1], "icon": row[2], "color": row[3], "sort_order": row[4]}


class SqliteQuestRepo:
    """Quest repository backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def load_all(self, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at, abandoned_at, "
            "checklist, priority, project, labels, artifacts, workspace_id "
            "FROM quests WHERE workspace_id = ? ORDER BY frog DESC, priority ASC, created_at ASC",
            (workspace_id,),
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
                "abandoned_at": r[7],
                "checklist": json.loads(r[8] or "[]"),
                "priority": r[9] if r[9] is not None else 4,
                "project": r[10],
                "labels": json.loads(r[11] or "[]"),
                "artifacts": json.loads(r[12] or "{}"),
                "workspace_id": r[13],
            }
            for r in rows
        ]

    async def add(
        self,
        title: str,
        *,
        priority: int = 4,
        project: str | None = None,
        labels: list | None = None,
        artifacts: dict | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict:
        qid = uuid.uuid4().hex[:8]
        now = clock.utcnow().isoformat()
        labels_json = json.dumps(labels or [])
        artifacts_json = json.dumps(artifacts or {})
        await self._db.execute(
            "INSERT INTO quests (id, title, status, frog, created_at, priority, project, labels, artifacts, workspace_id) "
            "VALUES (?, ?, 'log', 0, ?, ?, ?, ?, ?, ?)",
            (qid, title, now, priority, project, labels_json, artifacts_json, workspace_id),
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
            "abandoned_at": None,
            "checklist": [],
            "priority": priority,
            "project": project,
            "labels": labels or [],
            "artifacts": artifacts or {},
            "workspace_id": workspace_id,
        }

    async def update_status(
        self, quest_id: str, status: str, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ? AND workspace_id = ?",
            (quest_id, workspace_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        now = clock.utcnow().isoformat()
        started_at = row[5]
        completed_at = row[6]

        if status == "active" and not started_at:
            started_at = now
        elif status == "done":
            completed_at = now

        await self._db.execute(
            "UPDATE quests SET status = ?, started_at = ?, completed_at = ? "
            "WHERE id = ? AND workspace_id = ?",
            (status, started_at, completed_at, quest_id, workspace_id),
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
            "workspace_id": workspace_id,
        }

    async def abandon(self, quest_id: str, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ? AND workspace_id = ?",
            (quest_id, workspace_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        now = clock.utcnow().isoformat()
        await self._db.execute(
            "UPDATE quests SET status = 'abandoned', abandoned_at = ? WHERE id = ? AND workspace_id = ?",
            (now, quest_id, workspace_id),
        )
        await self._db.commit()
        return {
            "id": row[0],
            "title": row[1],
            "status": "abandoned",
            "frog": bool(row[3]),
            "created_at": row[4],
            "started_at": row[5],
            "completed_at": row[6],
            "abandoned_at": now,
            "workspace_id": workspace_id,
        }

    async def toggle_frog(self, quest_id: str, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at "
            "FROM quests WHERE id = ? AND workspace_id = ?",
            (quest_id, workspace_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        new_frog = not bool(row[3])
        await self._db.execute(
            "UPDATE quests SET frog = ? WHERE id = ? AND workspace_id = ?",
            (int(new_frog), quest_id, workspace_id),
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
            "workspace_id": workspace_id,
        }

    async def update_checklist(
        self, quest_id: str, checklist: list[dict], workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at, abandoned_at "
            "FROM quests WHERE id = ? AND workspace_id = ?",
            (quest_id, workspace_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        await self._db.execute(
            "UPDATE quests SET checklist = ? WHERE id = ? AND workspace_id = ?",
            (json.dumps(checklist), quest_id, workspace_id),
        )
        await self._db.commit()
        return {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "frog": bool(row[3]),
            "created_at": row[4],
            "started_at": row[5],
            "completed_at": row[6],
            "abandoned_at": row[7],
            "checklist": checklist,
            "workspace_id": workspace_id,
        }

    async def _load_quest(self, quest_id: str, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, title, status, frog, created_at, started_at, completed_at, abandoned_at, "
            "checklist, priority, project, labels, artifacts, workspace_id "
            "FROM quests WHERE id = ? AND workspace_id = ?",
            (quest_id, workspace_id),
        )
        r = await cursor.fetchone()
        if r is None:
            return None
        return {
            "id": r[0], "title": r[1], "status": r[2], "frog": bool(r[3]),
            "created_at": r[4], "started_at": r[5], "completed_at": r[6],
            "abandoned_at": r[7], "checklist": json.loads(r[8] or "[]"),
            "priority": r[9] if r[9] is not None else 4, "project": r[10],
            "labels": json.loads(r[11] or "[]"),
            "artifacts": json.loads(r[12] or "{}"),
            "workspace_id": r[13],
        }

    async def update_priority(
        self, quest_id: str, priority: int, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        if not 0 <= priority <= 4:
            return None
        await self._db.execute(
            "UPDATE quests SET priority = ? WHERE id = ? AND workspace_id = ?",
            (priority, quest_id, workspace_id),
        )
        await self._db.commit()
        return await self._load_quest(quest_id, workspace_id)

    async def update_project(
        self, quest_id: str, project: str | None, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        val = project.strip() if project else None
        await self._db.execute(
            "UPDATE quests SET project = ? WHERE id = ? AND workspace_id = ?",
            (val or None, quest_id, workspace_id),
        )
        await self._db.commit()
        return await self._load_quest(quest_id, workspace_id)

    async def update_labels(
        self, quest_id: str, labels: list[str], workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        await self._db.execute(
            "UPDATE quests SET labels = ? WHERE id = ? AND workspace_id = ?",
            (json.dumps(labels), quest_id, workspace_id),
        )
        await self._db.commit()
        return await self._load_quest(quest_id, workspace_id)

    async def update_artifacts(
        self, quest_id: str, artifacts: dict, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict | None:
        await self._db.execute(
            "UPDATE quests SET artifacts = ? WHERE id = ? AND workspace_id = ?",
            (json.dumps(artifacts), quest_id, workspace_id),
        )
        await self._db.commit()
        return await self._load_quest(quest_id, workspace_id)


class SqliteArtifactKeyRepo:
    """Artifact key registry backed by SQLite."""

    def __init__(self, db, workspace_id: str = DEFAULT_WORKSPACE_ID) -> None:
        self._db = db
        self._workspace_id = workspace_id

    async def list_keys(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, icon, sort_order FROM artifact_keys "
            "WHERE workspace_id = ? ORDER BY sort_order, name",
            (self._workspace_id,),
        )
        return [
            {"id": r[0], "name": r[1], "icon": r[2], "sort_order": r[3]}
            for r in await cursor.fetchall()
        ]

    async def add_key(self, name: str, icon: str | None = None) -> dict:
        name = name.strip()
        key_id = uuid.uuid4().hex[:8]
        cursor = await self._db.execute(
            "SELECT MAX(sort_order) FROM artifact_keys WHERE workspace_id = ?",
            (self._workspace_id,),
        )
        row = await cursor.fetchone()
        sort_order = (row[0] or 0) + 10
        await self._db.execute(
            "INSERT OR IGNORE INTO artifact_keys (id, workspace_id, name, icon, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (key_id, self._workspace_id, name, icon, sort_order),
        )
        await self._db.commit()
        cursor = await self._db.execute(
            "SELECT id, name, icon, sort_order FROM artifact_keys WHERE workspace_id = ? AND name = ?",
            (self._workspace_id, name),
        )
        row = await cursor.fetchone()
        return {"id": row[0], "name": row[1], "icon": row[2], "sort_order": row[3]}

    async def rename_key(self, old: str, new: str) -> None:
        new = new.strip()
        await self._db.execute(
            "UPDATE artifact_keys SET name = ? WHERE workspace_id = ? AND name = ?",
            (new, self._workspace_id, old),
        )
        await self._db.commit()

    async def delete_key(self, name: str) -> None:
        await self._db.execute(
            "DELETE FROM artifact_keys WHERE workspace_id = ? AND name = ?",
            (self._workspace_id, name),
        )
        await self._db.commit()

    async def reorder(self, names_in_order: list[str]) -> None:
        for i, name in enumerate(names_in_order):
            await self._db.execute(
                "UPDATE artifact_keys SET sort_order = ? WHERE workspace_id = ? AND name = ?",
                ((i + 1) * 10, self._workspace_id, name),
            )
        await self._db.commit()


class SqlitePomoRepo:
    """Pomo session repository backed by SQLite.

    load_all() returns nested dicts with segments lists, matching the
    JSON backend structure so core query functions work unchanged.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def load_all(self, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions, workspace_id "
            "FROM pomo_sessions WHERE workspace_id = ? ORDER BY started_at",
            (workspace_id,),
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
                "workspace_id": r[9],
                "segments": [],
            }
            seg_cursor = await self._db.execute(
                "SELECT type, lap, cycle, completed, interruptions, started_at, "
                "ended_at, charge, deed, break_size, interruption_reason, "
                "early_completion, forge_type, workspace_id "
                "FROM pomo_segments WHERE session_id = ? AND workspace_id = ? ORDER BY id",
                (r[0], workspace_id),
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
                    "workspace_id": s[13],
                })
            sessions.append(session)
        return sessions

    async def start_session(
        self, quest_id: str, quest_title: str, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict:
        sid = uuid.uuid4().hex[:8]
        now = clock.utcnow().isoformat()
        await self._db.execute(
            "INSERT INTO pomo_sessions "
            "(id, quest_id, quest_title, started_at, status, actual_pomos, "
            "streak_peak, total_interruptions, workspace_id) "
            "VALUES (?, ?, ?, ?, 'running', 0, 0, 0, ?)",
            (sid, quest_id, quest_title, now, workspace_id),
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
            "workspace_id": workspace_id,
        }

    async def get_session(self, session_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions, workspace_id "
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
            "workspace_id": r[9],
            "segments": [],
        }
        seg_cursor = await self._db.execute(
            "SELECT type, lap, cycle, completed, interruptions, started_at, "
            "ended_at, charge, deed, break_size, interruption_reason, "
            "early_completion, forge_type, workspace_id "
            "FROM pomo_segments WHERE session_id = ? AND workspace_id = ? ORDER BY id",
            (session_id, r[9]),
        )
        for s in await seg_cursor.fetchall():
            session["segments"].append({
                "type": s[0], "lap": s[1], "cycle": s[2],
                "completed": bool(s[3]), "interruptions": s[4],
                "started_at": s[5], "ended_at": s[6], "charge": s[7],
                "deed": s[8], "break_size": s[9],
                "interruption_reason": s[10],
                "early_completion": bool(s[11]), "forge_type": s[12],
                "workspace_id": s[13],
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
            "SELECT id, workspace_id FROM pomo_sessions WHERE id = ?", (session_id,)
        )
        session_row = await cursor.fetchone()
        if session_row is None:
            return None
        workspace_id = session_row[1]

        await self._db.execute(
            "INSERT INTO pomo_segments "
            "(session_id, type, lap, cycle, completed, interruptions, "
            "started_at, ended_at, charge, deed, break_size, "
            "interruption_reason, early_completion, forge_type, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, seg_type, lap, cycle, int(completed), interruptions,
             started_at, ended_at, charge, deed, break_size,
             interruption_reason, int(early_completion), forge_type, workspace_id),
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
        now = clock.utcnow().isoformat()
        await self._db.execute(
            "UPDATE pomo_sessions SET status = ?, ended_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        await self._db.commit()
        return await self.get_session(session_id)


class SqliteTrophyPRRepo:
    """Trophy personal records backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection, workspace_id: str = DEFAULT_WORKSPACE_ID) -> None:
        self._db = db
        self._workspace_id = workspace_id

    async def load_prs(self) -> dict:
        cursor = await self._db.execute(
            "SELECT trophy_id, best, date, detail FROM trophy_records WHERE workspace_id = ?",
            (self._workspace_id,),
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
        import json
        cursor = await self._db.execute(
            "SELECT trophy_id, best, date, detail FROM trophy_records WHERE workspace_id = ?",
            (self._workspace_id,),
        )
        existing = {
            r[0]: (r[1] or "", r[2] or "", r[3])
            for r in await cursor.fetchall()
        }
        desired = {}
        for tid, data in prs.items():
            record_id = f"{self._workspace_id}:{tid}"
            if tid.startswith("_"):
                desired[tid] = (record_id, self._workspace_id, tid, "", data.get("date", ""), json.dumps(data))
            else:
                desired[tid] = (record_id, self._workspace_id, tid, str(data["best"]), data["date"], data.get("detail"))

        rows = [
            row for tid, row in desired.items()
            if existing.get(tid) != row[3:]
        ]
        stale_ids = tuple(tid for tid in existing if tid not in desired)

        if not rows and not stale_ids:
            return

        # Only write changed rows; trophy panels render often, and no-op writes
        # would otherwise create noisy sync_changes entries.
        if rows:
            await self._db.executemany(
                "INSERT INTO trophy_records (id, workspace_id, trophy_id, best, date, detail) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(workspace_id, trophy_id) DO UPDATE SET "
                "best = excluded.best, date = excluded.date, detail = excluded.detail",
                rows,
            )
        if stale_ids:
            placeholders = ",".join("?" * len(stale_ids))
            await self._db.execute(
                f"DELETE FROM trophy_records WHERE workspace_id = ? AND trophy_id IN ({placeholders})",
                (self._workspace_id, *stale_ids),
            )
        await self._db.commit()
