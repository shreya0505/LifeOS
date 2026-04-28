"""Saga emotional logging routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.saga import render_markdown_note, saga_dashboard, timeline_days
from core.storage.saga_backend import SqliteSagaRepo, mood_catalog
from core.utils import today_local

router = APIRouter(prefix="/saga")


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _entry_context(entries: list[dict]) -> dict:
    return {"entries": _rendered_entries(entries), "mood_catalog": mood_catalog()}


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
        "mood_catalog": mood_catalog(),
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
async def saga_metrics_panel(request: Request, window: int = 7, grain: str | None = None):
    grain_windows = {"week": 7, "month": 35, "quarter": 90, "year": 365}
    selected_grain = None
    if grain:
        selected_grain = grain if grain in grain_windows else "week"
        window = grain_windows[selected_grain]
    if window not in {7, 35, 90, 365}:
        window = 7
    if selected_grain is None:
        selected_grain = {7: "week", 35: "month", 90: "quarter", 365: "year"}.get(window, "week")
    dashboard = await saga_dashboard(request.app.state.db, window)
    context = {
        "active_tab": "metrics",
        "dashboard": dashboard,
        "selected_window": window,
        "selected_grain": selected_grain,
    }
    if request.headers.get("HX-Request", "").lower() == "true":
        return _render(request, "saga_metrics.html", context)
    return _render(request, "saga_metrics_page.html", context)


@router.post("/entries", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    energy: int = Form(...),
    pleasantness: int = Form(...),
    mood_word: str = Form(...),
    note: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    try:
        await repo.create(
            energy,
            pleasantness,
            mood_word,
            note,
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
    energy: int = Form(...),
    pleasantness: int = Form(...),
    mood_word: str = Form(...),
    note: str = Form(""),
):
    repo = SqliteSagaRepo(request.app.state.db)
    updated = await repo.update(
        entry_id,
        energy,
        pleasantness,
        mood_word,
        note,
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
