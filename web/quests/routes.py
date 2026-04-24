"""Quest CRUD routes — HTML fragments for HTMX."""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from core.config import VALID_SOURCES, PRIORITY_NAMES, PRIORITY_GLYPHS
from core.utils import (
    fantasy_date, format_duration, get_elapsed, today_local, to_local_date,
    quest_age_days, quest_age_bucket, label_hue, is_url,
)
from core.pomo_queries import get_all_pomo_counts_today
from web.deps import get_quest_repo, get_pomo_repo, get_artifact_key_repo
from web.pomos.engine import get_engine as _get_pomo_engine

router = APIRouter()


# ── Column definitions ──────────────────────────────────────────────────
_COLUMNS = [
    {"status": "log",     "label": "Quest Board",  "icon": "scroll", "empty_text": "No quests inscribed yet."},
    {"status": "active",  "label": "In Battle",    "icon": "flame",  "empty_text": "No active quests."},
    {"status": "blocked", "label": "Blocked",       "icon": "shield", "empty_text": "Nothing blocked."},
    {"status": "done",    "label": "Conquered",     "icon": "check-circle", "empty_text": "No victories yet."},
]

_SORT_MODES = {"priority", "age"}


def _active_pomo_quest_id() -> str | None:
    engine = _get_pomo_engine()
    if engine.is_active and engine.session:
        return engine.session.get("quest_id")
    return None


def _enrich_quest(q: dict, pomo_counts: dict, today_str: str) -> dict:
    enriched = dict(q)
    elapsed = get_elapsed(q)
    enriched["elapsed"] = format_duration(elapsed).lstrip("⏱ ") if elapsed and elapsed > 0 else None
    enriched["pomo_count"] = pomo_counts.get(q["id"], 0) or None
    enriched["done_today"] = (
        q["status"] == "done" and to_local_date(q.get("completed_at", "")) == today_str
    )
    days = quest_age_days(q)
    enriched["age_days"] = days
    enriched["age_bucket"] = quest_age_bucket(days)
    enriched["priority_name"] = PRIORITY_NAMES.get(q.get("priority", 4), "Whisper")
    enriched["priority_glyph"] = PRIORITY_GLYPHS.get(q.get("priority", 4), "·")
    # Annotate labels with hue for coloring
    enriched["labels_with_hue"] = [
        {"name": lbl, "hue": label_hue(lbl)} for lbl in q.get("labels", [])
    ]
    # Annotate artifacts — mark URL values
    enriched["artifacts_display"] = [
        {"key": k, "value": v, "is_url": is_url(v)}
        for k, v in (q.get("artifacts") or {}).items()
    ]
    return enriched


def _apply_filters(
    quests: list[dict],
    filter_priority: list[int] | None,
    filter_labels: list[str] | None,
    filter_project: str | None,
    filter_age: list[str] | None,
) -> list[dict]:
    result = []
    for q in quests:
        if filter_priority and q.get("priority", 4) not in filter_priority:
            continue
        if filter_labels and not set(filter_labels).issubset(set(q.get("labels", []))):
            continue
        if filter_project and q.get("project") != filter_project:
            continue
        if filter_age and q.get("age_bucket") not in filter_age:
            continue
        result.append(q)
    return result


def _sort_column_quests(quests: list[dict], sort_mode: str | None) -> list[dict]:
    if sort_mode == "age":
        return sorted(
            quests,
            key=lambda q: (
                not q.get("frog", False),
                -q.get("age_days", 0),
                q.get("priority", 4),
                q.get("created_at", ""),
            ),
        )
    if sort_mode == "priority":
        return sorted(
            quests,
            key=lambda q: (
                not q.get("frog", False),
                q.get("priority", 4),
                -q.get("age_days", 0),
                q.get("created_at", ""),
            ),
        )
    return quests


