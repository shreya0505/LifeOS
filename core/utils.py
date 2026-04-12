"""Shared utility helpers for QuestLog.

Timezone conversion, duration formatting, and display helpers used by
both TUI and web frontends.
"""

from datetime import datetime, date, timezone, timedelta

from core.config import USER_TZ


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


def format_duration(seconds: float | int | None) -> str:
    """Format seconds with ⏱ prefix — scales from minutes to weeks."""
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    w = seconds // 604800
    d = (seconds % 604800) // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    if w > 0:
        parts = [f"{w}w"]
        if d:
            parts.append(f"{d}d")
        return f"⏱ {' '.join(parts)}"
    if d > 0:
        parts = [f"{d}d"]
        if h:
            parts.append(f"{h}h")
        return f"⏱ {' '.join(parts)}"
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
    w = s // 604800
    d = (s % 604800) // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    if w:
        return f"{w}w {d}d" if d else f"{w}w"
    if d:
        return f"{d}d {h}h" if h else f"{d}d"
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
