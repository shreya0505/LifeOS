"""Saga emotional logging routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.saga import dyad_catalog, emotion_catalog, render_markdown_note, saga_dashboard, timeline_days
from core.storage.saga_backend import SqliteSagaRepo
from core.utils import today_local

router = APIRouter(prefix="/saga")


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _entry_context(entries: list[dict]) -> dict:
    return {"entries": _rendered_entries(entries), "emotion_catalog": emotion_catalog()}


def _rendered_entries(entries: list[dict]) -> list[dict]:
    return [{**entry, "note_html": render_markdown_note(entry.get("note"))} for entry in entries]


def _today_context(entries: list[dict]) -> dict:
    return {"entries": _rendered_entries(entries)}


async def _recent_response(request: Request, repo: SqliteSagaRepo) -> HTMLResponse:
    return _render(request, "saga_recent_entries.html", _entry_context(await repo.list_recent()))


async def _today_notes_response(request: Request, repo: SqliteSagaRepo) -> HTMLResponse:
    return _render(
        request,
        "saga_today_entries.html",
        _today_context(await repo.list_by_date(today_local().isoformat())),
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def saga_index(request: Request):
    repo = SqliteSagaRepo(request.app.state.db)
    today = today_local().isoformat()
    return _render(request, "saga_index.html", {
        "active_tab": "today",
        "today": today,
        "today_label": date.fromisoformat(today).strftime("%b %d"),
        "emotion_catalog": emotion_catalog(),
        "dyad_catalog": dyad_catalog(),
        "today_entries": _rendered_entries(await repo.list_by_date(today)),
    })


@router.get("/today", response_class=HTMLResponse)
async def saga_today_redirect():
    return RedirectResponse("/saga", status_code=303)


@router.get("/timeline", response_class=HTMLResponse)
async def saga_timeline(request: Request, page: int = 1):
    return _render(request, "saga_timeline.html", {
        "timeline": await timeline_days(request.app.state.db, page=page),
    })


@router.get("/metrics", response_class=HTMLResponse)
async def saga_metrics_panel(request: Request, window: int = 7):
    if window not in {7, 35, 90, 365}:
        window = 7
    dashboard = await saga_dashboard(request.app.state.db, window)
    context = {
        "active_tab": "metrics",
        "dashboard": dashboard,
        "selected_window": window,
    }
    if request.headers.get("HX-Request", "").lower() == "true":
        return _render(request, "saga_metrics.html", context)
    return _render(request, "saga_metrics_page.html", context)


@router.post("/entries", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    emotion_family: str = Form(...),
    emotion_label: str = Form(...),
    intensity: int = Form(...),
    note: str = Form(""),
    secondary_emotion_family: str = Form(""),
    secondary_emotion_label: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    try:
        await repo.create(
            emotion_family,
            emotion_label,
            intensity,
            note,
            secondary_emotion_family=secondary_emotion_family,
            secondary_emotion_label=secondary_emotion_label,
        )
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)
    response = await _today_notes_response(request, repo)
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
    secondary_emotion_family: str = Form(""),
    secondary_emotion_label: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    updated = await repo.update(
        entry_id,
        emotion_family,
        emotion_label,
        intensity,
        note,
        secondary_emotion_family=secondary_emotion_family,
        secondary_emotion_label=secondary_emotion_label,
    )
    if updated is None:
        return HTMLResponse("Entry not found.", status_code=404)
    response = await _today_notes_response(request, repo)
    response.headers["HX-Trigger"] = "saga-changed"
    return response


@router.delete("/entries/{entry_id}", response_class=HTMLResponse)
async def delete_entry(request: Request, entry_id: str):
    repo = SqliteSagaRepo(request.app.state.db)
    await repo.delete(entry_id)
    response = await _today_notes_response(request, repo)
    response.headers["HX-Trigger"] = "saga-changed"
    return response