async def _build_board_context(
    quest_repo,
    pomo_repo,
    *,
    filter_priority: list[int] | None = None,
    filter_labels: list[str] | None = None,
    filter_project: str | None = None,
    filter_age: list[str] | None = None,
    sort_mode: str | None = None,
) -> tuple[list[dict], list[str], list[dict]]:
    """Build column data with enriched quest cards. Returns (columns, all_projects, all_labels_with_hue)."""
    quests = await quest_repo.load_all()
    sessions = await pomo_repo.load_all()
    pomo_counts = get_all_pomo_counts_today(sessions)

    today_str = today_local().isoformat()
    enriched_all = [
        _enrich_quest(q, pomo_counts, today_str)
        for q in quests if q["status"] != "abandoned"
    ]

    # Collect distinct projects and labels before filtering so dropdowns always show all options
    all_projects = sorted({q["project"] for q in enriched_all if q.get("project")})
    all_label_names = sorted({lbl for q in enriched_all for lbl in q.get("labels", [])})
    all_labels_with_hue = [{"name": lbl, "hue": label_hue(lbl)} for lbl in all_label_names]

    if any([filter_priority, filter_labels, filter_project, filter_age]):
        enriched_all = _apply_filters(enriched_all, filter_priority, filter_labels, filter_project, filter_age)

    by_status: dict[str, list[dict]] = {c["status"]: [] for c in _COLUMNS}
    for enriched in enriched_all:
        status = enriched["status"]
        if status in by_status:
            by_status[status].append(enriched)

    for status in ("log", "active", "blocked"):
        by_status[status] = _sort_column_quests(by_status[status], sort_mode)

    columns = [{**col_def, "quests": by_status[col_def["status"]]} for col_def in _COLUMNS]
    return columns, all_projects, all_labels_with_hue


def _parse_query_state(query: str) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(query, keep_blank_values=True).items()
        if values
    }


async def _parse_filter_params(request: Request) -> dict:
    params = dict(request.query_params)
    if request.method not in {"GET", "HEAD"}:
        try:
            form = await request.form()
        except Exception:
            form = None
        if form and form.get("filter_state"):
            params.update(_parse_query_state(str(form.get("filter_state"))))

    priority = None
    if "priority" in params:
        try:
            priority = [int(p) for p in params["priority"].split(",") if p.strip()]
        except ValueError:
            priority = None
    labels = None
    if "labels" in params:
        labels = [l.strip() for l in params["labels"].split(",") if l.strip()]
    project = params.get("project") or None
    age = None
    if "age" in params:
        age = [a.strip() for a in params["age"].split(",") if a.strip()]
    sort_mode = params.get("sort")
    if sort_mode not in _SORT_MODES:
        sort_mode = "priority"
    return {
        "filter_priority": priority,
        "filter_labels": labels,
        "filter_project": project,
        "filter_age": age,
        "sort_mode": sort_mode,
    }


async def _quest_counts(quest_repo) -> dict:
    quests = [q for q in await quest_repo.load_all() if q["status"] != "abandoned"]
    total = len(quests)
    active = sum(1 for q in quests if q["status"] == "active")
    done = sum(1 for q in quests if q["status"] == "done")
    return {"total": total, "active": active, "done": done}


async def _board_response(request, quest_repo, pomo_repo, filters: dict | None = None, key_repo=None):
    f = filters or {}
    columns, all_projects, all_labels_with_hue = await _build_board_context(quest_repo, pomo_repo, **f)
    artifact_keys = await key_repo.list_keys() if key_repo else []
    return _render(request, "board.html", {
        "columns": columns,
        "all_projects": all_projects,
        "all_labels_with_hue": all_labels_with_hue,
        "active_filters": f,
        "priority_names": PRIORITY_NAMES,
        "priority_glyphs": PRIORITY_GLYPHS,
        "artifact_keys": artifact_keys,
        "active_pomo_quest_id": _active_pomo_quest_id(),
        "request": request,
    })


def _render(request, name, context):
    """Render a Jinja2 template with Starlette 1.0 API."""
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


