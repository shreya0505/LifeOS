from datetime import date

from pomo_store import load_pomos
from utils import today_local, to_local_date


def get_today_receipt() -> list[dict]:
    """Return today's completed work segments with both charge and deed, sorted by start.
    Falls back to legacy intent/retro keys for data written before v1.1.
    """
    today = today_local().isoformat()
    entries = []
    for s in load_pomos():
        for seg in s["segments"]:
            charge = seg.get("charge") or seg.get("intent")
            deed   = seg.get("deed")   or seg.get("retro")
            if (
                seg["type"] == "work"
                and seg["completed"]
                and charge
                and deed
                and to_local_date(seg.get("started_at", "")) == today
            ):
                entries.append({
                    "quest_title": s["quest_title"],
                    "started_at":  seg["started_at"],
                    "charge":      charge,
                    "deed":        deed,
                    "forge_type":  seg.get("forge_type"),
                })
    entries.sort(key=lambda e: e["started_at"])
    return entries


def get_quest_pomo_total(quest_id: str) -> int:
    """Total completed work pomodoros across all sessions for a quest."""
    return sum(s.get("actual_pomos", 0) for s in load_pomos() if s["quest_id"] == quest_id)


def get_quest_lap_history(quest_id: str) -> dict:
    """Returns {lap_num: 'done'|'broken'} for all work segments of a quest.
    A lap is 'done' if any session completed it; 'broken' if only interrupted.
    """
    history: dict[int, str] = {}
    for s in load_pomos():
        if s["quest_id"] != quest_id:
            continue
        for seg in s["segments"]:
            if seg["type"] != "work":
                continue
            lap = seg["lap"]
            if seg["completed"]:
                history[lap] = "done"
            elif history.get(lap) != "done":
                history[lap] = "broken"
    return history


def get_quest_segment_journey(quest_id: str) -> list[dict]:
    """Return all sessions for a quest in chronological order, each with their segments.
    Used by the per-task journey track to render all-time history.
    Returns list of {'date': 'YYYY-MM-DD', 'session_id': str, 'segments': [...]}.
    """
    sessions = []
    for s in load_pomos():
        if s["quest_id"] != quest_id:
            continue
        if not s.get("segments"):
            continue
        date_str = to_local_date(s.get("started_at") or "")
        sessions.append({
            "date": date_str,
            "session_id": s["id"],
            "segments": s["segments"],
            "status": s.get("status", "running"),
        })
    sessions.sort(key=lambda x: x.get("date", ""))
    return sessions


def get_today_timeline() -> list[dict]:
    """Return all sessions with segments from today, in chronological order.
    Used by the global timeline in the right panel.
    Returns list of {'quest_title', 'session_id', 'started_at', 'segments', 'status'}.
    """
    today = today_local().isoformat()
    result = []
    for s in load_pomos():
        segs_today = [
            seg for seg in s.get("segments", [])
            if to_local_date(seg.get("started_at", "")) == today
        ]
        if to_local_date(s.get("started_at", "")) == today or segs_today:
            result.append({
                "quest_title": s["quest_title"],
                "session_id":  s["id"],
                "started_at":  s.get("started_at", ""),
                "segments":    segs_today,
                "status":      s.get("status", "running"),
            })
    result.sort(key=lambda x: x.get("started_at", ""))
    return result


def get_all_pomo_counts_today() -> dict:
    """Return {quest_id: count} of completed work pomodoros for each quest today.
    Excludes hollow forges.
    """
    today = today_local().isoformat()
    counts: dict[str, int] = {}
    for s in load_pomos():
        qid = s["quest_id"]
        for seg in s["segments"]:
            if (
                seg["type"] == "work"
                and seg["completed"]
                and seg.get("forge_type") != "hollow"
                and to_local_date(seg.get("started_at", "")) == today
            ):
                counts[qid] = counts.get(qid, 0) + 1
    return counts


def get_berserker_stats() -> dict:
    """Return berserker forge stats for chronicle panel.
    Returns {'today': int, 'week': int, 'all_time': int, 'best_day': int, 'best_day_date': str}.
    """
    from datetime import timedelta
    today = today_local()
    today_str = today.isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    daily_counts: dict[str, int] = {}
    total = 0

    for s in load_pomos():
        for seg in s.get("segments", []):
            if seg["type"] == "work" and seg.get("forge_type") == "berserker":
                seg_date = to_local_date(seg.get("started_at", ""))
                daily_counts[seg_date] = daily_counts.get(seg_date, 0) + 1
                total += 1

    today_count = daily_counts.get(today_str, 0)
    week_count = sum(v for d, v in daily_counts.items() if d >= week_start)
    best_day = max(daily_counts.values()) if daily_counts else 0
    best_day_date = ""
    if daily_counts:
        best_day_date = max(daily_counts, key=daily_counts.get)

    return {
        "today": today_count,
        "week": week_count,
        "all_time": total,
        "best_day": best_day,
        "best_day_date": best_day_date,
    }
