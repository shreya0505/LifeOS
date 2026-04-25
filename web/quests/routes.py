"""Quest CRUD routes — HTML fragments for HTMX."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from core.config import VALID_SOURCES, PRIORITY_NAMES, PRIORITY_GLYPHS, USER_TZ
from core.utils import (
    fantasy_date, format_duration, get_elapsed, today_local, to_local_date,
    quest_age_days, quest_age_bucket, label_hue, is_url,
)
from core.pomo_queries import get_all_pomo_counts_today
from core.storage.sqlite_backend import SqliteArtifactKeyRepo
from web.deps import get_quest_repo, get_pomo_repo, get_workspace_repo
from web.pomos.engine import get_engine as _get_pomo_engine
from web.questlog_context import WORKSPACE_COOKIE, QuestlogContext, resolve_questlog_context

router = APIRouter()


# ── Column definitions ──────────────────────────────────────────────────
_COLUMNS = [
    {"status": "log",     "label": "Quest Board",  "icon": "scroll", "empty_text": "No quests inscribed yet."},
    {"status": "active",  "label": "In Battle",    "icon": "flame",  "empty_text": "No active quests."},
    {"status": "blocked", "label": "Blocked",       "icon": "shield", "empty_text": "Nothing blocked."},
    {"status": "done",    "label": "Conquered",     "icon": "check-circle", "empty_text": "No victories yet."},
]

_SORT_MODES = {"priority", "age"}
_WORKSPACE_ICONS = {"folder", "clipboard-list", "hammer", "target", "flame", "moon", "scroll", "tag"}
_WORKSPACE_COLORS = {"blue", "green", "amber", "rose", "violet", "slate"}


def _active_pomo_quest_id() -> str | None:
    engine = _get_pomo_engine()
    if engine.is_active and engine.session:
        return engine.session.get("quest_id")
    return None


def _active_pomo_workspace_id() -> str | None:
    engine = _get_pomo_engine()
    if engine.is_active and engine.session:
        return engine.session.get("workspace_id") or "work"
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


def _completed_dt(quest: dict) -> datetime | None:
    completed_at = quest.get("completed_at")
    if not completed_at:
        return None
    try:
        dt = datetime.fromisoformat(completed_at)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(USER_TZ)


def _legend_date_label(date_key: str) -> str:
    if date_key == "unknown":
        return "Unknown date"
    try:
        day = date.fromisoformat(date_key)
    except ValueError:
        return "Unknown date"
    today = today_local()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return f"{day.strftime('%B')} {day.day}, {day.year}"


async def _build_board_context(
    quest_repo,
    pomo_repo,
    *,
    workspace_id: str = "work",
    filter_priority: list[int] | None = None,
    filter_labels: list[str] | None = None,
    filter_project: str | None = None,
    filter_age: list[str] | None = None,
    sort_mode: str | None = None,
) -> tuple[list[dict], list[str], list[dict]]:
    """Build column data with enriched quest cards. Returns (columns, all_projects, all_labels_with_hue)."""
    quests = await quest_repo.load_all(workspace_id)
    sessions = await pomo_repo.load_all(workspace_id)
    pomo_counts = get_all_pomo_counts_today(sessions)

    today_str = today_local().isoformat()
    enriched_all = [
        _enrich_quest(q, pomo_counts, today_str)
        for q in quests if q["status"] != "abandoned"
    ]
    done_all = [q for q in enriched_all if q["status"] == "done"]
    done_stats = {
        "all_count": len(done_all),
        "today_count": sum(1 for q in done_all if q.get("done_today")),
        "archived_count": sum(1 for q in done_all if not q.get("done_today")),
    }

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
    by_status["done"] = sorted(
        (q for q in by_status["done"] if q.get("done_today")),
        key=lambda q: q.get("completed_at") or "",
        reverse=True,
    )

    columns = []
    for col_def in _COLUMNS:
        col = {**col_def, "quests": by_status[col_def["status"]]}
        if col_def["status"] == "done":
            col.update(done_stats)
        columns.append(col)
    return columns, all_projects, all_labels_with_hue


async def _build_legend_context(quest_repo, workspace_id: str) -> dict:
    today_str = today_local().isoformat()
    done_quests = [
        _enrich_quest(q, {}, today_str)
        for q in await quest_repo.load_all(workspace_id)
        if q["status"] == "done"
    ]
    for quest in done_quests:
        completed = _completed_dt(quest)
        quest["_completed_dt"] = completed
        quest["completed_time"] = completed.strftime("%H:%M") if completed else ""
        quest["completed_date"] = completed.date().isoformat() if completed else "unknown"

    done_quests.sort(
        key=lambda q: (
            q["_completed_dt"] is not None,
            q["_completed_dt"] or datetime.min.replace(tzinfo=USER_TZ),
        ),
        reverse=True,
    )

    by_date: dict[str, list[dict]] = defaultdict(list)
    for quest in done_quests:
        by_date[quest["completed_date"]].append(quest)

    def date_sort_key(date_key: str) -> tuple[int, str]:
        return (0, "") if date_key == "unknown" else (1, date_key)

    groups = [
        {
            "date": date_key,
            "label": _legend_date_label(date_key),
            "quests": grouped,
            "count": len(grouped),
        }
        for date_key, grouped in sorted(by_date.items(), key=lambda item: date_sort_key(item[0]), reverse=True)
    ]
    return {"legend_groups": groups, "legend_total": len(done_quests)}


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


async def _quest_counts(quest_repo, workspace_id: str) -> dict:
    quests = [q for q in await quest_repo.load_all(workspace_id) if q["status"] != "abandoned"]
    total = len(quests)
    active = sum(1 for q in quests if q["status"] == "active")
    done = sum(1 for q in quests if q["status"] == "done")
    return {"total": total, "active": active, "done": done}


async def _board_response(
    request,
    quest_repo,
    pomo_repo,
    filters: dict | None = None,
    key_repo=None,
    qctx: QuestlogContext | None = None,
):
    f = filters or {}
    workspace_id = qctx.workspace_id if qctx else "work"
    columns, all_projects, all_labels_with_hue = await _build_board_context(
        quest_repo, pomo_repo, workspace_id=workspace_id, **f
    )
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
        "current_workspace": qctx.workspace if qctx else None,
        "workspaces": qctx.workspaces if qctx else [],
        "request": request,
    })


def _render(request, name, context):
    """Render a Jinja2 template with Starlette 1.0 API."""
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


# ── Workspaces ──────────────────────────────────────────────────────────

@router.post("/workspaces/select", response_class=HTMLResponse)
async def select_workspace(
    request: Request,
    workspace_id: str = Form(...),
    workspace_repo=Depends(get_workspace_repo),
):
    workspace = await workspace_repo.get(workspace_id)
    if workspace is None:
        return HTMLResponse("Workspace not found.", status_code=404)
    active_workspace = _active_pomo_workspace_id()
    if active_workspace and active_workspace != workspace_id:
        return HTMLResponse("Finish the active pomo before switching workspaces.", status_code=409)
    response = HTMLResponse("")
    response.set_cookie(WORKSPACE_COOKIE, workspace_id, httponly=False, samesite="lax")
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/workspaces", response_class=HTMLResponse)
async def create_workspace(
    request: Request,
    name: str = Form(...),
    icon: str = Form("folder"),
    color: str = Form("blue"),
    workspace_repo=Depends(get_workspace_repo),
):
    if _active_pomo_workspace_id():
        return HTMLResponse("Finish the active pomo before creating a new workspace.", status_code=409)
    icon = icon if icon in _WORKSPACE_ICONS else "folder"
    color = color if color in _WORKSPACE_COLORS else "blue"
    name = name.strip()
    if not name:
        return HTMLResponse("Workspace name is required.", status_code=400)
    workspace = await workspace_repo.create(name, icon, color)
    response = HTMLResponse("")
    response.set_cookie(WORKSPACE_COOKIE, workspace["id"], httponly=False, samesite="lax")
    response.headers["HX-Refresh"] = "true"
    return response


# ── Full page ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request,
                quest_repo=Depends(get_quest_repo),
                pomo_repo=Depends(get_pomo_repo),
                qctx: QuestlogContext = Depends(resolve_questlog_context)):
    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    columns, all_projects, all_labels_with_hue = await _build_board_context(
        quest_repo, pomo_repo, workspace_id=qctx.workspace_id, **f
    )
    counts = await _quest_counts(quest_repo, qctx.workspace_id)
    sessions = await pomo_repo.load_all(qctx.workspace_id)
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
        "current_workspace": qctx.workspace,
        "workspaces": qctx.workspaces,
    })


# ── Quest board (HTMX partial) ──────────────────────────────────────────

@router.get("/quests", response_class=HTMLResponse)
async def quest_board(request: Request,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo),
                      qctx: QuestlogContext = Depends(resolve_questlog_context)):
    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


# ── Completed quest archive ─────────────────────────────────────────────

@router.get("/quests/legend", response_class=HTMLResponse)
async def quest_legend(request: Request,
                       quest_repo=Depends(get_quest_repo),
                       qctx: QuestlogContext = Depends(resolve_questlog_context)):
    return _render(request, "quest_legend.html", await _build_legend_context(quest_repo, qctx.workspace_id))


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
    qctx: QuestlogContext = Depends(resolve_questlog_context),
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
            workspace_id=qctx.workspace_id,
        )
    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)
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
                        qctx: QuestlogContext = Depends(resolve_questlog_context)):
    valid_sources = VALID_SOURCES.get(
        {"active": "start", "blocked": "block", "done": "done", "abandoned": "abandon"}.get(status, ""),
        set(),
    )
    quests = await quest_repo.load_all(qctx.workspace_id)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    transitioned = False
    if quest and quest["status"] in valid_sources:
        await quest_repo.update_status(quest_id, status, qctx.workspace_id)
        transitioned = True

    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)
    if transitioned and status == "done":
        response.headers["HX-Trigger"] = "quest-done"
    return response


# ── Toggle frog ──────────────────────────────────────────────────────────

@router.patch("/quests/{quest_id}/frog", response_class=HTMLResponse)
async def toggle_frog(request: Request,
                      quest_id: str,
                      quest_repo=Depends(get_quest_repo),
                      pomo_repo=Depends(get_pomo_repo),
                      qctx: QuestlogContext = Depends(resolve_questlog_context)):
    await quest_repo.toggle_frog(quest_id, qctx.workspace_id)
    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


# ── Abandon quest ────────────────────────────────────────────────────────

@router.post("/quests/{quest_id}/abandon", response_class=HTMLResponse)
async def abandon_quest(request: Request,
                        quest_id: str,
                        quest_repo=Depends(get_quest_repo),
                        pomo_repo=Depends(get_pomo_repo),
                        qctx: QuestlogContext = Depends(resolve_questlog_context)):
    await quest_repo.abandon(quest_id, qctx.workspace_id)
    f = await _parse_filter_params(request)
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    response = await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)
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
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    await quest_repo.update_priority(quest_id, max(0, min(4, priority)), qctx.workspace_id)
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo, qctx.workspace_id)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


@router.patch("/quests/{quest_id}/project", response_class=HTMLResponse)
async def update_project(
    request: Request,
    quest_id: str,
    project: str = Form(""),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    await quest_repo.update_project(quest_id, project.strip() or None, qctx.workspace_id)
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo, qctx.workspace_id)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


@router.put("/quests/{quest_id}/labels", response_class=HTMLResponse)
async def update_labels(
    request: Request,
    quest_id: str,
    labels: str = Form(""),
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    await quest_repo.update_labels(quest_id, label_list, qctx.workspace_id)
    if request.query_params.get("strip"):
        return await _meta_strip_response(request, quest_id, quest_repo, key_repo, qctx.workspace_id)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


@router.put("/quests/{quest_id}/artifacts", response_class=HTMLResponse)
async def update_artifacts(
    request: Request,
    quest_id: str,
    quest_repo=Depends(get_quest_repo),
    pomo_repo=Depends(get_pomo_repo),
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    form_data = await request.form()
    artifact_keys_raw = form_data.getlist("artifact_key[]")
    artifact_vals_raw = form_data.getlist("artifact_val[]")
    artifacts = {k: v for k, v in zip(artifact_keys_raw, artifact_vals_raw) if k.strip() and v.strip()}
    await quest_repo.update_artifacts(quest_id, artifacts, qctx.workspace_id)
    f = await _parse_filter_params(request)
    return await _board_response(request, quest_repo, pomo_repo, f, key_repo=key_repo, qctx=qctx)


async def _meta_strip_response(request, quest_id, quest_repo, key_repo, workspace_id: str):
    """Return just the meta strip partial (used by pomo screen edits)."""
    quests = await quest_repo.load_all(workspace_id)
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
    qctx: QuestlogContext = Depends(resolve_questlog_context),
):
    key_repo = SqliteArtifactKeyRepo(request.app.state.db, qctx.workspace_id)
    quests = await quest_repo.load_all(qctx.workspace_id)
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
    qctx = await resolve_questlog_context(request)
    quests = await quest_repo.load_all(qctx.workspace_id)
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
    qctx = await resolve_questlog_context(request)
    text = text.strip()
    if not text:
        quests = await quest_repo.load_all(qctx.workspace_id)
        quest = next((q for q in quests if q["id"] == quest_id), None)
        checklist = quest.get("checklist", []) if quest else []
        return _render_checklist(request, quest_id, checklist)

    quests = await quest_repo.load_all(qctx.workspace_id)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = list(quest.get("checklist", []))
    checklist.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False})
    await quest_repo.update_checklist(quest_id, checklist, qctx.workspace_id)
    return _render_checklist(request, quest_id, checklist)


@router.patch("/quests/{quest_id}/checklist/{item_id}/toggle", response_class=HTMLResponse)
async def toggle_checklist_item(
    request: Request,
    quest_id: str,
    item_id: str,
    quest_repo=Depends(get_quest_repo),
):
    qctx = await resolve_questlog_context(request)
    quests = await quest_repo.load_all(qctx.workspace_id)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = list(quest.get("checklist", []))
    for item in checklist:
        if item["id"] == item_id:
            item["done"] = not item["done"]
            break
    await quest_repo.update_checklist(quest_id, checklist, qctx.workspace_id)
    return _render_checklist(request, quest_id, checklist)


@router.delete("/quests/{quest_id}/checklist/{item_id}", response_class=HTMLResponse)
async def delete_checklist_item(
    request: Request,
    quest_id: str,
    item_id: str,
    quest_repo=Depends(get_quest_repo),
):
    qctx = await resolve_questlog_context(request)
    quests = await quest_repo.load_all(qctx.workspace_id)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest is None:
        return HTMLResponse("", status_code=404)

    checklist = [i for i in quest.get("checklist", []) if i["id"] != item_id]
    await quest_repo.update_checklist(quest_id, checklist, qctx.workspace_id)
    return _render_checklist(request, quest_id, checklist)


# ── Stats bar (HTMX polling) ────────────────────────────────────────────

@router.get("/stats", response_class=HTMLResponse)
async def stats_bar(request: Request,
                    quest_repo=Depends(get_quest_repo),
                    pomo_repo=Depends(get_pomo_repo)):
    qctx = await resolve_questlog_context(request)
    counts = await _quest_counts(quest_repo, qctx.workspace_id)
    sessions = await pomo_repo.load_all(qctx.workspace_id)
    pomo_count = sum(get_all_pomo_counts_today(sessions).values())
    return _render(request, "stats_bar.html", {
        "quest_counts": counts,
        "pomo_count": pomo_count,
    })
