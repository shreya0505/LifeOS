from datetime import datetime, date, timezone, timedelta

from config import USER_TZ, POMO_CONFIG


def today_local() -> date:
    """Return today's date in the user's timezone."""
    return datetime.now(USER_TZ).date()


def to_local_date(iso_str: str) -> str:
    """Convert a UTC ISO timestamp string to a local date string (YYYY-MM-DD)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(USER_TZ).date().isoformat()
    except Exception:
        return iso_str[:10]


def fantasy_date(d: date | None = None) -> str:
    d = d or datetime.now(USER_TZ).date()
    day    = d.day
    month  = d.strftime("%B")
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    roman  = _to_roman(d.year)
    return f"The {day}{suffix} of {month}  ·  Anno {roman} of the Realm"


def _to_roman(n: int) -> str:
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
            (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    r = ""
    for v, s in vals:
        while n >= v:
            r += s; n -= v
    return r


def parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


def get_elapsed(quest: dict) -> float | None:
    started = parse_dt(quest.get("started_at"))
    if started is None:
        return None
    completed = parse_dt(quest.get("completed_at"))
    end = completed if completed else datetime.now(timezone.utc)
    return (end - started).total_seconds()


# ── Shared formatting helpers ────────────────────────────────────────────────
# Used by compute_metrics, compute_pomo_metrics, and chronicle_panel.


def format_duration(seconds: float | int | None) -> str:
    """Format seconds with ⏱ prefix (for stats bars and quest display)."""
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0 and m > 0:
        return f"⏱ {h}h {m}m"
    elif h > 0:
        return f"⏱ {h}h"
    elif m > 0:
        return f"⏱ {m}m"
    return "⏱ <1m"


def fmt_compact(secs: float | None) -> str:
    """Compact duration — no prefix, handles None and negative."""
    if secs is None:
        return "—"
    s = int(abs(secs))
    h, m = s // 3600, (s % 3600) // 60
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    if m:
        return f"{m}m"
    return "<1m"


def segment_duration(seg: dict) -> float:
    """Elapsed seconds for a segment dict with started_at / ended_at keys."""
    try:
        s = datetime.fromisoformat(seg["started_at"])
        e = datetime.fromisoformat(seg["ended_at"])
        return max(0.0, (e - s).total_seconds())
    except Exception:
        return 0.0


def classify_delta(d: float | int | None, good: str) -> str:
    """Classify a numeric delta as 'good', 'bad', or 'neutral'.

    ``good`` is either ``'up'`` (positive deltas are good) or
    ``'down'`` (negative deltas are good).
    """
    if d is None or d == 0:
        return "neutral"
    return "good" if (good == "up") == (d > 0) else "bad"


def delta_arrow(d: float | int | None) -> str:
    """Return ▲ / ▼ / → for a numeric delta."""
    if d is None or d == 0:
        return "→"
    return "▲" if d > 0 else "▼"


def fmt_delta_duration(d: float | None, context: str) -> str:
    """Format a duration delta with trailing context text."""
    if d is None:
        return "not enough data"
    if d == 0:
        return "no change"
    sign = "+" if d > 0 else "-"
    return f"{sign}{fmt_compact(d)} {context}"


def fmt_delta_count(d: int | None, context: str, unit: str = "") -> str:
    """Format a count delta with trailing context text."""
    if d is None:
        return "not enough data"
    if d == 0:
        return "no change"
    return f"{d:+d}{unit} {context}"


# ── Metric computation ───────────────────────────────────────────────────────


def compute_metrics(quests: list[dict]) -> list[dict]:
    """Compute productivity improvement metrics from quest history."""
    now         = datetime.now(timezone.utc)
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

    return [
        {
            "icon": "🚀", "name": "Weekly Velocity",
            "value": f"{this_wk} done",
            "context": "this week",
            "delta": fmt_delta_count(vel_d, "vs last week"),
            "arrow": delta_arrow(vel_d),
            "color": classify_delta(vel_d, "up"),
        },
        {
            "icon": "⚡", "name": "Avg Cycle Time",
            "value": fmt_compact(ct_cur),
            "context": "start → done (last 5)",
            "delta": fmt_delta_duration(ct_d, "vs prev 5"),
            "arrow": delta_arrow(ct_d),
            "color": classify_delta(ct_d, "down"),
        },
        {
            "icon": "⏳", "name": "Pickup Speed",
            "value": fmt_compact(ps_cur),
            "context": "log → active (last 5)",
            "delta": fmt_delta_duration(ps_d, "vs prev 5"),
            "arrow": delta_arrow(ps_d),
            "color": classify_delta(ps_d, "down"),
        },
        {
            "icon": "📥", "name": "Backlog Change",
            "value": f"{bl_cur:+d} net",
            "context": "added − done this week",
            "delta": fmt_delta_count(bl_d, "vs last week"),
            "arrow": delta_arrow(bl_d),
            "color": classify_delta(bl_d, "down"),
        },
        {
            "icon": "📊", "name": "Completion Rate",
            "value": f"{cr_cur}%" if cr_cur is not None else "—",
            "context": "last 10 quests",
            "delta": fmt_delta_count(cr_d, "vs prev 10", unit="%") if cr_d is not None else "not enough data",
            "arrow": delta_arrow(cr_d),
            "color": classify_delta(cr_d, "up"),
        },
    ]


def compute_pomo_metrics(sessions: list[dict]) -> list[dict]:
    """Compute productivity metrics from pomodoro session history."""
    now         = datetime.now(timezone.utc)
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

    # ── 3. Plan Accuracy: % of last 10 sessions where actual <= target ────────
    def _plan_acc(sess_list):
        if not sess_list:
            return None
        return round(
            sum(1 for s in sess_list if s.get("actual_pomos", 0) <= s.get("target_pomos", 0))
            / len(sess_list) * 100
        )

    pa_cur  = _plan_acc(sessions[-10:])
    pa_prev = _plan_acc(sessions[-20:-10])
    pa_d    = (pa_cur - pa_prev) if None not in (pa_cur, pa_prev) else None

    # ── 4. Longest Focus Streak ───────────────────────────────────────────────
    streak = max_streak = 0
    for seg in all_work_segs:
        if seg.get("completed"):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # ── 5. Interruption Rate: avg interruptions per work segment ─────────────
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
        ir_delta = f"{ir_d:+.2f}/seg vs prev 20"

    # ── 6. Break Compliance ───────────────────────────────────────────────────
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
            "icon": "🍅", "name": "Weekly Focus Time",
            "value": fmt_compact(this_wk_secs) if this_wk_secs > 0 else "—",
            "context": "this week",
            "delta": fmt_delta_duration(focus_d, "vs last week"),
            "arrow": delta_arrow(focus_d),
            "color": classify_delta(focus_d, "up"),
        },
        {
            "icon": "✅", "name": "Pomo Completion Rate",
            "value": f"{cr_cur}%" if cr_cur is not None else "—",
            "context": "last 20 segments",
            "delta": fmt_delta_count(cr_d, "vs prev 20", unit="%") if cr_d is not None else "not enough data",
            "arrow": delta_arrow(cr_d),
            "color": classify_delta(cr_d, "up"),
        },
        {
            "icon": "🎯", "name": "Plan Accuracy",
            "value": f"{pa_cur}%" if pa_cur is not None else "—",
            "context": "last 10 sessions",
            "delta": fmt_delta_count(pa_d, "vs prev 10", unit="%") if pa_d is not None else "not enough data",
            "arrow": delta_arrow(pa_d),
            "color": classify_delta(pa_d, "up"),
        },
        {
            "icon": "🔥", "name": "Longest Focus Streak",
            "value": f"{max_streak} 🍅",
            "context": "all time best",
            "delta": "all time best",
            "arrow": "→",
            "color": "neutral",
        },
        {
            "icon": "⚠️", "name": "Interruption Rate",
            "value": f"{ir_cur:.2f}/seg" if ir_cur is not None else "—",
            "context": "last 20 segments",
            "delta": ir_delta,
            "arrow": delta_arrow(ir_d),
            "color": classify_delta(ir_d, "down"),
        },
        {
            "icon": "☕", "name": "Break Compliance",
            "value": f"{bc_cur}%" if bc_cur is not None else "—",
            "context": "last 10 sessions",
            "delta": fmt_delta_count(bc_d, "vs prev 10", unit="%") if bc_d is not None else "not enough data",
            "arrow": delta_arrow(bc_d),
            "color": classify_delta(bc_d, "up"),
        },
        {
            "icon": "🏖", "name": "Cycle Completion",
            "value": f"{cc_cur}%" if cc_cur is not None else "—",
            "context": "last 5 full cycles",
            "delta": fmt_delta_count(cc_d, "vs prev 5", unit="%") if cc_d is not None else "not enough data",
            "arrow": delta_arrow(cc_d),
            "color": classify_delta(cc_d, "up"),
        },
        {
            "icon": "⚡", "name": "Berserker Rate",
            "value": f"{br_cur}%" if br_cur is not None else "—",
            "context": "last 20 segments",
            "delta": fmt_delta_count(br_d, "vs prev 20", unit="%") if br_d is not None else "not enough data",
            "arrow": delta_arrow(br_d),
            "color": classify_delta(br_d, "up"),
        },
    ]
