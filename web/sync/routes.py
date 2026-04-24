"""R2 sync routes for the SQLite web app."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.sync.config import SyncConfig, SyncConfigError
from core.sync.service import SyncResult, SyncService
from core.sync.store import build_store

router = APIRouter(prefix="/sync")


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _config(request: Request) -> SyncConfig | None:
    return getattr(request.app.state, "sync_config", None)


def _config_error(request: Request) -> str:
    return getattr(request.app.state, "sync_config_error", "")


def _service(request: Request) -> SyncService:
    config = _config(request)
    if config is None:
        raise SyncConfigError(_config_error(request) or "Sync configuration unavailable.")
    if not config.enabled:
        raise SyncConfigError("Sync is disabled.")
    return SyncService(request.app.state.db, config, build_store(config))


async def _panel_context(request: Request, result: SyncResult | None = None) -> dict:
    config = _config(request)
    config_error = _config_error(request)
    if config is None:
        return {
            "enabled": False,
            "config_error": config_error,
            "status": None,
            "conflicts": [],
            "result": result,
        }
    if not config.enabled:
        return {
            "enabled": False,
            "config_error": "",
            "status": {"enabled": False, "device_name": config.device_name or "", "auto_enabled": False},
            "conflicts": [],
            "result": result,
        }
    try:
        service = _service(request)
        return {
            "enabled": True,
            "config_error": "",
            "status": {
                **await service.status(),
                "auto_enabled": config.auto_enabled,
                "interval_seconds": config.interval_seconds,
                "show_prompts": config.show_prompts,
            },
            "conflicts": await service.open_conflicts(),
            "result": result,
        }
    except Exception:
        return {
            "enabled": False,
            "config_error": "Sync is enabled but could not initialize.",
            "status": None,
            "conflicts": [],
            "result": result,
        }


@router.get("/panel", response_class=HTMLResponse)
async def panel(request: Request):
    return _render(request, "sync_panel.html", await _panel_context(request))


@router.get("/status")
async def status(request: Request):
    config = _config(request)
    if config is None:
        return JSONResponse(
            {"enabled": False, "error": _config_error(request) or "Sync configuration unavailable."},
            status_code=200,
        )
    if not config.enabled:
        return {"enabled": False}
    service = _service(request)
    return await service.status()


@router.post("/pull", response_class=HTMLResponse)
async def pull(request: Request):
    try:
        result = await _service(request).pull()
    except Exception:
        result = SyncResult("pull", "error", "Pull failed.")
    return _render(request, "sync_panel.html", await _panel_context(request, result))


@router.post("/push", response_class=HTMLResponse)
async def push(request: Request):
    try:
        result = await _service(request).push()
    except Exception:
        result = SyncResult("push", "error", "Push failed.")
    return _render(request, "sync_panel.html", await _panel_context(request, result))


@router.post("/run", response_class=HTMLResponse)
async def run(request: Request):
    try:
        result = await _service(request).run()
    except Exception:
        result = SyncResult("run", "error", "Sync failed.")
    return _render(request, "sync_panel.html", await _panel_context(request, result))


@router.post("/conflicts/{conflict_id}/resolve", response_class=HTMLResponse)
async def resolve_conflict(
    request: Request,
    conflict_id: str,
    resolution: str = Form(...),
):
    try:
        result = await _service(request).resolve_conflict(conflict_id, resolution)
    except Exception:
        result = SyncResult("resolve", "error", "Conflict resolution failed.")
    return _render(request, "sync_panel.html", await _panel_context(request, result))
