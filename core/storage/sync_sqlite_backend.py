"""Synchronous SQLite storage backend — for use with PomoEngine.

PomoEngine calls repo methods synchronously. This backend uses plain sqlite3
(not aiosqlite) so the engine works without async/await. Used as the engine's
repo while the async SqlitePomoRepo handles read-heavy analytics queries.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from core import clock
from pathlib import Path


class SyncSqlitePomoRepo:
    """Sync PomoRepo backed by sqlite3 — implements the sync Protocol."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self._conn.close()

    def load_all(self, workspace_id: str = "work") -> list[dict]:
        cursor = self._conn.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions, workspace_id "
            "FROM pomo_sessions WHERE workspace_id = ? ORDER BY started_at",
            (workspace_id,),
        )
        sessions = []
        for r in cursor.fetchall():
            session = {
                "id": r[0], "quest_id": r[1], "quest_title": r[2],
                "started_at": r[3], "ended_at": r[4], "actual_pomos": r[5],
                "status": r[6], "streak_peak": r[7], "total_interruptions": r[8],
                "workspace_id": r[9],
                "segments": [],
            }
            seg_cursor = self._conn.execute(
                "SELECT type, lap, cycle, completed, interruptions, started_at, "
                "ended_at, charge, deed, break_size, interruption_reason, "
                "early_completion, forge_type, workspace_id "
                "FROM pomo_segments WHERE session_id = ? AND workspace_id = ? ORDER BY id",
                (r[0], workspace_id),
            )
            for s in seg_cursor.fetchall():
                session["segments"].append({
                    "type": s[0], "lap": s[1], "cycle": s[2],
                    "completed": bool(s[3]), "interruptions": s[4],
                    "started_at": s[5], "ended_at": s[6], "charge": s[7],
                    "deed": s[8], "break_size": s[9],
                    "interruption_reason": s[10],
                    "early_completion": bool(s[11]), "forge_type": s[12],
                    "workspace_id": s[13],
                })
            sessions.append(session)
        return sessions

    def start_session(self, quest_id: str, quest_title: str, workspace_id: str = "work") -> dict:
        sid = uuid.uuid4().hex[:8]
        now = clock.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO pomo_sessions "
            "(id, quest_id, quest_title, started_at, status, actual_pomos, "
            "streak_peak, total_interruptions, workspace_id) "
            "VALUES (?, ?, ?, ?, 'running', 0, 0, 0, ?)",
            (sid, quest_id, quest_title, now, workspace_id),
        )
        self._conn.commit()
        return {
            "id": sid, "quest_id": quest_id, "quest_title": quest_title,
            "started_at": now, "ended_at": None, "segments": [],
            "actual_pomos": 0, "status": "running",
            "streak_peak": 0, "total_interruptions": 0,
            "workspace_id": workspace_id,
        }

    def get_session(self, session_id: str) -> dict | None:
        cursor = self._conn.execute(
            "SELECT id, quest_id, quest_title, started_at, ended_at, "
            "actual_pomos, status, streak_peak, total_interruptions, workspace_id "
            "FROM pomo_sessions WHERE id = ?",
            (session_id,),
        )
        r = cursor.fetchone()
        if r is None:
            return None
        session = {
            "id": r[0], "quest_id": r[1], "quest_title": r[2],
            "started_at": r[3], "ended_at": r[4], "actual_pomos": r[5],
            "status": r[6], "streak_peak": r[7], "total_interruptions": r[8],
            "workspace_id": r[9],
            "segments": [],
        }
        seg_cursor = self._conn.execute(
            "SELECT type, lap, cycle, completed, interruptions, started_at, "
            "ended_at, charge, deed, break_size, interruption_reason, "
            "early_completion, forge_type, workspace_id "
            "FROM pomo_segments WHERE session_id = ? AND workspace_id = ? ORDER BY id",
            (session_id, r[9]),
        )
        for s in seg_cursor.fetchall():
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

    def add_segment(
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
        cursor = self._conn.execute(
            "SELECT id, workspace_id FROM pomo_sessions WHERE id = ?", (session_id,)
        )
        session_row = cursor.fetchone()
        if session_row is None:
            return None
        workspace_id = session_row[1]

        self._conn.execute(
            "INSERT INTO pomo_segments "
            "(session_id, type, lap, cycle, completed, interruptions, "
            "started_at, ended_at, charge, deed, break_size, "
            "interruption_reason, early_completion, forge_type, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, seg_type, lap, cycle, int(completed), interruptions,
             started_at, ended_at, charge, deed, break_size,
             interruption_reason, int(early_completion), forge_type, workspace_id),
        )

        if seg_type == "work" and completed and forge_type != "hollow":
            self._conn.execute(
                "UPDATE pomo_sessions SET actual_pomos = actual_pomos + 1 "
                "WHERE id = ?",
                (session_id,),
            )

        self._conn.commit()
        return self.get_session(session_id)

    def update_segment_deed(
        self, session_id: str, lap: int, deed: str,
        forge_type: str | None = None,
    ) -> None:
        cursor = self._conn.execute(
            "SELECT id, forge_type FROM pomo_segments "
            "WHERE session_id = ? AND type = 'work' AND lap = ? AND completed = 1 "
            "ORDER BY id DESC LIMIT 1",
            (session_id, lap),
        )
        row = cursor.fetchone()
        if row is None:
            return

        seg_id = row[0]
        was_hollow = row[1] == "hollow"

        self._conn.execute(
            "UPDATE pomo_segments SET deed = ?, forge_type = ? WHERE id = ?",
            (deed, forge_type, seg_id),
        )

        if forge_type == "hollow" and not was_hollow:
            self._conn.execute(
                "UPDATE pomo_sessions SET actual_pomos = MAX(0, actual_pomos - 1) "
                "WHERE id = ?",
                (session_id,),
            )

        self._conn.commit()

    def end_session(self, session_id: str) -> dict | None:
        cursor = self._conn.execute(
            "SELECT actual_pomos FROM pomo_sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        status = "completed" if row[0] > 0 else "stopped"
        now = clock.utcnow().isoformat()
        self._conn.execute(
            "UPDATE pomo_sessions SET status = ?, ended_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        self._conn.commit()
        return self.get_session(session_id)
