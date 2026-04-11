"""Chronicle panel routes — heatmap + today's timeline."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from core.pomo_queries import get_today_timeline, get_berserker_stats
from core.utils import today_local, to_local_date, segment_duration, fmt_compact
from web.deps import get_pomo_repo

router = APIRouter()


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _build_heatmap(sessions: list[dict]) -> list[dict]:
    """Build heatmap cells for the current month as a Mon-Sun calendar grid."""
    today = today_local()
    # First and last day of current month
    first_of_month = today.replace(day=1)
    if today.month == 12:
        last_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    # Pad to full weeks (Mon=0 start)
    grid_start = first_of_month - timedelta(days=first_of_month.weekday())
    grid_end = last_of_month + timedelta(days=6 - last_of_month.weekday())

    # Count completed work pomos per day (excluding hollow)
    daily: dict[str, int] = defaultdict(int)
    for s in sessions:
        for seg in s.get("segments", []):
            if (
                seg["type"] == "work"
                and seg.get("completed")
                and seg.get("forge_type") != "hollow"
            ):
                d = to_local_date(seg.get("started_at", ""))
                if d:
                    daily[d] += 1

    cells = []
    current = grid_start
    today_str = today.isoformat()
    while current <= grid_end:
        d = current.isoformat()
        in_month = current.month == today.month and current.year == today.year
        is_future = current > today
        count = daily.get(d, 0)
        if not in_month or is_future:
            level = "outside"
        elif count == 0:
            level = "empty"
        elif count <= 2:
            level = "light"
        elif count <= 5:
            level = "medium"
        else:
            level = "heavy"
        cells.append({
            "date": d,
            "count": count,
            "level": level,
            "is_today": d == today_str,
            "in_month": in_month,
            "day_num": current.day,
        })
        current += timedelta(days=1)

    return cells


def _build_today_entries(sessions: list[dict]) -> list[dict]:
    """Build today's pomo entries for the timeline."""
    today_str = today_local().isoformat()
    entries = []
    for s in sessions:
        qt = s.get("quest_title", "?")
        segs = s.get("segments", [])
        for i, seg in enumerate(segs):
            if seg["type"] != "work":
                continue
            seg_date = to_local_date(seg.get("started_at", ""))
            if seg_date != today_str:
                continue
            charge = seg.get("charge") or seg.get("intent") or ""
            deed = seg.get("deed") or seg.get("retro") or ""
            forge_type = seg.get("forge_type")
            entries.append({
                "time": seg.get("started_at", "")[11:16],
                "quest": qt,
                "charge": charge,
                "deed": deed,
                "completed": seg.get("completed", False),
                "forge_type": forge_type,
                "interruption_reason": seg.get("interruption_reason") or "",
                "duration_secs": segment_duration(seg),
            })
    entries.sort(key=lambda e: e["time"], reverse=True)
    return entries


def _week_summary(sessions: list[dict]) -> dict:
    """Compute this-week summary stats."""
    today = today_local()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    total_pomos = 0
    total_secs = 0.0
    for s in sessions:
        for seg in s.get("segments", []):
            if (
                seg["type"] == "work"
                and seg.get("completed")
                and seg.get("forge_type") != "hollow"
                and to_local_date(seg.get("started_at", "")) >= week_start
            ):
                total_pomos += 1
                total_secs += segment_duration(seg)
    return {
        "pomos": total_pomos,
        "focus_time": fmt_compact(total_secs) if total_secs > 0 else "0m",
    }


@router.get("/chronicle", response_class=HTMLResponse)
async def chronicle(request: Request, pomo_repo=Depends(get_pomo_repo)):
    sessions = await pomo_repo.load_all()
    heatmap_cells = _build_heatmap(sessions)
    today_entries = _build_today_entries(sessions)
    week = _week_summary(sessions)

    today_pomos = sum(1 for e in today_entries if e["completed"] and e.get("forge_type") != "hollow")
    today_focus_secs = sum(e["duration_secs"] for e in today_entries if e["completed"])

    today = today_local()
    month_label = today.strftime("%B %Y")

    return _render(request, "chronicle/panel.html", {
        "heatmap_cells": heatmap_cells,
        "today_entries": today_entries,
        "today_pomos": today_pomos,
        "today_focus": fmt_compact(today_focus_secs) if today_focus_secs > 0 else "0m",
        "week_pomos": week["pomos"],
        "week_focus": week["focus_time"],
        "month_label": month_label,
    })
