"""Trophy panel routes — Hall of Valor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from core.trophy_compute import compute_trophies
from web.deps import get_quest_repo, get_pomo_repo, get_trophy_repo

router = APIRouter()


def _render(request: Request, name: str, context: dict):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)





@router.get("/trophies", response_class=HTMLResponse)
async def trophies(
    request: Request,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    trophy_repo=Depends(get_trophy_repo),
):
    sessions = await pomo_repo.load_all()
    quests = await quest_repo.load_all()
    prs = await trophy_repo.load_prs()
    old_prs = dict(prs)  # snapshot before compute

    result, updated_prs = compute_trophies(sessions, quests, prs)
    await trophy_repo.save_prs(updated_prs)

    # Detect newly earned/improved personal records
    new_records = any(
        updated_prs.get(k) != old_prs.get(k)
        for k in updated_prs
    )

    # Add tier icons for template
    for t in result["trophies"]:
        # Compute progress percentage for bar
        if t["target"] > 0:
            t["progress_pct"] = min(int(t["progress"] / t["target"] * 100), 100)
        else:
            t["progress_pct"] = 0

    response = _render(request, "trophies/panel.html", {
        "trophies": result["trophies"],
        "summary": result["summary"],
        "best_day": result["best_day"],
    })

    if new_records:
        response.headers["HX-Trigger"] = "trophy-earned"
    return response
