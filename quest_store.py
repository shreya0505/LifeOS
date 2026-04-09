import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

QUESTS_FILE = Path(__file__).parent / "quests.json"


def load_quests():
    if not QUESTS_FILE.exists():
        return []
    with open(QUESTS_FILE) as f:
        return json.load(f)


def save_quests(quests):
    with open(QUESTS_FILE, "w") as f:
        json.dump(quests, f, indent=2)


def add_quest(title):
    quests = load_quests()
    quest = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "status": "log",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
    }
    quests.append(quest)
    save_quests(quests)
    return quest


def delete_quest(quest_id):
    quests = load_quests()
    match  = next((q for q in quests if q["id"] == quest_id), None)
    if not match:
        return None
    save_quests([q for q in quests if q["id"] != quest_id])
    return match


def toggle_frog(quest_id):
    """Toggle the 🐸 frog flag on a quest."""
    quests = load_quests()
    for quest in quests:
        if quest["id"] == quest_id:
            quest["frog"] = not quest.get("frog", False)
            save_quests(quests)
            return quest
    return None


def update_quest(quest_id, status):
    quests = load_quests()
    for quest in quests:
        if quest["id"] == quest_id:
            quest["status"] = status
            now = datetime.now(timezone.utc).isoformat()
            if status == "active" and not quest.get("started_at"):
                quest["started_at"] = now
            elif status == "done":
                quest["completed_at"] = now
            save_quests(quests)
            return quest
    return None
