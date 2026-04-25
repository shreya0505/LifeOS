"""Trophy panel routes — Hall of Valor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from core.metrics import compute_war_room
from core.trophy_compute import compute_trophies
from web.deps import get_quest_repo, get_pomo_repo
from core.storage.sqlite_backend import SqliteTrophyPRRepo
from web.questlog_context import QuestlogContext, resolve_questlog_context

router = APIRouter()


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _compute(sessions, quests, prs):
    result, updated_prs = compute_trophies(sessions, quests, prs)
    for t in result["trophies"]:
        t["progress_pct"] = min(int(t["progress"] / t["target"] * 100), 100) if t["target"] > 0 else 0
    return result, updated_prs


@router.get("/trophies", response_class=HTMLResponse)
async def trophies(
    request: Request,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    trophy_repo = SqliteTrophyPRRepo(request.app.state.db, qctx.workspace_id)
    sessions = await pomo_repo.load_all(qctx.workspace_id)
    quests = await quest_repo.load_all(qctx.workspace_id)
    prs = await trophy_repo.load_prs()
    old_prs = dict(prs)

    result, updated_prs = _compute(sessions, quests, prs)
    await trophy_repo.save_prs(updated_prs)

    new_records = any(updated_prs.get(k) != old_prs.get(k) for k in updated_prs)

    war_room = compute_war_room(quests, sessions)

    response = _render(request, "trophies/panel.html", {
        "trophies": result["trophies"],
        "summary": result["summary"],
        "best_day": result["best_day"],
        "quest_charts": war_room["quest_charts"],
        "focus_charts": war_room["focus_charts"],
    })

    if new_records:
        response.headers["HX-Trigger"] = "trophy-earned"
    return response


@router.get("/trophies/strip", response_class=HTMLResponse)
async def trophies_strip(
    request: Request,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    trophy_repo = SqliteTrophyPRRepo(request.app.state.db, qctx.workspace_id)
    sessions = await pomo_repo.load_all(qctx.workspace_id)
    quests = await quest_repo.load_all(qctx.workspace_id)
    prs = await trophy_repo.load_prs()

    result, updated_prs = _compute(sessions, quests, prs)
    await trophy_repo.save_prs(updated_prs)

    return _render(request, "trophies/strip.html", {
        "trophies": result["trophies"],
    })
