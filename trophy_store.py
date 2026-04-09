"""Trophy computation and personal-record persistence for the Hall of Valor.

All 7 trophies are computed from a single pass over today's pomo segments
plus a quick quest lookup.  PRs are single-day bests (no streaks).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from pomo_store import load_pomos
from quest_store import load_quests
from config import USER_TZ
from utils import today_local, to_local_date


def _to_local_date(iso_str: str) -> str:
    return to_local_date(iso_str)

TROPHIES_FILE = Path(__file__).parent / "trophies.json"

# ── Trophy definitions ───────────────────────────────────────────────────────

TROPHY_DEFS: list[dict] = [
    {
        "id": "frog_slayer",
        "name": "Frog Slayer",
        "icon": "🐸",
        "desc": "Eat your most dreaded task — bonus for doing it first",
        "tiers": {
            "bronze": "Frog eaten",
            "silver": "Eaten before noon",
            "gold":   "Eaten as first completed quest",
        },
        "pr_label": "Earliest frog completion",
    },
    {
        "id": "swamp_clearer",
        "name": "Swamp Clearer",
        "icon": "🐸",
        "desc": "Power through multiple dreaded tasks in one day",
        "tiers": {
            "bronze": "1 frog",
            "silver": "2 frogs",
            "gold":   "4 frogs",
        },
        "pr_label": "Most frogs in a day",
    },
    {
        "id": "forge_master",
        "name": "Forge Master",
        "icon": "🔨",
        "desc": "Deep work hours — real focused pomodoros completed",
        "tiers": {
            "bronze": "2 pomos (~1hr)",
            "silver": "6 pomos (~3hr)",
            "gold":   "10 pomos (~5hr)",
        },
        "pr_label": "Most pomos in a day",
    },
    {
        "id": "untouchable",
        "name": "Untouchable",
        "icon": "🛡️",
        "desc": "Consecutive pomos with zero interruptions",
        "tiers": {
            "bronze": "2 clean streak",
            "silver": "4 clean streak",
            "gold":   "7 clean streak",
        },
        "pr_label": "Longest clean run in a day",
    },
    {
        "id": "quest_closer",
        "name": "Quest Closer",
        "icon": "⚔️",
        "desc": "Close quests — move tasks to done and clear the board",
        "tiers": {
            "bronze": "3 quests",
            "silver": "5 quests",
            "gold":   "8 quests",
        },
        "pr_label": "Most quests closed in a day",
    },
    {
        "id": "scribe",
        "name": "Scribe",
        "icon": "📜",
        "desc": "Log your intent before and result after every pomo",
        "tiers": {
            "bronze": "1 documented",
            "silver": "3 documented",
            "gold":   "Every pomo today",
        },
        "pr_label": "Best documented count",
    },
    {
        "id": "ironclad",
        "name": "Ironclad",
        "icon": "☕",
        "desc": "Take your breaks — recovery is part of the fight",
        "tiers": {
            "bronze": "1 break taken",
            "silver": "3 breaks taken",
            "gold":   "Every pomo today",
        },
        "pr_label": "Best recovery % in a day",
    },
]


# ── PR persistence ───────────────────────────────────────────────────────────

def _load_prs() -> dict:
    if not TROPHIES_FILE.exists():
        return {}
    with open(TROPHIES_FILE) as f:
        return json.load(f)


def _save_prs(prs: dict) -> None:
    with open(TROPHIES_FILE, "w") as f:
        json.dump(prs, f, indent=2)


# ── Core computation ─────────────────────────────────────────────────────────

def compute_trophies() -> dict:
    """Compute all trophy states for today.

    Returns {
        "trophies": [ {id, name, icon, desc, tier, progress, target, pr, ...} ],
        "summary": { "gold": N, "silver": N, "bronze": N, "locked": N },
        "best_day": { "count": N, "date": "..." },
    }
    """
    today_str = today_local().isoformat()
    sessions = load_pomos()
    quests = load_quests()
    prs = _load_prs()

    # ── Gather today's work segments ─────────────────────────────────────
    today_pomos = 0
    today_clean_streak = 0
    best_clean_streak = 0
    today_documented = 0
    today_breaks_taken = 0
    today_break_opportunities = 0
    current_clean = 0

    for s in sessions:
        segs = s.get("segments", [])
        for i, seg in enumerate(segs):
            seg_date = _to_local_date(seg.get("started_at", ""))
            if seg_date != today_str:
                continue
            if seg["type"] == "work" and seg.get("completed"):
                # Hollow forges don't count toward trophies
                if seg.get("forge_type") == "hollow":
                    continue
                today_pomos += 1
                # Clean streak
                if seg.get("interruptions", 0) == 0:
                    current_clean += 1
                    best_clean_streak = max(best_clean_streak, current_clean)
                else:
                    current_clean = 0
                # Documented (charge + deed)
                has_charge = bool(seg.get("charge") or seg.get("intent"))
                has_deed = bool(seg.get("deed") or seg.get("retro"))
                if has_charge and has_deed:
                    today_documented += 1
                # Break taken after this work segment?
                today_break_opportunities += 1
                if i + 1 < len(segs) and segs[i + 1]["type"] != "work":
                    today_breaks_taken += 1

    today_clean_streak = best_clean_streak

    # ── Frog quests completed today ──────────────────────────────────────
    frog_quests_done = []
    non_frog_quests_done_before_first_frog = 0
    first_frog_time = None
    all_quests_done_today = []

    for q in quests:
        if q["status"] == "done" and _to_local_date(q.get("completed_at", "")) == today_str:
            all_quests_done_today.append(q)
            if q.get("frog"):
                frog_quests_done.append(q)
                try:
                    ft = datetime.fromisoformat(q["completed_at"])
                    if first_frog_time is None or ft < first_frog_time:
                        first_frog_time = ft
                except Exception:
                    pass

    # Check if frog was eaten first (no non-frog quests completed before it)
    frog_eaten_first = False
    if frog_quests_done and first_frog_time is not None:
        frog_eaten_first = all(
            datetime.fromisoformat(q["completed_at"]) >= first_frog_time
            for q in all_quests_done_today
            if not q.get("frog") and q.get("completed_at")
        )

    # Check if frog was eaten before noon
    frog_before_noon = False
    if first_frog_time is not None:
        local_time = first_frog_time.astimezone(USER_TZ)
        frog_before_noon = local_time.hour < 12

    quests_done_today = len(all_quests_done_today)
    frogs_eaten = len(frog_quests_done)

    # ── Compute each trophy ──────────────────────────────────────────────
    results = []

    def _tier(value: float, bronze: float, silver: float, gold: float) -> tuple[str, float, float]:
        """Returns (tier, progress, target_for_next)."""
        if value >= gold:
            return "gold", value, gold
        elif value >= silver:
            return "silver", value, gold
        elif value >= bronze:
            return "bronze", value, silver
        else:
            return "locked", value, bronze

    # 1. Frog Slayer
    if frog_eaten_first and frogs_eaten > 0:
        fs_tier = "gold"
    elif frog_before_noon and frogs_eaten > 0:
        fs_tier = "silver"
    elif frogs_eaten > 0:
        fs_tier = "bronze"
    else:
        fs_tier = "locked"

    fs_progress_label = ""
    if fs_tier == "gold":
        fs_progress_label = "eaten 1st!"
    elif fs_tier == "silver":
        fs_progress_label = "before noon"
    elif fs_tier == "bronze":
        fs_progress_label = "frog eaten"
    else:
        fs_progress_label = "no frog eaten"

    results.append({
        "id": "frog_slayer",
        "tier": fs_tier,
        "progress": 1 if frogs_eaten > 0 else 0,
        "target": 1,
        "progress_label": fs_progress_label,
    })

    # 2. Swamp Clearer
    sc_tier, sc_prog, sc_target = _tier(frogs_eaten, 1, 2, 4)
    results.append({
        "id": "swamp_clearer",
        "tier": sc_tier,
        "progress": frogs_eaten,
        "target": sc_target,
        "progress_label": f"{frogs_eaten} frog{'s' if frogs_eaten != 1 else ''}",
    })

    # 3. Forge Master
    fm_tier, fm_prog, fm_target = _tier(today_pomos, 2, 6, 10)
    results.append({
        "id": "forge_master",
        "tier": fm_tier,
        "progress": today_pomos,
        "target": fm_target,
        "progress_label": f"{today_pomos}/10 pomos",
    })

    # 4. Untouchable
    ut_tier, ut_prog, ut_target = _tier(today_clean_streak, 2, 4, 7)
    results.append({
        "id": "untouchable",
        "tier": ut_tier,
        "progress": today_clean_streak,
        "target": ut_target,
        "progress_label": f"{today_clean_streak}/7 streak",
    })

    # 5. Quest Closer
    qc_tier, qc_prog, qc_target = _tier(quests_done_today, 3, 5, 8)
    results.append({
        "id": "quest_closer",
        "tier": qc_tier,
        "progress": quests_done_today,
        "target": qc_target,
        "progress_label": f"{quests_done_today}/8 quests",
    })

    # 6. Scribe — gold = every pomo documented
    if today_pomos > 0 and today_documented >= today_pomos:
        scr_tier = "gold"
    elif today_documented >= 3:
        scr_tier = "silver"
    elif today_documented >= 1:
        scr_tier = "bronze"
    else:
        scr_tier = "locked"
    scr_target = max(today_pomos, 3) if scr_tier != "gold" else today_pomos
    results.append({
        "id": "scribe",
        "tier": scr_tier,
        "progress": today_documented,
        "target": scr_target if scr_target > 0 else 1,
        "progress_label": f"{today_documented}/{today_pomos or '?'} logged",
    })

    # 7. Ironclad — gold = every pomo followed by break
    if today_break_opportunities > 0 and today_breaks_taken >= today_break_opportunities:
        ic_tier = "gold"
    elif today_breaks_taken >= 3:
        ic_tier = "silver"
    elif today_breaks_taken >= 1:
        ic_tier = "bronze"
    else:
        ic_tier = "locked"
    ic_target = max(today_break_opportunities, 3) if ic_tier != "gold" else today_break_opportunities
    results.append({
        "id": "ironclad",
        "tier": ic_tier,
        "progress": today_breaks_taken,
        "target": ic_target if ic_target > 0 else 1,
        "progress_label": f"{today_breaks_taken}/{today_break_opportunities or '?'} breaks",
    })

    # ── Merge with definitions and update PRs ────────────────────────────
    pr_values = {
        "frog_slayer": first_frog_time.astimezone(USER_TZ).strftime("%H:%M") if first_frog_time else None,
        "swamp_clearer": frogs_eaten,
        "forge_master": today_pomos,
        "untouchable": today_clean_streak,
        "quest_closer": quests_done_today,
        "scribe": today_documented,
        "ironclad": (round(today_breaks_taken / today_break_opportunities * 100)
                     if today_break_opportunities > 0 else 0),
    }

    pr_display_values = {
        "frog_slayer": first_frog_time.astimezone(USER_TZ).strftime("%H:%M") if first_frog_time else None,
        "swamp_clearer": f"{frogs_eaten} frogs" if frogs_eaten else None,
        "forge_master": f"{today_pomos} pomos" if today_pomos else None,
        "untouchable": f"{today_clean_streak} consecutive" if today_clean_streak else None,
        "quest_closer": f"{quests_done_today} quests" if quests_done_today else None,
        "scribe": f"{today_documented} documented" if today_documented else None,
        "ironclad": f"{pr_values['ironclad']}% recovery" if today_break_opportunities > 0 else None,
    }

    # Update PRs (numeric comparison, higher is better; frog_slayer uses earliest time)
    updated = False
    for trophy_id, val in pr_values.items():
        if val is None or val == 0:
            continue
        existing = prs.get(trophy_id)

        is_new_pr = False
        if existing is None:
            is_new_pr = True
        elif trophy_id == "frog_slayer":
            # Earlier time is better
            is_new_pr = val < existing.get("best", "99:99")
        else:
            is_new_pr = val > existing.get("best", 0)

        if is_new_pr:
            prs[trophy_id] = {
                "best": val,
                "date": today_str,
                "detail": pr_display_values[trophy_id],
            }
            updated = True

    if updated:
        _save_prs(prs)

    # ── Build final output ───────────────────────────────────────────────
    def_map = {d["id"]: d for d in TROPHY_DEFS}
    trophies = []
    summary = {"gold": 0, "silver": 0, "bronze": 0, "locked": 0}

    for r in results:
        defn = def_map[r["id"]]
        tier = r["tier"]
        summary[tier] += 1

        pr_data = prs.get(r["id"])
        if pr_data:
            pr_str = f"{pr_data['detail']} · {pr_data['date'][5:]}"
        else:
            pr_str = "never earned"

        trophies.append({
            **defn,
            "tier": tier,
            "progress": r["progress"],
            "target": r["target"],
            "progress_label": r["progress_label"],
            "pr": pr_str,
        })

    # Sort: gold first, then silver, bronze, locked
    tier_order = {"gold": 0, "silver": 1, "bronze": 2, "locked": 3}
    trophies.sort(key=lambda t: tier_order.get(t["tier"], 4))

    # Best day ever (count of non-locked trophies)
    today_earned = summary["gold"] + summary["silver"] + summary["bronze"]
    best_day = prs.get("_best_day", {"count": 0, "date": ""})
    if today_earned > best_day["count"]:
        best_day = {"count": today_earned, "date": today_str}
        prs["_best_day"] = best_day
        _save_prs(prs)

    return {
        "trophies": trophies,
        "summary": summary,
        "best_day": best_day,
    }
