"""JSON file storage backend — wraps the original quest/pomo/trophy store logic.

Implements the repository protocols using flat JSON files on disk.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from core import clock
from pathlib import Path


class JsonQuestRepo:
    """Quest repository backed by a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        with open(self._path) as f:
            return json.load(f)

    def _save(self, quests: list[dict]) -> None:
        with open(self._path, "w") as f:
            json.dump(quests, f, indent=2)

    def load_all(self) -> list[dict]:
        quests = self._load()
        for q in quests:
            q.setdefault("checklist", [])
        return quests

    def add(self, title: str) -> dict:
        quests = self._load()
        quest = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "status": "log",
            "created_at": clock.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None,
            "checklist": [],
        }
        quests.append(quest)
        self._save(quests)
        return quest

    def update_status(self, quest_id: str, status: str) -> dict | None:
        quests = self._load()
        for quest in quests:
            if quest["id"] == quest_id:
                quest["status"] = status
                now = clock.utcnow().isoformat()
                if status == "active" and not quest.get("started_at"):
                    quest["started_at"] = now
                elif status == "done":
                    quest["completed_at"] = now
                self._save(quests)
                return quest
        return None

    def abandon(self, quest_id: str) -> dict | None:
        quests = self._load()
        for quest in quests:
            if quest["id"] == quest_id:
                quest["status"] = "abandoned"
                quest["abandoned_at"] = clock.utcnow().isoformat()
                self._save(quests)
                return quest
        return None

    def toggle_frog(self, quest_id: str) -> dict | None:
        quests = self._load()
        for quest in quests:
            if quest["id"] == quest_id:
                quest["frog"] = not quest.get("frog", False)
                self._save(quests)
                return quest
        return None

    def update_checklist(self, quest_id: str, checklist: list[dict]) -> dict | None:
        quests = self._load()
        for quest in quests:
            if quest["id"] == quest_id:
                quest["checklist"] = checklist
                self._save(quests)
                return quest
        return None


class JsonPomoRepo:
    """Pomo session repository backed by a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        with open(self._path) as f:
            return json.load(f)

    def _save(self, pomos: list[dict]) -> None:
        with open(self._path, "w") as f:
            json.dump(pomos, f, indent=2)

    def load_all(self) -> list[dict]:
        return self._load()

    def start_session(self, quest_id: str, quest_title: str) -> dict:
        pomos = self._load()
        session = {
            "id": str(uuid.uuid4())[:8],
            "quest_id": quest_id,
            "quest_title": quest_title,
            "started_at": clock.utcnow().isoformat(),
            "ended_at": None,
            "segments": [],
            "actual_pomos": 0,
            "status": "running",
            "streak_peak": 0,
            "total_interruptions": 0,
        }
        pomos.append(session)
        self._save(pomos)
        return session

    def get_session(self, session_id: str) -> dict | None:
        for s in self._load():
            if s["id"] == session_id:
                return s
        return None

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
        pomos = self._load()
        for s in pomos:
            if s["id"] == session_id:
                s["segments"].append({
                    "type": seg_type,
                    "lap": lap,
                    "cycle": cycle,
                    "completed": completed,
                    "interruptions": interruptions,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "charge": charge,
                    "deed": deed,
                    "break_size": break_size,
                    "interruption_reason": interruption_reason,
                    "early_completion": early_completion,
                    "forge_type": forge_type,
                })
                # Hollow forges don't count as real pomos
                if seg_type == "work" and completed and forge_type != "hollow":
                    s["actual_pomos"] += 1
                self._save(pomos)
                return s
        return None

    def update_segment_deed(
        self, session_id: str, lap: int, deed: str,
        forge_type: str | None = None,
    ) -> None:
        pomos = self._load()
        for s in pomos:
            if s["id"] != session_id:
                continue
            for seg in reversed(s["segments"]):
                if seg["type"] == "work" and seg["lap"] == lap and seg["completed"]:
                    seg["deed"] = deed
                    if forge_type is not None:
                        seg["forge_type"] = forge_type
                    # If marking as hollow, undo the actual_pomos increment
                    if forge_type == "hollow":
                        s["actual_pomos"] = max(0, s.get("actual_pomos", 1) - 1)
                    self._save(pomos)
                    return

    def end_session(self, session_id: str) -> dict | None:
        pomos = self._load()
        for s in pomos:
            if s["id"] == session_id:
                s["status"] = "completed" if s["actual_pomos"] > 0 else "stopped"
                s["ended_at"] = clock.utcnow().isoformat()
                self._save(pomos)
                return s
        return None


class JsonTrophyPRRepo:
    """Trophy personal records backed by a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load_prs(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path) as f:
            return json.load(f)

    def save_prs(self, prs: dict) -> None:
        with open(self._path, "w") as f:
            json.dump(prs, f, indent=2)
