"""Dashboard route — metrics modal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from core.metrics import compute_metrics, compute_pomo_metrics
from web.deps import get_quest_repo, get_pomo_repo
from web.questlog_context import QuestlogContext, resolve_questlog_context

router = APIRouter()


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    quests = await quest_repo.load_all(qctx.workspace_id)
    sessions = await pomo_repo.load_all(qctx.workspace_id)
    quest_metrics = compute_metrics(quests)
    pomo_metrics = compute_pomo_metrics(sessions)

    return _render(request, "dashboard/modal.html", {
        "quest_metrics": quest_metrics,
        "pomo_metrics": pomo_metrics,
    })
