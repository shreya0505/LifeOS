"""Productivity metrics computation.

Both compute_metrics (quest-based) and compute_pomo_metrics (pomo-based)
accept data as parameters — no internal I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from core import clock

from core.config import POMO_CONFIG, PRIORITY_NAMES
from core.utils import (
    parse_dt, fmt_compact, fmt_delta_duration, fmt_delta_count,
    delta_arrow, classify_delta, segment_duration, to_local_date,
    quest_age_bucket, quest_age_days,
)


def compute_metrics(quests: list[dict]) -> list[dict]:
    """Compute productivity improvement metrics from quest history."""
    now         = clock.utcnow()
    week_ago    = now - timedelta(days=7)
    two_wks_ago = now - timedelta(days=14)

    done_qs     = [q for q in quests if q["status"] == "done" and q.get("completed_at")]
    done_sorted = sorted(done_qs, key=lambda q: q["completed_at"])

    # ── 1. Weekly Velocity ────────────────────────────────────────────────────
    this_wk = sum(1 for q in done_qs if parse_dt(q["completed_at"]) >= week_ago)
    last_wk = sum(1 for q in done_qs
                  if two_wks_ago <= parse_dt(q["completed_at"]) < week_ago)
    vel_d   = this_wk - last_wk

    # ── 2. Avg Cycle Time (started → done), last 5 vs prev 5 ─────────────────
    def _avg_gap(qs, k0, k1):
        vals = [(parse_dt(q[k1]) - parse_dt(q[k0])).total_seconds()
                for q in qs if q.get(k0) and q.get(k1)]
        return sum(vals) / len(vals) if vals else None

    ct_cur  = _avg_gap(done_sorted[-5:],    "started_at", "completed_at")
    ct_prev = _avg_gap(done_sorted[-10:-5], "started_at", "completed_at")
    ct_d    = (ct_cur - ct_prev) if None not in (ct_cur, ct_prev) else None

    # ── 3. Pickup Speed (created → started), last 5 vs prev 5 ────────────────
    started = sorted((q for q in quests if q.get("started_at")),
                     key=lambda q: q["started_at"])
    ps_cur  = _avg_gap(started[-5:],    "created_at", "started_at")
    ps_prev = _avg_gap(started[-10:-5], "created_at", "started_at")
    ps_d    = (ps_cur - ps_prev) if None not in (ps_cur, ps_prev) else None

    # ── 4. Net Backlog Change this week vs last week ───────────────────────────
    new_this = sum(1 for q in quests if parse_dt(q["created_at"]) >= week_ago)
    new_last = sum(1 for q in quests
                   if two_wks_ago <= parse_dt(q["created_at"]) < week_ago)
    bl_cur  = new_this - this_wk
    bl_prev = new_last - last_wk
    bl_d    = bl_cur - bl_prev

    # ── 5. Completion Rate, last 10 created vs prev 10 ────────────────────────
    by_created = sorted(quests, key=lambda q: q["created_at"])

    def _rate(qs):
        return round(sum(1 for q in qs if q["status"] == "done") / len(qs) * 100) if qs else None

    cr_cur  = _rate(by_created[-10:])
    cr_prev = _rate(by_created[-20:-10])
    cr_d    = (cr_cur - cr_prev) if None not in (cr_cur, cr_prev) else None

    open_qs = [q for q in quests if q["status"] in ("log", "active", "blocked")]
    high_open = [q for q in open_qs if q.get("priority", 4) <= 1]
    stale_high = [
        q for q in high_open
        if quest_age_bucket(quest_age_days(q, now)) in ("stale", "ancient", "fossil")
    ]

    age_scores = {"fresh": 0, "aging": 1, "stale": 2, "ancient": 4, "fossil": 6}
    priority_scores = {0: 5, 1: 3, 2: 2, 3: 1, 4: 0}
    neglect = sum(
        priority_scores.get(q.get("priority", 4), 0)
        * age_scores.get(quest_age_bucket(quest_age_days(q, now)), 0)
        for q in open_qs
    )

    priority_this = sum(
        1 for q in done_qs
        if q.get("priority", 4) <= 1 and parse_dt(q["completed_at"]) >= week_ago
    )
    priority_last = sum(
        1 for q in done_qs
        if q.get("priority", 4) <= 1
        and two_wks_ago <= parse_dt(q["completed_at"]) < week_ago
    )
    priority_d = priority_this - priority_last

    def _age_at_completion(q: dict) -> str:
        completed = parse_dt(q.get("completed_at"))
        return quest_age_bucket(quest_age_days(q, completed)) if completed else "fresh"

    old_this = sum(
        1 for q in done_qs
        if _age_at_completion(q) in ("ancient", "fossil")
        and parse_dt(q["completed_at"]) >= week_ago
    )
    old_last = sum(
        1 for q in done_qs
        if _age_at_completion(q) in ("ancient", "fossil")
        and two_wks_ago <= parse_dt(q["completed_at"]) < week_ago
    )
    old_d = old_this - old_last

    return [
        {
            "icon": "⚔", "name": "Battle Tempo",
            "value": f"{this_wk} slain",
            "context": "quests conquered this week",
            "delta": fmt_delta_count(vel_d, "vs last week"),
            "arrow": delta_arrow(vel_d),
            "color": classify_delta(vel_d, "up"),
        },
        {
            "icon": "🗡", "name": "Blade Speed",
            "value": fmt_compact(ct_cur),
            "context": "draw → kill (last 5)",
            "delta": fmt_delta_duration(ct_d, "vs prev 5"),
            "arrow": delta_arrow(ct_d),
            "color": classify_delta(ct_d, "down"),
        },
        {
            "icon": "📯", "name": "Call to Arms",
            "value": fmt_compact(ps_cur),
            "context": "scroll → battle (last 5)",
            "delta": fmt_delta_duration(ps_d, "vs prev 5"),
            "arrow": delta_arrow(ps_d),
            "color": classify_delta(ps_d, "down"),
        },
        {
            "icon": "📜", "name": "Scroll Tide",
            "value": f"{bl_cur:+d} net",
            "context": "inscribed − conquered this week",
            "delta": fmt_delta_count(bl_d, "vs last week"),
            "arrow": delta_arrow(bl_d),
            "color": classify_delta(bl_d, "down"),
        },
        {
            "icon": "🏆", "name": "Victory Rate",
            "value": f"{cr_cur}%" if cr_cur is not None else "—",
            "context": "last 10 quests",
            "delta": fmt_delta_count(cr_d, "vs prev 10", unit="%") if cr_d is not None else "not enough data",
            "arrow": delta_arrow(cr_d),
            "color": classify_delta(cr_d, "up"),
        },
        {
            "icon": "🔥", "name": "Doomfire Pressure",
            "value": f"{len(high_open)} open",
            "context": "P0/P1 quests on the board",
            "delta": f"{len(stale_high)} stale+ high priority",
            "arrow": "▲" if stale_high else "→",
            "color": "bad" if stale_high else ("good" if high_open else "neutral"),
        },
        {
            "icon": "⌛", "name": "Neglect Index",
            "value": str(neglect),
            "context": "priority-weighted aging risk",
            "delta": "snapshot",
            "arrow": "→",
            "color": "bad" if neglect >= 20 else ("neutral" if neglect else "good"),
        },
        {
            "icon": "🎯", "name": "Priority Burn",
            "value": f"{priority_this} slain",
            "context": "P0/P1 conquered this week",
            "delta": fmt_delta_count(priority_d, "vs last week"),
            "arrow": delta_arrow(priority_d),
            "color": classify_delta(priority_d, "up"),
        },
        {
            "icon": "🕯", "name": "Old Debt Cleared",
            "value": f"{old_this} slain",
            "context": "ancient/fossil quests this week",
            "delta": fmt_delta_count(old_d, "vs last week"),
            "arrow": delta_arrow(old_d),
            "color": classify_delta(old_d, "up"),
        },
    ]


def compute_pomo_metrics(sessions: list[dict]) -> list[dict]:
    """Compute productivity metrics from pomodoro session history."""
    now         = clock.utcnow()
    week_ago    = now - timedelta(days=7)
    two_wks_ago = now - timedelta(days=14)

    # Collect all work segments across all sessions
    all_work_segs = []
    for s in sessions:
        for seg in s.get("segments", []):
            if seg["type"] == "work":
                all_work_segs.append(seg)

    # ── 1. Weekly Focus Time ──────────────────────────────────────────────────
    week_ago_str    = week_ago.date().isoformat()
    two_wks_ago_str = two_wks_ago.date().isoformat()

    this_wk_secs = sum(
        segment_duration(seg) for seg in all_work_segs
        if seg.get("completed") and to_local_date(seg.get("started_at", "")) >= week_ago_str
    )
    prev_wk_secs = sum(
        segment_duration(seg) for seg in all_work_segs
        if seg.get("completed")
        and two_wks_ago_str <= to_local_date(seg.get("started_at", "")) < week_ago_str
    )
    focus_d = this_wk_secs - prev_wk_secs

    # ── 2. Pomo Completion Rate: % of last 20 work segments completed ─────────
    last_20 = all_work_segs[-20:]
    prev_20 = all_work_segs[-40:-20]

    def _rate(segs):
        if not segs:
            return None
        return round(sum(1 for s in segs if s.get("completed")) / len(segs) * 100)

    cr_cur  = _rate(last_20)
    cr_prev = _rate(prev_20)
    cr_d    = (cr_cur - cr_prev) if None not in (cr_cur, cr_prev) else None

    # ── 3. Longest Focus Streak ───────────────────────────────────────────────
    streak = max_streak = 0
    for seg in all_work_segs:
        if seg.get("completed"):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # ── 4. Interruption Rate: avg interruptions per work segment ─────────────
    def _avg_interruptions(segs):
        if not segs:
            return None
        return sum(s.get("interruptions", 0) for s in segs) / len(segs)

    ir_cur  = _avg_interruptions(last_20)
    ir_prev = _avg_interruptions(prev_20)
    ir_d    = (ir_cur - ir_prev) if None not in (ir_cur, ir_prev) else None

    if ir_d is None:
        ir_delta = "not enough data"
    elif ir_d == 0:
        ir_delta = "no change"
    else:
        ir_delta = f"{ir_d:+.2f}/heat vs prev 20"

    # ── 5. Break Compliance ───────────────────────────────────────────────────
    done_sessions = [s for s in sessions if s.get("status") in ("completed", "stopped")]

    def _break_compliance(sess_list):
        scheduled = taken = 0
        for s in sess_list:
            segs = s.get("segments", [])
            for i, seg in enumerate(segs):
                if seg["type"] == "work" and seg.get("completed"):
                    scheduled += 1
                    if i + 1 < len(segs) and segs[i + 1]["type"] in ("short_break", "long_break"):
                        taken += 1
        return round(taken / scheduled * 100) if scheduled > 0 else None

    bc_cur  = _break_compliance(done_sessions[-10:])
    bc_prev = _break_compliance(done_sessions[-20:-10])
    bc_d    = (bc_cur - bc_prev) if None not in (bc_cur, bc_prev) else None

    # ── 7. Cycle Completion ───────────────────────────────────────────────────
    _laps = POMO_CONFIG.get("laps_before_long", 4)

    def _cycle_flags(sess_list):
        flags = []
        for s in sess_list:
            segs = s.get("segments", [])
            work_done = sum(1 for sg in segs if sg["type"] == "work" and sg.get("completed"))
            if work_done >= _laps:
                flags.append(any(sg["type"] == "long_break" and sg.get("completed") for sg in segs))
        return flags

    all_cycle_flags = _cycle_flags(done_sessions)
    cc_cur  = (round(sum(all_cycle_flags[-5:]) / len(all_cycle_flags[-5:]) * 100)
               if len(all_cycle_flags) >= 1 else None)
    cc_prev = (round(sum(all_cycle_flags[-10:-5]) / len(all_cycle_flags[-10:-5]) * 100)
               if len(all_cycle_flags[-10:-5]) >= 1 else None)
    cc_d    = (cc_cur - cc_prev) if None not in (cc_cur, cc_prev) else None

    # ── 8. Berserker Rate ────────────────────────────────────────────────────
    def _berserker_rate(segs):
        completed = [s for s in segs if s.get("completed")]
        if not completed:
            return None
        return round(sum(1 for s in completed if s.get("forge_type") == "berserker")
                     / len(completed) * 100)

    br_cur  = _berserker_rate(last_20)
    br_prev = _berserker_rate(prev_20)
    br_d    = (br_cur - br_prev) if None not in (br_cur, br_prev) else None

    return [
        {
            "icon": "🔥", "name": "Forge Hours",
            "value": fmt_compact(this_wk_secs) if this_wk_secs > 0 else "—",
            "context": "time at the anvil this week",
            "delta": fmt_delta_duration(focus_d, "vs last week"),
            "arrow": delta_arrow(focus_d),
            "color": classify_delta(focus_d, "up"),
        },
        {
            "icon": "🔨", "name": "Forge Yield",
            "value": f"{cr_cur}%" if cr_cur is not None else "—",
            "context": "last 20 heats",
            "delta": fmt_delta_count(cr_d, "vs prev 20", unit="%") if cr_d is not None else "not enough data",
            "arrow": delta_arrow(cr_d),
            "color": classify_delta(cr_d, "up"),
        },
        {
            "icon": "⛓", "name": "Flame Chain",
            "value": f"{max_streak} heats",
            "context": "longest unbroken streak",
            "delta": "all-time record",
            "arrow": "→",
            "color": "neutral",
        },
        {
            "icon": "👹", "name": "Ambush Rate",
            "value": f"{ir_cur:.2f}/heat" if ir_cur is not None else "—",
            "context": "last 20 heats",
            "delta": ir_delta,
            "arrow": delta_arrow(ir_d),
            "color": classify_delta(ir_d, "down"),
        },
        {
            "icon": "☕", "name": "Rest Discipline",
            "value": f"{bc_cur}%" if bc_cur is not None else "—",
            "context": "last 10 sessions",
            "delta": fmt_delta_count(bc_d, "vs prev 10", unit="%") if bc_d is not None else "not enough data",
            "arrow": delta_arrow(bc_d),
            "color": classify_delta(bc_d, "up"),
        },
        {
            "icon": "♻", "name": "Full Circuit",
            "value": f"{cc_cur}%" if cc_cur is not None else "—",
            "context": "last 5 full cycles",
            "delta": fmt_delta_count(cc_d, "vs prev 5", unit="%") if cc_d is not None else "not enough data",
            "arrow": delta_arrow(cc_d),
            "color": classify_delta(cc_d, "up"),
        },
        {
            "icon": "⚡", "name": "Berserker Fury",
            "value": f"{br_cur}%" if br_cur is not None else "—",
            "context": "last 20 heats",
            "delta": fmt_delta_count(br_d, "vs prev 20", unit="%") if br_d is not None else "not enough data",
            "arrow": delta_arrow(br_d),
            "color": classify_delta(br_d, "up"),
        },
    ]


# ── War Room ────────────────────────────────────────────────────────────────
# Consistent grains — all metrics of the same grain use the same N.
WEEK_N    = 6   # all week-grain charts
DAY_D     = 14  # all day-grain charts
SESSION_M = 10  # all session-grain charts

# Colour tokens (mirror tokens.css)
_C_GREEN  = "#163422"
_C_TERRA  = "#95482b"
_C_SAGE   = "#7a9e7e"
_C_AMBER  = "#d4943a"
_C_EMBER  = "#b5493a"
_C_MUTED  = "#74796c"
_C_GRID   = "rgba(194,200,192,0.3)"
_C_FILL_G = "rgba(22,52,34,0.08)"
_C_FILL_E = "rgba(181,73,58,0.08)"
_C_FILL_A = "rgba(212,148,58,0.10)"
_C_FILL_S = "rgba(122,158,126,0.10)"
_C_EMPTY  = "rgba(194,200,192,0.35)"


def _base_opts(index_axis: str | None = None, stacked: bool = False) -> dict:
    opts: dict = {
        "responsive": True,
        "maintainAspectRatio": False,
        "plugins": {
            "legend": {"display": stacked},
            "tooltip": {"enabled": True},
        },
        "scales": {
            "x": {
                "grid": {"color": _C_GRID},
                "ticks": {"color": _C_MUTED, "font": {"size": 11}},
                "border": {"display": False},
                "stacked": stacked,
            },
            "y": {
                "grid": {"color": _C_GRID},
                "ticks": {"color": _C_MUTED, "font": {"size": 11}},
                "border": {"display": False},
                "beginAtZero": True,
                "stacked": stacked,
            },
        },
    }
    if index_axis:
        opts["indexAxis"] = index_axis
    return opts


def _count_opts(index_axis: str | None = None, stacked: bool = False) -> dict:
    """Chart.js options for discrete counts: no fractional task ticks."""
    opts = _base_opts(index_axis=index_axis, stacked=stacked)
    value_axis = "x" if index_axis == "y" else "y"
    opts["scales"][value_axis]["ticks"]["stepSize"] = 1
    opts["scales"][value_axis]["ticks"]["precision"] = 0
    return opts


def _week_ranges(now: datetime, n: int) -> list[tuple[datetime, datetime]]:
    """Last n rolling 7-day windows, oldest first."""
    return [
        (now - timedelta(weeks=n - i), now - timedelta(weeks=n - i - 1))
        for i in range(n)
    ]


def _week_labels(n: int) -> list[str]:
    labels = []
    for i in range(n):
        ago = n - 1 - i
        if ago == 0:
            labels.append("This wk")
        elif ago == 1:
            labels.append("1w ago")
        else:
            labels.append(f"{ago}w ago")
    return labels


def _trend_line(values: list) -> list:
    """3-point centred moving average for trend overlay."""
    out = []
    for i in range(len(values)):
        window = [x for x in values[max(0, i - 1):i + 2] if x is not None]
        out.append(round(sum(window) / len(window), 2) if window else None)
    return out


def compute_war_room(quests: list[dict], sessions: list[dict]) -> dict:
    """Chart configs for the War Room section (below Hall of Valor)."""
    now      = clock.utcnow()
    wranges  = _week_ranges(now, WEEK_N)
    wlabels  = _week_labels(WEEK_N)

    day_dates  = [(now - timedelta(days=DAY_D - 1 - i)).date() for i in range(DAY_D)]
    day_labels = [d.strftime("%-d %b") for d in day_dates]

    done_qs = [q for q in quests if q["status"] == "done" and q.get("completed_at")]
    open_qs = [q for q in quests if q["status"] in ("log", "active", "blocked")]
    age_names = ["fresh", "aging", "stale", "ancient", "fossil"]
    age_labels = ["Fresh", "Aging", "Stale", "Ancient", "Fossil"]

    def _bucket_now(q: dict) -> str:
        return quest_age_bucket(quest_age_days(q, now))

    def _bucket_at_completion(q: dict) -> str:
        completed = parse_dt(q.get("completed_at"))
        return quest_age_bucket(quest_age_days(q, completed)) if completed else "fresh"

    age_scores = {"fresh": 0, "aging": 1, "stale": 2, "ancient": 4, "fossil": 6}
    priority_scores = {0: 5, 1: 3, 2: 2, 3: 1, 4: 0}
    neglect = sum(
        priority_scores.get(q.get("priority", 4), 0)
        * age_scores.get(_bucket_now(q), 0)
        for q in open_qs
    )

    # ── Quest Chart 1: Priority Loadout (snapshot) ───────────────────────────
    priority_counts = [
        sum(1 for q in open_qs if q.get("priority", 4) == p)
        for p in range(5)
    ]
    qc1 = {
        "type": "bar",
        "data": {
            "labels": [f"P{p} {PRIORITY_NAMES.get(p, '')}" for p in range(5)],
            "datasets": [{
                "label": "Open quests",
                "data": priority_counts,
                "backgroundColor": [_C_EMBER, _C_TERRA, _C_AMBER, _C_SAGE, _C_EMPTY],
                "borderRadius": 4,
            }],
        },
        "options": _count_opts(),
    }

    # ── Quest Chart 2: High-Priority Pressure (snapshot by age) ──────────────
    qc2 = {
        "type": "bar",
        "data": {
            "labels": age_labels,
            "datasets": [
                {
                    "label": "P0",
                    "data": [
                        sum(1 for q in open_qs if q.get("priority", 4) == 0 and _bucket_now(q) == age)
                        for age in age_names
                    ],
                    "backgroundColor": _C_EMBER,
                    "borderRadius": 4,
                },
                {
                    "label": "P1",
                    "data": [
                        sum(1 for q in open_qs if q.get("priority", 4) == 1 and _bucket_now(q) == age)
                        for age in age_names
                    ],
                    "backgroundColor": _C_TERRA,
                    "borderRadius": 4,
                },
            ],
        },
        "options": _count_opts(stacked=True),
    }

    # ── Quest Chart 3: Priority Burn Rate (added vs completed by week) ───────
    priority_groups = [
        ("P0", lambda q: q.get("priority", 4) == 0, "rgba(181,73,58,0.35)", _C_EMBER),
        ("P1", lambda q: q.get("priority", 4) == 1, "rgba(149,72,43,0.35)", _C_TERRA),
        ("P2", lambda q: q.get("priority", 4) == 2, "rgba(212,148,58,0.35)", _C_AMBER),
        ("P3-P4", lambda q: q.get("priority", 4) >= 3, "rgba(122,158,126,0.35)", _C_SAGE),
    ]
    qc3 = {
        "type": "bar",
        "data": {
            "labels": wlabels,
            "datasets": [
                dataset
                for label, matcher, added_color, completed_color in priority_groups
                for dataset in (
                    {
                        "label": f"{label} added",
                        "stack": "Added",
                        "data": [
                            sum(
                                1 for q in quests
                                if matcher(q) and ws <= parse_dt(q["created_at"]) < we
                            )
                            for ws, we in wranges
                        ],
                        "backgroundColor": added_color,
                        "borderRadius": 4,
                    },
                    {
                        "label": f"{label} completed",
                        "stack": "Completed",
                        "data": [
                            sum(
                                1 for q in done_qs
                                if matcher(q) and ws <= parse_dt(q["completed_at"]) < we
                            )
                            for ws, we in wranges
                        ],
                        "backgroundColor": completed_color,
                        "borderRadius": 4,
                    },
                )
            ],
        },
        "options": _count_opts(stacked=True),
    }

    # ── Quest Chart 4: Age Burn Rate (stacked by week) ───────────────────────
    qc4 = {
        "type": "bar",
        "data": {
            "labels": wlabels,
            "datasets": [
                {
                    "label": label,
                    "data": [
                        sum(
                            1 for q in done_qs
                            if _bucket_at_completion(q) == age
                            and ws <= parse_dt(q["completed_at"]) < we
                        )
                        for ws, we in wranges
                    ],
                    "backgroundColor": color,
                    "borderRadius": 4,
                }
                for age, label, color in zip(
                    age_names,
                    age_labels,
                    [_C_SAGE, _C_AMBER, _C_TERRA, _C_EMBER, "#7a1a12"],
                )
            ],
        },
        "options": _count_opts(stacked=True),
    }

    # ── Quest Chart 5: Neglect Index (priority weight × age weight) ──────────
    opts_qc5 = _count_opts(index_axis="y")
    opts_qc5["scales"]["x"]["suggestedMax"] = max(10, neglect)
    neglect_priority_groups = [
        ("P0 x5", 0, _C_EMBER),
        ("P1 x3", 1, _C_TERRA),
        ("P2 x2", 2, _C_AMBER),
        ("P3 x1", 3, _C_SAGE),
    ]
    neglect_age_names = ["aging", "stale", "ancient", "fossil"]
    neglect_age_labels = ["Aging x1", "Stale x2", "Ancient x4", "Fossil x6"]
    qc5 = {
        "type": "bar",
        "data": {
            "labels": neglect_age_labels,
            "datasets": [
                {
                    "label": label,
                    "data": [
                        sum(
                            priority_scores.get(priority, 0) * age_scores.get(age, 0)
                            for q in open_qs
                            if q.get("priority", 4) == priority and _bucket_now(q) == age
                        )
                        for age in neglect_age_names
                    ],
                    "backgroundColor": color,
                    "borderRadius": 4,
                }
                for label, priority, color in neglect_priority_groups
            ],
        },
        "options": opts_qc5,
    }

    # ── All completed work segments ───────────────────────────────────────────
    work_segs = [
        seg for s in sessions
        for seg in s.get("segments", [])
        if seg["type"] == "work"
    ]

    # ── Focus Chart 1: Daily Focus Time (bar, DAY_D days) ────────────────────
    daily_h = [
        round(sum(
            segment_duration(sg) for sg in work_segs
            if sg.get("completed")
            and to_local_date(sg.get("started_at", "")) == d.isoformat()
        ) / 3600, 2)
        for d in day_dates
    ]
    fc1 = {
        "type": "bar",
        "data": {
            "labels": day_labels,
            "datasets": [{
                "label": "Hours", "data": daily_h,
                "backgroundColor": _C_GREEN, "borderRadius": 4,
            }],
        },
        "options": _base_opts(),
    }

    # ── Focus Chart 2: Weekly Focus Trend (area line, WEEK_N weeks) ──────────
    weekly_h = []
    for ws, we in wranges:
        ws_d, we_d = ws.date().isoformat(), we.date().isoformat()
        secs = sum(
            segment_duration(sg) for sg in work_segs
            if sg.get("completed")
            and ws_d <= to_local_date(sg.get("started_at", "")) < we_d
        )
        weekly_h.append(round(secs / 3600, 2))

    fc2 = {
        "type": "line",
        "data": {
            "labels": wlabels,
            "datasets": [{
                "label": "Hours", "data": weekly_h,
                "borderColor": _C_GREEN, "backgroundColor": _C_FILL_G,
                "fill": True, "tension": 0.4,
                "pointRadius": 4, "pointBackgroundColor": _C_GREEN, "borderWidth": 2,
            }],
        },
        "options": _base_opts(),
    }

    # ── Session-grain (last SESSION_M done sessions) ──────────────────────────
    done_sess = [s for s in sessions if s.get("status") in ("completed", "stopped")]
    last_m = done_sess[-SESSION_M:]
    prev_m = done_sess[-(SESSION_M * 2):-SESSION_M]

    def _avg_p(sl: list) -> float:
        return round(sum(s.get("actual_pomos", 0) for s in sl) / len(sl), 1) if sl else 0.0

    # ── Focus Chart 3: Session Depth (horizontal bar, SESSION_M sessions) ────
    opts_fc3 = _base_opts(index_axis="y")
    opts_fc3["scales"]["x"]["ticks"]["stepSize"] = 1  # type: ignore[index]

    fc3 = {
        "type": "bar",
        "data": {
            "labels": [f"Prev {SESSION_M}", f"Last {SESSION_M}"],
            "datasets": [{
                "label": "Avg pomos",
                "data": [_avg_p(prev_m), _avg_p(last_m)],
                "backgroundColor": [_C_EMPTY, _C_GREEN],
                "borderRadius": 4,
            }],
        },
        "options": opts_fc3,
    }

    # ── Focus Chart 4: Pomo Completion Rate (half-doughnut gauge) ────────────
    last_m_work = [
        sg for s in last_m for sg in s.get("segments", []) if sg["type"] == "work"
    ]
    cr = (
        round(sum(1 for sg in last_m_work if sg.get("completed")) / len(last_m_work) * 100)
        if last_m_work else 0
    )
    fc4 = {
        "type": "doughnut",
        "data": {
            "labels": ["Completed", "Abandoned"],
            "datasets": [{
                "data": [cr, 100 - cr],
                "backgroundColor": [_C_SAGE, _C_EMPTY],
                "borderWidth": 0,
            }],
        },
        "options": {
            "rotation": -90,
            "circumference": 180,
            "cutout": "72%",
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": False},
                "tooltip": {"enabled": False},
            },
        },
        "_center": f"{cr}%",
    }

    # ── Focus Chart 5: Interruption Rate Trend (line, WEEK_N weeks) ──────────
    ir_weekly: list = []
    for ws, we in wranges:
        ws_d, we_d = ws.date().isoformat(), we.date().isoformat()
        had_sessions = any(
            ws_d <= to_local_date(s.get("started_at", "")) < we_d
            for s in sessions
        )
        segs = [
            sg for sg in work_segs
            if ws_d <= to_local_date(sg.get("started_at", "")) < we_d
        ]
        if had_sessions:
            ir_weekly.append(
                round(sum(sg.get("interruptions", 0) for sg in segs) / len(segs), 2)
                if segs else 0
            )
        else:
            ir_weekly.append(None)

    fc5 = {
        "type": "line",
        "data": {
            "labels": wlabels,
            "datasets": [{
                "label": "Avg interruptions", "data": ir_weekly,
                "borderColor": _C_EMBER, "backgroundColor": _C_FILL_E,
                "fill": True, "tension": 0.4,
                "pointRadius": 4, "pointBackgroundColor": _C_EMBER, "borderWidth": 2,
                "spanGaps": True,
            }],
        },
        "options": _base_opts(),
    }

    # ── Focus Chart 6: Berserker Rate Trend (line, WEEK_N weeks) ─────────────
    berserker_weekly: list = []
    for ws, we in wranges:
        ws_d, we_d = ws.date().isoformat(), we.date().isoformat()
        had_sessions = any(
            ws_d <= to_local_date(s.get("started_at", "")) < we_d
            for s in sessions
        )
        completed_segs = [
            sg for sg in work_segs
            if sg.get("completed")
            and ws_d <= to_local_date(sg.get("started_at", "")) < we_d
        ]
        if had_sessions:
            berserker_weekly.append(
                round(sum(1 for sg in completed_segs if sg.get("forge_type") == "berserker")
                      / len(completed_segs) * 100, 1)
                if completed_segs else 0
            )
        else:
            berserker_weekly.append(None)

    fc6 = {
        "type": "line",
        "data": {
            "labels": wlabels,
            "datasets": [{
                "label": "Berserker %", "data": berserker_weekly,
                "borderColor": _C_AMBER, "backgroundColor": _C_FILL_A,
                "fill": True, "tension": 0.4,
                "pointRadius": 4, "pointBackgroundColor": _C_AMBER, "borderWidth": 2,
                "spanGaps": True,
            }],
        },
        "options": _base_opts(),
    }

    # ── Focus Chart 7: Break Compliance Trend (line, WEEK_N weeks) ───────────
    break_compliance_weekly: list = []
    for ws, we in wranges:
        ws_d, we_d = ws.date().isoformat(), we.date().isoformat()
        week_sessions = [
            s for s in sessions
            if s.get("status") in ("completed", "stopped")
            and ws_d <= to_local_date(s.get("started_at", "")) < we_d
        ]
        scheduled = taken = 0
        for s in week_sessions:
            segs = s.get("segments", [])
            for i, seg in enumerate(segs):
                if seg["type"] == "work" and seg.get("completed"):
                    scheduled += 1
                    if i + 1 < len(segs) and segs[i + 1]["type"] in ("short_break", "long_break"):
                        taken += 1
        if week_sessions:
            break_compliance_weekly.append(round(taken / scheduled * 100) if scheduled else 0)
        else:
            break_compliance_weekly.append(None)

    fc7 = {
        "type": "line",
        "data": {
            "labels": wlabels,
            "datasets": [{
                "label": "Break compliance %", "data": break_compliance_weekly,
                "borderColor": _C_SAGE, "backgroundColor": _C_FILL_S,
                "fill": True, "tension": 0.4,
                "pointRadius": 4, "pointBackgroundColor": _C_SAGE, "borderWidth": 2,
                "spanGaps": True,
            }],
        },
        "options": _base_opts(),
    }

    return {
        "quest_charts": [
            {
                "id": "priority-loadout", "icon": "flame", "name": "Priority Loadout",
                "sub": "snapshot",
                "desc": "Open quests by priority.",
                "tip": "P0/P1 should stay small enough to act on.",
                "config": qc1,
            },
            {
                "id": "high-priority-pressure", "icon": "triangle-alert", "name": "High-Priority Pressure",
                "sub": "snapshot",
                "desc": "Open P0/P1 quests split by age.",
                "tip": "Stale high priority means the board is lying.",
                "config": qc2,
            },
            {
                "id": "priority-burn-rate", "icon": "target", "name": "Priority Burn Rate",
                "sub": f"{WEEK_N} weeks",
                "desc": "Added vs completed quests by priority group.",
                "tip": "Completed stack below added stack = backlog pressure.",
                "config": qc3,
            },
            {
                "id": "age-burn-rate", "icon": "hourglass", "name": "Age Burn Rate",
                "sub": f"{WEEK_N} weeks",
                "desc": "Completed quests by age at completion.",
                "tip": "Old debt cleared is real maintenance work.",
                "config": qc4,
            },
            {
                "id": "neglect-index", "icon": "shield", "name": "Neglect Index",
                "sub": f"score {neglect}",
                "desc": "Open quests: priority weight x age weight.",
                "tip": "P0=5, P1=3, P2=2, P3=1; aging=1, stale=2, ancient=4, fossil=6.",
                "config": qc5,
            },
        ],
        "focus_charts": [
            {
                "id": "daily-focus", "icon": "flame", "name": "Daily Focus",
                "sub": f"{DAY_D} days",
                "desc": "Deep-work hours per day.",
                "tip": "Consistency > volume.",
                "config": fc1,
            },
            {
                "id": "weekly-focus", "icon": "trending-up", "name": "Weekly Trend",
                "sub": f"{WEEK_N} weeks",
                "desc": "Total focus hours per week. Slope > absolute.",
                "tip": "Rising = compounding. Flat = plateau.",
                "config": fc2,
            },
            {
                "id": "session-depth", "icon": "hammer", "name": "Session Depth",
                "sub": f"{SESSION_M} sessions",
                "desc": f"Avg pomos: prev {SESSION_M} vs last {SESSION_M}.",
                "tip": "Deeper sessions = less ramp-up cost.",
                "config": fc3,
            },
            {
                "id": "completion-rate", "icon": "check-circle", "name": "Completion Rate",
                "sub": f"last {SESSION_M} sessions",
                "desc": "% of started pomos fully completed.",
                "tip": "Below 80% = too many interruptions.",
                "config": fc4, "gauge": True, "_center": f"{cr}%",
            },
            {
                "id": "interruption-rate", "icon": "triangle-alert", "name": "Interruptions",
                "sub": f"{WEEK_N} weeks",
                "desc": "Avg interruptions per work segment.",
                "tip": "Any value > 0 costs recovery time.",
                "config": fc5,
            },
            {
                "id": "berserker-rate", "icon": "zap", "name": "Berserker Rate",
                "sub": f"{WEEK_N} weeks",
                "desc": "% of pomos that pushed past the timer.",
                "tip": "10\u201330% healthy. Higher = timer too short.",
                "config": fc6,
            },
            {
                "id": "break-compliance", "icon": "moon", "name": "Break Compliance",
                "sub": f"{WEEK_N} weeks",
                "desc": "% of pomos followed by a break.",
                "tip": "90%+ sustains output across the day.",
                "config": fc7,
            },
        ],
    }
