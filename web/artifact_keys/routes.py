"""Artifact key management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from web.deps import get_artifact_key_repo

router = APIRouter()


def _render(request, name, context):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


async def _panel_response(request, key_repo):
    keys = await key_repo.list_keys()
    return _render(request, "artifact_keys_panel.html", {"keys": keys})


@router.get("/artifact-keys", response_class=HTMLResponse)
async def list_artifact_keys(request: Request, key_repo=Depends(get_artifact_key_repo)):
    return await _panel_response(request, key_repo)


@router.post("/artifact-keys", response_class=HTMLResponse)
async def add_artifact_key(
    request: Request,
    name: str = Form(...),
    icon: str = Form(None),
    key_repo=Depends(get_artifact_key_repo),
):
    name = name.strip()
    if name:
        await key_repo.add_key(name, icon or None)
    return await _panel_response(request, key_repo)


@router.patch("/artifact-keys/{name}", response_class=HTMLResponse)
async def rename_artifact_key(
    request: Request,
    name: str,
    new_name: str = Form(...),
    key_repo=Depends(get_artifact_key_repo),
):
    new_name = new_name.strip()
    if new_name and new_name != name:
        await key_repo.rename_key(name, new_name)
    return await _panel_response(request, key_repo)


@router.delete("/artifact-keys/{name}", response_class=HTMLResponse)
async def delete_artifact_key(
    request: Request,
    name: str,
    key_repo=Depends(get_artifact_key_repo),
):
    await key_repo.delete_key(name)
    return await _panel_response(request, key_repo)
