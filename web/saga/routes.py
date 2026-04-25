"""Saga emotional logging routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.saga import emotion_catalog, grouped_events, saga_metrics, unified_events
from core.storage.saga_backend import SqliteSagaRepo
from core.utils import today_local

router = APIRouter(prefix="/saga")


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _entry_context(entries: list[dict]) -> dict:
    return {"entries": entries, "emotion_catalog": emotion_catalog()}


async def _recent_response(request: Request, repo: SqliteSagaRepo) -> HTMLResponse:
    return _render(request, "saga_recent_entries.html", _entry_context(await repo.list_recent()))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def saga_index(request: Request):
    repo = SqliteSagaRepo(request.app.state.db)
    today = today_local().isoformat()
    events = await unified_events(request.app.state.db, today)
    return _render(request, "saga_index.html", {
        "active_tab": "today",
        "today": today,
        "today_label": date.fromisoformat(today).strftime("%b %d"),
        "emotion_catalog": emotion_catalog(),
        "recent_entries": await repo.list_recent(),
        "event_groups": grouped_events(events),
        "metrics": await saga_metrics(request.app.state.db),
    })


@router.get("/today", response_class=HTMLResponse)
async def saga_today_redirect():
    return RedirectResponse("/saga", status_code=303)


@router.get("/timeline", response_class=HTMLResponse)
async def saga_timeline(request: Request, local_date: str | None = None):
    day = local_date or today_local().isoformat()
    events = await unified_events(request.app.state.db, day)
    return _render(request, "saga_timeline.html", {
        "today": day,
        "today_label": date.fromisoformat(day).strftime("%b %d"),
        "event_groups": grouped_events(events),
    })


@router.get("/metrics", response_class=HTMLResponse)
async def saga_metrics_panel(request: Request):
    return _render(request, "saga_metrics.html", {
        "metrics": await saga_metrics(request.app.state.db),
    })


@router.post("/entries", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    emotion_family: str = Form(...),
    emotion_label: str = Form(...),
    intensity: int = Form(...),
    note: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    try:
        await repo.create(emotion_family, emotion_label, intensity, note)
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)
    response = await _recent_response(request, repo)
    response.headers["HX-Trigger"] = "saga-changed"
    return response


@router.patch("/entries/{entry_id}", response_class=HTMLResponse)
async def update_entry(
    request: Request,
    entry_id: str,
    emotion_family: str = Form(...),
    emotion_label: str = Form(...),
    intensity: int = Form(...),
    note: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    updated = await repo.update(entry_id, emotion_family, emotion_label, intensity, note)
    if updated is None:
        return HTMLResponse("Entry not found.", status_code=404)
    response = await _recent_response(request, repo)
    response.headers["HX-Trigger"] = "saga-changed"
    return response


@router.delete("/entries/{entry_id}", response_class=HTMLResponse)
async def delete_entry(request: Request, entry_id: str):
    repo = SqliteSagaRepo(request.app.state.db)
    await repo.delete(entry_id)
    response = await _recent_response(request, repo)
    response.headers["HX-Trigger"] = "saga-changed"
    return response
