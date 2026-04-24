"""Trophy computation for the Hall of Valor.

13 trophies: 3 tiered + 10 flat unlocks.
All reset daily. Pure computation — no I/O.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from core.config import USER_TZ
from core.utils import quest_age_bucket, quest_age_days, today_local, to_local_date
from core.trophy_defs import TROPHY_DEFS


def compute_trophies(
    sessions: list[dict],
    quests: list[dict],
    prs: dict,
) -> tuple[dict, dict]:
    today_str = today_local().isoformat()
    quest_by_id = {q.get("id"): q for q in quests if q.get("id")}
    quests_by_title: dict[str, list[dict]] = defaultdict(list)
    for q in quests:
        quests_by_title[q.get("title", "")].append(q)

    # ── Scan today's segments ────────────────────────────────────────────
    today_pomos = 0
    any_berserker = False
    any_long_break = False
    all_clean = True          # ghost_mode: no interruptions on any non-hollow work seg
    first_pomo_time = None
    priority_pomos_today = 0
    pomos_per_quest: dict[str, int] = defaultdict(int)

    for s in sessions:
        quest_title = s.get("quest_title", "")
        quest = quest_by_id.get(s.get("quest_id"))
        if quest is None:
            matches = quests_by_title.get(quest_title, [])
            quest = matches[0] if len(matches) == 1 else None
        for seg in s.get("segments", []):
            seg_date = to_local_date(seg.get("started_at", ""))
            if seg_date != today_str:
                continue

            if seg["type"] == "work" and seg.get("completed"):
                if seg.get("forge_type") == "hollow":
                    continue  # hollow never count
                today_pomos += 1
                pomos_per_quest[quest_title] += 1

                if quest and quest.get("priority", 4) <= 1:
                    priority_pomos_today += 1

                if seg.get("forge_type") == "berserker":
                    any_berserker = True

                if seg.get("interruptions", 0) > 0:
                    all_clean = False

                try:
                    t = datetime.fromisoformat(seg["started_at"])
                    if first_pomo_time is None or t < first_pomo_time:
                        first_pomo_time = t
                except Exception:
                    pass

            if seg["type"] == "long_break" and seg.get("completed"):
                any_long_break = True

    ghost_mode_earned = today_pomos > 0 and all_clean
    deep_siege_earned = any(v >= 4 for v in pomos_per_quest.values())

    dawn_forge_earned = False
    if first_pomo_time is not None:
        local_t = first_pomo_time.astimezone(USER_TZ)
        dawn_forge_earned = local_t.hour < 9

    # ── Frog Slayer (tiered) ─────────────────────────────────────────────
    frog_quests_done = []
    first_frog_time = None
    all_quests_done_today = []

    for q in quests:
        if q["status"] == "done" and to_local_date(q.get("completed_at", "")) == today_str:
            all_quests_done_today.append(q)
            if q.get("frog"):
                frog_quests_done.append(q)
                try:
                    ft = datetime.fromisoformat(q["completed_at"])
                    if first_frog_time is None or ft < first_frog_time:
                        first_frog_time = ft
                except Exception:
                    pass

    frogs_eaten = len(frog_quests_done)
    p0_done_today = sum(1 for q in all_quests_done_today if q.get("priority", 4) == 0)
    old_done_today = [
        q for q in all_quests_done_today
        if quest_age_bucket(quest_age_days(q)) in ("ancient", "fossil")
    ]
    sorted_done_today = sorted(
        (q for q in all_quests_done_today if q.get("completed_at")),
        key=lambda q: q["completed_at"],
    )
    first_strike_earned = (
        bool(sorted_done_today)
        and sorted_done_today[0].get("priority", 4) <= 1
    )
    open_high_priority = [
        q for q in quests
        if q.get("status") in ("log", "active", "blocked") and q.get("priority", 4) <= 1
    ]
    triage_rite_earned = bool(open_high_priority) and all(
        quest_age_bucket(quest_age_days(q)) in ("fresh", "aging")
        for q in open_high_priority
    )
    ancient_bane_earned = bool(old_done_today)
    deep_priority_earned = priority_pomos_today >= 2
    frog_before_noon = False
    frog_eaten_first = False

    if first_frog_time is not None:
        local_frog = first_frog_time.astimezone(USER_TZ)
        frog_before_noon = local_frog.hour < 12
        frog_eaten_first = all(
            datetime.fromisoformat(q["completed_at"]) >= first_frog_time
            for q in all_quests_done_today
            if not q.get("frog") and q.get("completed_at")
        )

    # ── Zero Debt ────────────────────────────────────────────────────────
    quests_created_today = sum(
        1 for q in quests
        if to_local_date(q.get("created_at", "")) == today_str
    )
    quests_closed_today = len(all_quests_done_today)
    zero_debt_earned = quests_closed_today >= quests_created_today and quests_created_today > 0

    # ── Build results ────────────────────────────────────────────────────
    def _tier(value, bronze, silver, gold):
        if value >= gold:
            return "gold", value, gold
        elif value >= silver:
            return "silver", value, gold
        elif value >= bronze:
            return "bronze", value, silver
        return "locked", value, bronze

    results = []

    # 1. Forge Master (tiered)
    fm_tier, fm_prog, fm_target = _tier(today_pomos, 2, 6, 10)
    results.append({
        "id": "forge_master",
        "tier": fm_tier,
        "progress": today_pomos,
        "target": fm_target,
        "progress_label": f"{today_pomos}/10 pomos",
    })

    # 2. Frog Slayer (tiered)
    if frog_eaten_first and frogs_eaten > 0:
        fs_tier = "gold"
    elif frog_before_noon and frogs_eaten > 0:
        fs_tier = "silver"
    elif frogs_eaten > 0:
        fs_tier = "bronze"
    else:
        fs_tier = "locked"

    fs_labels = {"gold": "eaten first!", "silver": "before noon", "bronze": "frog eaten", "locked": "none eaten"}
    results.append({
        "id": "frog_slayer",
        "tier": fs_tier,
        "progress": 1 if frogs_eaten > 0 else 0,
        "target": 1,
        "progress_label": fs_labels[fs_tier],
    })

    # 3. Doomfire Slayer (tiered)
    ds_tier, ds_prog, ds_target = _tier(p0_done_today, 1, 2, 3)
    results.append({
        "id": "doomfire_slayer",
        "tier": ds_tier,
        "progress": ds_prog,
        "target": ds_target,
        "progress_label": f"{p0_done_today}/3 P0 quests",
    })

    # 4–13. Flat trophies
    flat_results = [
        ("dawn_forge",  dawn_forge_earned,   "before 9am" if dawn_forge_earned else "first pomo after 9am"),
        ("berserker",   any_berserker,        "flow state" if any_berserker else "no berserker yet"),
        ("ghost_mode",  ghost_mode_earned,    "no interruptions" if ghost_mode_earned else "interrupted today"),
        ("deep_siege",  deep_siege_earned,    "4+ on one quest" if deep_siege_earned else f"max {max(pomos_per_quest.values(), default=0)}/4 on one quest"),
        ("sabbath",     any_long_break,       "long break taken" if any_long_break else "no long break yet"),
        ("zero_debt",   zero_debt_earned,     f"{quests_closed_today} closed / {quests_created_today} opened" if quests_created_today > 0 else "no quests opened today"),
        ("ancient_bane", ancient_bane_earned,  f"{len(old_done_today)} old quest closed" if ancient_bane_earned else "no ancient/fossil closed"),
        ("first_strike", first_strike_earned,  "high priority first" if first_strike_earned else "first quest was lower priority"),
        ("triage_rite",  triage_rite_earned,   "high priority is fresh" if triage_rite_earned else "stale high priority remains"),
        ("deep_priority", deep_priority_earned, f"{priority_pomos_today}/2 priority pomos" if not deep_priority_earned else "2+ priority pomos"),
    ]

    for tid, earned, label in flat_results:
        results.append({
            "id": tid,
            "tier": "earned" if earned else "locked",
            "progress": 1 if earned else 0,
            "target": 1,
            "progress_label": label,
        })

    # ── Update PRs ───────────────────────────────────────────────────────
    pr_values = {
        "forge_master": today_pomos,
        "frog_slayer": first_frog_time.astimezone(USER_TZ).strftime("%H:%M") if first_frog_time else None,
        "doomfire_slayer": p0_done_today,
        "dawn_forge":  1 if dawn_forge_earned else 0,
        "berserker":   1 if any_berserker else 0,
        "ghost_mode":  1 if ghost_mode_earned else 0,
        "deep_siege":  1 if deep_siege_earned else 0,
        "sabbath":     1 if any_long_break else 0,
        "zero_debt":   1 if zero_debt_earned else 0,
        "ancient_bane": 1 if ancient_bane_earned else 0,
        "first_strike": 1 if first_strike_earned else 0,
        "triage_rite":  1 if triage_rite_earned else 0,
        "deep_priority": 1 if deep_priority_earned else 0,
    }

    pr_display = {
        "forge_master": f"{today_pomos} pomos" if today_pomos else None,
        "frog_slayer":  first_frog_time.astimezone(USER_TZ).strftime("%H:%M") if first_frog_time else None,
        "doomfire_slayer": f"{p0_done_today} P0 quests" if p0_done_today else None,
        "dawn_forge":   "before 9am" if dawn_forge_earned else None,
        "berserker":    "flow state" if any_berserker else None,
        "ghost_mode":   "zero interruptions" if ghost_mode_earned else None,
        "deep_siege":   "4+ on one quest" if deep_siege_earned else None,
        "sabbath":      "long break taken" if any_long_break else None,
        "zero_debt":    "zero debt day" if zero_debt_earned else None,
        "ancient_bane": f"{len(old_done_today)} old quest closed" if ancient_bane_earned else None,
        "first_strike": "high priority first" if first_strike_earned else None,
        "triage_rite":  "high priority fresh" if triage_rite_earned else None,
        "deep_priority": "2+ priority pomos" if deep_priority_earned else None,
    }

    for trophy_id, val in pr_values.items():
        if not val:
            continue
        existing = prs.get(trophy_id)
        is_new_pr = False
        if existing is None:
            is_new_pr = True
        elif trophy_id == "frog_slayer":
            is_new_pr = val < existing.get("best", "99:99")
        else:
            is_new_pr = val > existing.get("best", 0)

        if is_new_pr and pr_display[trophy_id]:
            prs[trophy_id] = {
                "best": val,
                "date": today_str,
                "detail": pr_display[trophy_id],
            }

    # ── Merge with defs ──────────────────────────────────────────────────
    def_map = {d["id"]: d for d in TROPHY_DEFS}
    trophies = []
    summary = {"gold": 0, "silver": 0, "bronze": 0, "earned": 0, "locked": 0}

    for r in results:
        defn = def_map[r["id"]]
        tier = r["tier"]
        summary[tier] = summary.get(tier, 0) + 1

        pr_data = prs.get(r["id"])
        pr_str = f"{pr_data['detail']} · {pr_data['date'][5:]}" if pr_data else "never earned"

        trophies.append({
            **defn,
            "tier": tier,
            "progress": r["progress"],
            "target": r["target"],
            "progress_label": r["progress_label"],
            "pr": pr_str,
        })

    # Sort: gold → silver → bronze → earned → locked
    tier_order = {"gold": 0, "silver": 1, "bronze": 2, "earned": 3, "locked": 4}
    trophies.sort(key=lambda t: tier_order.get(t["tier"], 5))

    today_earned = summary["gold"] + summary["silver"] + summary["bronze"] + summary["earned"]
    best_day = prs.get("_best_day", {"count": 0, "date": ""})
    if today_earned > best_day["count"]:
        best_day = {"count": today_earned, "date": today_str}
        prs["_best_day"] = best_day

    return {
        "trophies": trophies,
        "summary": summary,
        "best_day": best_day,
    }, prs
