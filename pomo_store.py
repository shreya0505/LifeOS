import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from config import POMO_CONFIG

POMOS_FILE = Path(__file__).parent / "pomodoros.json"


def load_pomos() -> list[dict]:
    if not POMOS_FILE.exists():
        return []
    with open(POMOS_FILE) as f:
        return json.load(f)


def save_pomos(pomos: list[dict]) -> None:
    with open(POMOS_FILE, "w") as f:
        json.dump(pomos, f, indent=2)


def start_session(quest_id: str, quest_title: str) -> dict:
    pomos = load_pomos()
    session = {
        "id": str(uuid.uuid4())[:8],
        "quest_id": quest_id,
        "quest_title": quest_title,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "segments": [],
        "actual_pomos": 0,
        "status": "running",
        "streak_peak": 0,
        "total_interruptions": 0,
    }
    pomos.append(session)
    save_pomos(pomos)
    return session


def get_session(session_id: str) -> dict | None:
    for s in load_pomos():
        if s["id"] == session_id:
            return s
    return None


def add_segment(
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
    pomos = load_pomos()
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
            save_pomos(pomos)
            return s
    return None


def update_segment_deed(session_id: str, lap: int, deed: str,
                        forge_type: str | None = None) -> None:
    """Set deed and optional forge_type on the most-recently added completed work segment."""
    pomos = load_pomos()
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
                save_pomos(pomos)
                return


def end_session(session_id: str) -> dict | None:
    pomos = load_pomos()
    for s in pomos:
        if s["id"] == session_id:
            s["status"] = "completed" if s["actual_pomos"] > 0 else "stopped"
            s["ended_at"] = datetime.now(timezone.utc).isoformat()
            save_pomos(pomos)
            return s
    return None