# ── Full page ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request,
                quest_repo=Depends(get_quest_repo),
                pomo_repo=Depends(get_pomo_repo),
                key_repo=Depends(get_artifact_key_repo)):
    f = await _parse_filter_params(request)
    columns, all_projects, all_labels_with_hue = await _build_board_context(quest_repo, pomo_repo, **f)
    counts = await _quest_counts(quest_repo)
    sessions = await pomo_repo.load_all()
    pomo_count = sum(get_all_pomo_counts_today(sessions).values())
    return _render(request, "index.html", {
        "columns": columns,
        "all_projects": all_projects,
        "all_labels_with_hue": all_labels_with_hue,
        "active_filters": f,
        "fantasy_date": fantasy_date(),
        "quest_counts": counts,
        "pomo_count": pomo_count,
        "volume_number": today_local().isocalendar()[1],
        "active_pomo_quest_id": _active_pomo_quest_id(),
        "priority_names": PRIORITY_NAMES,
        "priority_glyphs": PRIORITY_GLYPHS,
        "artifact_keys": await key_repo.list_keys(),
    })


# ── Quest board (HTMX partial) ──────────────────────────────────────────

@router.get("/quests", response_class=HTMLResponse)
async def quest_board(request: Request,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo),
                      key_repo=Depends(get_artifact_key_repo)):
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


# ── Add quest ────────────────────────────────────────────────────────────

@router.post("/quests", response_class=HTMLResponse)
async def add_quest(
    request: Request,
    title: str = Form(...),
    priority: int = Form(4),
    project: str = Form(""),
    labels: str = Form(""),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    title = title.strip()
    if title:
        label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else []
        form_data = await request.form()
        artifact_keys_raw = form_data.getlist("artifact_key[]")
        artifact_vals_raw = form_data.getlist("artifact_val[]")
        artifacts = {k: v for k, v in zip(artifact_keys_raw, artifact_vals_raw) if k.strip() and v.strip()}
        await quest_repo.add(
            title,
            priority=max(0, min(4, priority)),
            project=project.strip() or None,
            labels=label_list,
            artifacts=artifacts,
        )
    f = await _parse_filter_params(request)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)
    if title:
        response.headers["HX-Trigger"] = "quest-added"
    return response


# ── Update status ────────────────────────────────────────────────────────

@router.patch("/quests/{quest_id}/status", response_class=HTMLResponse)
async def update_status(request: Request,
                        quest_id: str,
                        status: str = Form(...),
                        quest_repo=Depends(get_quest_repo),
                        pomo_repo=Depends(get_pomo_repo),
                        key_repo=Depends(get_artifact_key_repo)):
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

    f = await _parse_filter_params(request)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)
    if transitioned and status == "done":
        response.headers["HX-Trigger"] = "quest-done"
    return response


# ── Toggle frog ──────────────────────────────────────────────────────────

@router.patch("/quests/{quest_id}/frog", response_class=HTMLResponse)
async def toggle_frog(request: Request,
                      quest_id: str,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo),
                      key_repo=Depends(get_artifact_key_repo)):
    await quest_repo.toggle_frog(quest_id)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


# ── Abandon quest ────────────────────────────────────────────────────────

@router.post("/quests/{quest_id}/abandon", response_class=HTMLResponse)
async def abandon_quest(request: Request,
                        quest_id: str,
                        quest_repo=Depends(get_quest_repo),
                        pomo_repo=Depends(get_pomo_repo),
                        key_repo=Depends(get_artifact_key_repo)):
    await quest_repo.abandon(quest_id)
    f = await _parse_filter_params(request)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)
    response.headers["HX-Trigger"] = "quest-abandoned"
    return response


# ── Update priority / project / labels / artifacts ───────────────────────

