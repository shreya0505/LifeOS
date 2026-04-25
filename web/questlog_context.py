"""QuestLog workspace scoping helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from core.storage.sqlite_backend import DEFAULT_WORKSPACE_ID, SqliteWorkspaceRepo

WORKSPACE_COOKIE = "questlog_workspace_id"


@dataclass(frozen=True)
class QuestlogContext:
    workspace_id: str
    workspace: dict
    workspaces: list[dict]


async def resolve_questlog_context(request: Request) -> QuestlogContext:
    repo = SqliteWorkspaceRepo(request.app.state.db)
    workspaces = await repo.list_workspaces()
    if not workspaces:
        workspace = await repo.create("Work", "folder", "blue")
        workspaces = [workspace]

    selected = request.cookies.get(WORKSPACE_COOKIE) or DEFAULT_WORKSPACE_ID
    workspace = next((w for w in workspaces if w["id"] == selected), None)
    if workspace is None:
        workspace = next((w for w in workspaces if w["id"] == DEFAULT_WORKSPACE_ID), workspaces[0])

    return QuestlogContext(
        workspace_id=workspace["id"],
        workspace=workspace,
        workspaces=workspaces,
    )
