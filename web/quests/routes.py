"""Quest CRUD routes — HTML fragments for HTMX."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from core.config import VALID_SOURCES
from core.utils import fantasy_date, format_duration, get_elapsed, today_local, to_local_date
from core.pomo_queries import get_all_pomo_counts_today
from web.deps import get_quest_repo, get_pomo_repo
from web.pomos.engine import get_engine as _get_pomo_engine

router = APIRouter()


# ── Column definitions ──────────────────────────────────────────────────
_COLUMNS = [
    {"status": "log",     "label": "Quest Board",  "icon": "scroll", "empty_text": "No quests inscribed yet."},
    {"status": "active",  "label": "In Battle",    "icon": "flame",  "empty_text": "No active quests."},
    {"status": "blocked", "label": "Blocked",       "icon": "shield", "empty_text": "Nothing blocked."},
    {"status": "done",    "label": "Conquered",     "icon": "check-circle", "empty_text": "No victories yet."},
]


def _active_pomo_quest_id() -> str | None:
    engine = _get_pomo_engine()
    if engine.is_active and engine.session:
        return engine.session.get("quest_id")
    return None


async def _build_board_context(quest_repo, pomo_repo) -> list[dict]:
    """Build column data with enriched quest cards."""
    quests = await quest_repo.load_all()
    sessions = await pomo_repo.load_all()
    pomo_counts = get_all_pomo_counts_today(sessions)

    today_str = today_local().isoformat()
    by_status: dict[str, list[dict]] = {c["status"]: [] for c in _COLUMNS}
    for q in (q for q in quests if q["status"] != "abandoned"):
        enriched = dict(q)
        elapsed = get_elapsed(q)
        enriched["elapsed"] = format_duration(elapsed).lstrip("⏱ ") if elapsed and elapsed > 0 else None
        enriched["pomo_count"] = pomo_counts.get(q["id"], 0) or None
        enriched["done_today"] = (
            q["status"] == "done" and to_local_date(q.get("completed_at", "")) == today_str
        )
        status = q["status"]
        if status in by_status:
            by_status[status].append(enriched)

    columns = []
    for col_def in _COLUMNS:
        columns.append({**col_def, "quests": by_status[col_def["status"]]})
    return columns


async def _quest_counts(quest_repo) -> dict:
    quests = [q for q in await quest_repo.load_all() if q["status"] != "abandoned"]
    total = len(quests)
    active = sum(1 for q in quests if q["status"] == "active")
    done = sum(1 for q in quests if q["status"] == "done")
    return {"total": total, "active": active, "done": done}


def _render(request, name, context):
    """Render a Jinja2 template with Starlette 1.0 API."""
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


# ── Full page ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request,
                quest_repo=Depends(get_quest_repo),
                pomo_repo=Depends(get_pomo_repo)):
    columns = await _build_board_context(quest_repo, pomo_repo)
    counts = await _quest_counts(quest_repo)
    sessions = await pomo_repo.load_all()
    pomo_count = sum(get_all_pomo_counts_today(sessions).values())
    return _render(request, "index.html", {
        "columns": columns,
        "fantasy_date": fantasy_date(),
        "quest_counts": counts,
        "pomo_count": pomo_count,
        "volume_number": today_local().isocalendar()[1],
        "active_pomo_quest_id": _active_pomo_quest_id(),
    })


# ── Quest board (HTMX partial) ──────────────────────────────────────────

@router.get("/quests", response_class=HTMLResponse)
async def quest_board(request: Request,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo)):
    columns = await _build_board_context(quest_repo, pomo_repo)
    return _render(request, "board.html", {"columns": columns, "active_pomo_quest_id": _active_pomo_quest_id()})


# ── Add quest ────────────────────────────────────────────────────────────

@router.post("/quests", response_class=HTMLResponse)
async def add_quest(request: Request,
                    title: str = Form(...),
                    quest_repo=Depends(get_quest_repo),
                    pomo_repo=Depends(get_pomo_repo)):
    title = title.strip()
    if title:
        await quest_repo.add(title)
    columns = await _build_board_context(quest_repo, pomo_repo)
    response = _render(request, "board.html", {"columns": columns, "active_pomo_quest_id": _active_pomo_quest_id()})
    if title:
        response.headers["HX-Trigger"] = "quest-added"
    return response


# ── Update status ────────────────────────────────────────────────────────

@router.patch("/quests/{quest_id}/status", response_class=HTMLResponse)
async def update_status(request: Request,
                        quest_id: str,
                        status: str = Form(...),
                        quest_repo=Depends(get_quest_repo),
                        pomo_repo=Depends(get_pomo_repo)):
    # Validate transition
    valid_sources = VALID_SOURCES.get(
        {"active": "start", "blocked": "block", "done": "done", "abandoned": "abandon"}.get(status, ""),
        set(),
    )
    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    transitioned = False
    if quest and quest["status"] in valid_sources:
        await quest_repo.update_status(quest_id, status)
        transitioned = True

    columns = await _build_board_context(quest_repo, pomo_repo)
    response = _render(request, "board.html", {"columns": columns, "active_pomo_quest_id": _active_pomo_quest_id()})

    # Fire celebration events via HX-Trigger
    if transitioned and status == "done":
        response.headers["HX-Trigger"] = "quest-done"
    return response


# ── Toggle frog ──────────────────────────────────────────────────────────

@router.patch("/quests/{quest_id}/frog", response_class=HTMLResponse)
async def toggle_frog(request: Request,
                      quest_id: str,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo)):
    await quest_repo.toggle_frog(quest_id)
    columns = await _build_board_context(quest_repo, pomo_repo)
    return _render(request, "board.html", {"columns": columns, "active_pomo_quest_id": _active_pomo_quest_id()})


# ── Abandon quest ────────────────────────────────────────────────────────

@router.post("/quests/{quest_id}/abandon", response_class=HTMLResponse)
async def abandon_quest(request: Request,
                        quest_id: str,
                        quest_repo=Depends(get_quest_repo),
                        pomo_repo=Depends(get_pomo_repo)):
    await quest_repo.abandon(quest_id)
    columns = await _build_board_context(quest_repo, pomo_repo)
    response = _render(request, "board.html", {"columns": columns, "active_pomo_quest_id": _active_pomo_quest_id()})
    response.headers["HX-Trigger"] = "quest-abandoned"
    return response


# ── Stats bar (HTMX polling) ────────────────────────────────────────────

@router.get("/stats", response_class=HTMLResponse)
async def stats_bar(request: Request,
                    quest_repo=Depends(get_quest_repo),
                    pomo_repo=Depends(get_pomo_repo)):
    counts = await _quest_counts(quest_repo)
    sessions = await pomo_repo.load_all()
    pomo_count = sum(get_all_pomo_counts_today(sessions).values())
    return _render(request, "stats_bar.html", {
        "quest_counts": counts,
        "pomo_count": pomo_count,
    })