@router.patch("/quests/{quest_id}/priority", response_class=HTMLResponse)
async def update_priority(
    request: Request,
    quest_id: str,
    priority: int = Form(...),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    await quest_repo.update_priority(quest_id, max(0, min(4, priority)))
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


@router.patch("/quests/{quest_id}/project", response_class=HTMLResponse)
async def update_project(
    request: Request,
    quest_id: str,
    project: str = Form(""),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    await quest_repo.update_project(quest_id, project.strip() or None)
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


@router.put("/quests/{quest_id}/labels", response_class=HTMLResponse)
async def update_labels(
    request: Request,
    quest_id: str,
    labels: str = Form(""),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    await quest_repo.update_labels(quest_id, label_list)
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


@router.put("/quests/{quest_id}/artifacts", response_class=HTMLResponse)
async def update_artifacts(
    request: Request,
    quest_id: str,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    form_data = await request.form()
    artifact_keys_raw = form_data.getlist("artifact_key[]")
    artifact_vals_raw = form_data.getlist("artifact_val[]")
    artifacts = {k: v for k, v in zip(artifact_keys_raw, artifact_vals_raw) if k.strip() and v.strip()}
    await quest_repo.update_artifacts(quest_id, artifacts)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo)


async def _meta_strip_response(request, quest_id, quest_repo, key_repo):
    """Return just the meta strip partial (used by pomo screen edits)."""
    quests = await quest_repo.load_all()
    q = next((q for q in quests if q["id"] == quest_id), None)
    if q is None:
        return HTMLResponse("", status_code=404)
    today_str = today_local().isoformat()
    enriched = _enrich_quest(q, {}, today_str)
    artifact_keys = await key_repo.list_keys()
    return _render(request, "quest_meta_strip.html", {
        "quest": enriched,
        "artifact_keys": artifact_keys,
        "priority_names": PRIORITY_NAMES,
        "priority_glyphs": PRIORITY_GLYPHS,
    })


# ── Quest meta strip (used by pomo timer) ───────────────────────────────

@router.get("/quests/{quest_id}/meta-strip", response_class=HTMLResponse)
async def quest_meta_strip(
    request: Request,
    quest_id: str,
    quest_repo=Depends(get_quest_repo),
    key_repo=Depends(get_artifact_key_repo),
):
    quests = await quest_repo.load_all()
    q = next((q for q in quests if q["id"] == quest_id), None)
    if q is None:
        return HTMLResponse("", status_code=404)
    today_str = today_local().isoformat()
    enriched = _enrich_quest(q, {}, today_str)
    artifact_keys = await key_repo.list_keys()
    return _render(request, "quest_meta_strip.html", {
        "quest": enriched,
        "artifact_keys": artifact_keys,
        "priority_names": PRIORITY_NAMES,
        "priority_glyphs": PRIORITY_GLYPHS,
    })


# ── Checklist (partial, used from pomo charge/deed screens) ─────────────

def _render_checklist(request, quest_id: str, checklist: list[dict]):
    response = _render(request, "checklist_panel.html", {
        "quest_id": quest_id,
        "checklist": checklist,
    })
    # Never cache — state mutates via PATCH/POST/DELETE
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/quests/{quest_id}/checklist", response_class=HTMLResponse)
async def get_checklist(request: Request, quest_id: str, quest_repo=Depends(get_quest_repo)):
    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)
    return _render_checklist(request, quest_id, quest.get("checklist", []))


@router.post("/quests/{quest_id}/checklist", response_class=HTMLResponse)
async def add_checklist_item(
    request: Request,
    quest_id: str,
    text: str = Form(...),
    quest_repo=Depends(get_quest_repo),
):
    text = text.strip()
    if not text:
        quests = await quest_repo.load_all()
        quest = next((q for q in quests if q["id"] == quest_id), None)
        checklist = quest.get("checklist", []) if quest else []
        return _render_checklist(request, quest_id, checklist)

    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = list(quest.get("checklist", []))
    checklist.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False})
    await quest_repo.update_checklist(quest_id, checklist)
    return _render_checklist(request, quest_id, checklist)


@router.patch("/quests/{quest_id}/checklist/{item_id}/toggle", response_class=HTMLResponse)
async def toggle_checklist_item(
    request: Request,
    quest_id: str,
    item_id: str,
    quest_repo=Depends(get_quest_repo),
):
    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = list(quest.get("checklist", []))
    for item in checklist:
        if item["id"] == item_id:
            item["done"] = not item["done"]
            break
    await quest_repo.update_checklist(quest_id, checklist)
    return _render_checklist(request, quest_id, checklist)


@router.delete("/quests/{quest_id}/checklist/{item_id}", response_class=HTMLResponse)
async def delete_checklist_item(
    request: Request,
    quest_id: str,
    item_id: str,
    quest_repo=Depends(get_quest_repo),
):
    quests = await quest_repo.load_all()
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = [i for i in quest.get("checklist", []) if i["id"] != item_id]
    await quest_repo.update_checklist(quest_id, checklist)
    return _render_checklist(request, quest_id, checklist)


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
