"""Artifact key management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from core.storage.sqlite_backend import SqliteArtifactKeyRepo
from web.questlog_context import QuestlogContext, resolve_questlog_context

router = APIRouter()


def _render(request, name, context):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


async def _panel_response(request, key_repo):
    keys = await key_repo.list_keys()
    return _render(request, "artifact_keys_panel.html", {"keys": keys})


@router.get("/artifact-keys", response_class=HTMLResponse)
async def list_artifact_keys(request: Request, qctx: QuestlogContext = Depends(resolve_questlog_context)):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    return await _panel_response(request, key_repo)


@router.post("/artifact-keys", response_class=HTMLResponse)
async def add_artifact_key(
    request: Request,
    name: str = Form(...),
    icon: str = Form(None),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    name = name.strip()
    if name:
        await key_repo.add_key(name, icon or None)
    return await _panel_response(request, key_repo)


@router.patch("/artifact-keys/{name}", response_class=HTMLResponse)
async def rename_artifact_key(
    request: Request,
    name: str,
    new_name: str = Form(...),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    new_name = new_name.strip()
    if new_name and new_name != name:
        await key_repo.rename_key(name, new_name)
    return await _panel_response(request, key_repo)


@router.delete("/artifact-keys/{name}", response_class=HTMLResponse)
async def delete_artifact_key(
    request: Request,
    name: str,
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    await key_repo.delete_key(name)
    return await _panel_response(request, key_repo)
