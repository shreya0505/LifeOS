"""Pomodoro routes — charge/timer/deed/break flow via HTMX."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from core.config import POMO_CONFIG, USER_TZ
from core.pomo_queries import (
    get_today_receipt,
    get_quest_pomo_total,
    get_quest_lap_history,
    get_quest_segment_journey,
)
from web.deps import get_quest_repo, get_pomo_repo
from web.pomos.engine import get_engine

router = APIRouter(prefix="/pomos")


def _render(request, name, context):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


# ── Start session ────────────────────────────────────────────────────────

@router.post("/start", response_class=HTMLResponse)
async def start_session(
    request: Request,
    quest_id: str = Form(...),
    pomo_repo=Depends(get_pomo_repo),
):
    engine = get_engine()

    # If engine already has an active session, return the current state
    if engine.is_active:
        return _render(request, "pomo/panel.html", _panel_context(engine))

    # Get quest info from async repo
    from web.deps import get_quest_repo as _get_quest_repo
    quest_repo = _get_quest_repo(request)
    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None or quest["status"] != "active":
        return HTMLResponse("<p>Quest must be active to start a pomo.</p>", status_code=400)

    # Get prior pomo count and lap history
    sessions = await pomo_repo.load_all()
    prior = get_quest_pomo_total(sessions, quest_id)
    lap_history = get_quest_lap_history(sessions, quest_id)

    engine.start_session(quest_id, quest["title"], prior_pomos=prior, lap_history=lap_history)

    return _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "charge",
        "quest_title": quest["title"],
    })


# ── Submit charge ────────────────────────────────────────────────────────

@router.post("/charge", response_class=HTMLResponse)
async def submit_charge(request: Request, charge: str = Form(...)):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("No active session.", status_code=400)

    engine.submit_charge(charge.strip())
    event = engine.start_segment("work")

    return _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "timer",
        "seg_type": "work",
        "duration": event.duration,
        "started_at": event.started_at,
        "lap": event.lap,
        "charge": engine.charge,
        "quest_title": engine.session["quest_title"],
        "journey": _journey(engine),
    })


# ── Submit deed ──────────────────────────────────────────────────────────

@router.post("/deed", response_class=HTMLResponse)
async def submit_deed(
    request: Request,
    deed: str = Form(...),
    forge_type: str = Form(""),
):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("No active session.", status_code=400)

    ft = forge_type.strip() or None
    event = engine.submit_deed(deed.strip(), forge_type=ft)

    response = _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "break_choice",
        "notification": event.notification,
        "actual_pomos": event.actual_pomos,
        "streak": event.streak,
        "quest_title": engine.session["quest_title"],
        "config": POMO_CONFIG,
    })

    # Fire celebration events
    if ft == "berserker":
        response.headers["HX-Trigger"] = "pomo-berserker"
    else:
        response.headers["HX-Trigger"] = "pomo-complete"
    return response


# ── Choose break ─────────────────────────────────────────────────────────

@router.post("/break", response_class=HTMLResponse)
async def choose_break(request: Request, choice: str = Form(...)):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("No active session.", status_code=400)

    event = engine.choose_break(choice)

    if event.action == "end_session":
        summary = engine.stop_session()
        return _render(request, "pomo/summary.html", {
            "quest_title": summary.quest_title,
            "actual_pomos": summary.actual_pomos,
        })

    if event.action == "skip_to_charge":
        return _render(request, "pomo/panel.html", {
            "engine": engine,
            "mode": "charge",
            "quest_title": engine.session["quest_title"],
        })

    # Start break timer
    seg_event = engine.start_segment(event.seg_type)
    return _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "timer",
        "seg_type": event.seg_type,
        "duration": seg_event.duration,
        "started_at": seg_event.started_at,
        "lap": seg_event.lap,
        "quest_title": engine.session["quest_title"],
        "journey": _journey(engine),
    })


# ── Interrupt ────────────────────────────────────────────────────────────

@router.post("/interrupt", response_class=HTMLResponse)
async def interrupt(request: Request, reason: str = Form("")):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("No active session.", status_code=400)

    engine.interrupt(reason.strip())

    response = _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "charge",
        "quest_title": engine.session["quest_title"],
        "interrupted": True,
    })
    response.headers["HX-Trigger"] = "pomo-interrupted"
    return response


# ── Complete early (Swiftblade) ──────────────────────────────────────────

@router.post("/complete-early", response_class=HTMLResponse)
async def complete_early(request: Request):
    engine = get_engine()
    if not engine.is_active or not engine.is_timing:
        return HTMLResponse("No active work segment.", status_code=400)

    event = engine.complete_early()

    if event.next_gate == "deed":
        return _render(request, "pomo/panel.html", {
            "engine": engine,
            "mode": "deed",
            "quest_title": engine.session["quest_title"],
            "early": True,
        })

    return _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "charge",
        "quest_title": engine.session["quest_title"],
    })


# ── Timer expired (called by SSE or client) ──────────────────────────────

@router.post("/timer-done", response_class=HTMLResponse)
async def timer_done(request: Request):
    engine = get_engine()
    if not engine.is_active or not engine.is_timing:
        return HTMLResponse("No active timer.", status_code=400)

    # Only complete if timer actually expired
    if engine.remaining() > 1:
        return HTMLResponse("Timer still running.", status_code=400)

    event = engine.end_segment(completed=True)

    if event.next_gate == "deed":
        return _render(request, "pomo/panel.html", {
            "engine": engine,
            "mode": "deed",
            "quest_title": engine.session["quest_title"],
        })

    # Break finished → back to charge
    return _render(request, "pomo/panel.html", {
        "engine": engine,
        "mode": "charge",
        "quest_title": engine.session["quest_title"],
    })


# ── Stop session ─────────────────────────────────────────────────────────

@router.post("/stop", response_class=HTMLResponse)
async def stop_session(request: Request):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("No active session.", status_code=400)

    # Abandon mid-segment if timing
    if engine.is_timing:
        engine.abandon_mid_segment()

    summary = engine.stop_session()
    response = _render(request, "pomo/summary.html", {
        "quest_title": summary.quest_title,
        "actual_pomos": summary.actual_pomos,
    })
    response.headers["HX-Trigger"] = "pomo-stopped"
    return response


# ── Status (for polling/checking) ────────────────────────────────────────

@router.get("/status", response_class=HTMLResponse)
async def pomo_status(request: Request):
    engine = get_engine()
    if not engine.is_active:
        return HTMLResponse("")

    remaining = engine.remaining()
    return HTMLResponse(
        f'<span class="stats-bar__item">'
        f'🍅 {engine.session["quest_title"]} — '
        f'{int(remaining // 60)}:{int(remaining % 60):02d}'
        f'</span>'
    )


# ── Receipt ──────────────────────────────────────────────────────────────

@router.get("/receipt", response_class=HTMLResponse)
async def receipt(request: Request, pomo_repo=Depends(get_pomo_repo)):
    sessions = await pomo_repo.load_all()
    entries = get_today_receipt(sessions)

    formatted = []
    for entry in entries:
        try:
            dt = datetime.fromisoformat(entry["started_at"])
            time_str = dt.astimezone(USER_TZ).strftime("%H:%M")
        except Exception:
            time_str = "??:??"
        formatted.append({**entry, "time_str": time_str})

    # Count real pomos (exclude hollows)
    hollow_count = sum(1 for e in entries if e.get("forge_type") == "hollow")
    berserker_count = sum(1 for e in entries if e.get("forge_type") == "berserker")
    real_pomos = len(entries) - hollow_count
    total_mins = real_pomos * POMO_CONFIG["work_secs"] // 60

    return _render(request, "pomo/receipt.html", {
        "entries": formatted,
        "real_pomos": real_pomos,
        "total_mins": total_mins,
        "berserker_count": berserker_count,
        "hollow_count": hollow_count,
    })


# ── Helpers ──────────────────────────────────────────────────────────────

def _panel_context(engine) -> dict:
    """Build context for the current engine state."""
    ctx = {
        "engine": engine,
        "quest_title": engine.session["quest_title"] if engine.session else "",
    }
    if engine.is_timing:
        ctx["mode"] = "timer"
        ctx["seg_type"] = engine.seg_type
        ctx["duration"] = engine.seg_duration()
        ctx["started_at"] = engine.seg_start.isoformat() if engine.seg_start else ""
        ctx["lap"] = engine.lap
        ctx["charge"] = engine.charge
        ctx["journey"] = _journey(engine)
    elif engine.deed_lap >= 0:
        ctx["mode"] = "deed"
    else:
        ctx["mode"] = "charge"
    return ctx


def _journey(engine) -> list[dict]:
    """Build journey dots for the progress display."""
    dots = []
    for i in range(max(8, engine.lap + 1)):
        status = engine.lap_history.get(i, "empty")
        if i == engine.lap and engine.is_timing and engine.seg_type == "work":
            status = "current"
        dots.append({"lap": i, "status": status})
    return dots
