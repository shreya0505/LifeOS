"""Hard 90 Challenge — HTTP routes."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.challenge import config as C
from core.challenge import anchors as anchor_engine
from core.challenge import era_names, level_engine, metrics_engine, reset_engine
from core.utils import today_local

from web.deps import (
    get_challenge_entry_repo,
    get_challenge_era_repo,
    get_challenge_experiment_repo,
    get_challenge_repo,
    get_challenge_task_repo,
)

router = APIRouter(prefix="/challenge")


def _render(request, name, context):
    from web.app import templates
    return templates.TemplateResponse(request, name, context)


def _days_elapsed(start_date: str) -> int:
    """Inclusive calendar-day counter: start_date = day 1."""
    start = date.fromisoformat(start_date)
    today = today_local()
    if today < start:
        return 0
    return (today - start).days + 1


def _target_info(challenge: dict) -> dict:
    """Compute which day the user should currently fill.

    target_day_num = first unsealed day (challenge.days_elapsed + 1).
    If stored days already >= calendar day → caught up, nothing to fill.
    """
    start_dt = date.fromisoformat(challenge["start_date"])
    calendar_day = _days_elapsed(challenge["start_date"])
    stored = challenge["days_elapsed"] or 0
    target_day_num = stored + 1
    caught_up_sealed = stored >= calendar_day  # today sealed, nothing to fill
    # Clamp target_date to today when caught up (display only)
    effective_day = min(target_day_num, max(calendar_day, 1))
    target_date = start_dt + timedelta(days=effective_day - 1)
    days_behind = max(0, calendar_day - target_day_num)
    is_backfill = (not caught_up_sealed) and target_day_num < calendar_day
    return {
        "target_day_num": target_day_num,
        "target_date": target_date.isoformat(),
        "target_date_fmt": target_date.strftime("%b %d"),
        "calendar_day": calendar_day,
        "caught_up_sealed": caught_up_sealed,
        "is_backfill": is_backfill,
        "days_behind": days_behind,
    }


def _decorate_experiment(exp: dict, today: date | None = None) -> dict:
    today = today or today_local()
    out = dict(exp)
    out["timeframe_label"] = C.EXPERIMENT_TIMEFRAME_LABELS.get(
        exp.get("timeframe"), exp.get("timeframe", "").title(),
    )
    out["duration_days"] = C.EXPERIMENT_TIMEFRAME_DAYS.get(exp.get("timeframe"), 0)
    out["verdict_label"] = (
        C.EXPERIMENT_VERDICTS.get(exp.get("verdict")) if exp.get("verdict") else None
    )
    out["is_overdue"] = False
    out["days_remaining"] = None
    out["trial_progress_pct"] = 0
    out["time_signal"] = "Awaiting start"
    if exp.get("status") == "running" and exp.get("started_at") and exp.get("ends_at"):
        start = date.fromisoformat(exp["started_at"])
        end = date.fromisoformat(exp["ends_at"])
        duration = max(1, (end - start).days + 1)
        elapsed = max(0, (today - start).days + 1)
        out["trial_progress_pct"] = min(100, round(elapsed / duration * 100))
        if today > end:
            overdue = (today - end).days
            out["is_overdue"] = True
            out["days_remaining"] = -overdue
            out["time_signal"] = f"{overdue} day{'s' if overdue != 1 else ''} overdue"
        else:
            remaining = (end - today).days + 1
            out["days_remaining"] = remaining
            out["time_signal"] = (
                f"{remaining} day{'s' if remaining != 1 else ''} remaining"
            )
    return out


def _decorate_experiments(experiments: list[dict]) -> list[dict]:
    today = today_local()
    return [_decorate_experiment(exp, today) for exp in experiments]


async def _build_today_context(
    challenge: dict, task_repo, entry_repo, experiment_repo=None,
) -> dict:
    info = _target_info(challenge)
    target_date = info["target_date"]
    today_str = today_local().isoformat()

    tasks = await task_repo.get_by_challenge(challenge["id"])
    target_entries = await entry_repo.get_by_date(challenge["id"], target_date)
    entries_by_task = {e["task_id"]: e for e in target_entries}

    by_bucket: dict[str, list] = {b: [] for b in C.BUCKETS}
    for t in tasks:
        ent = entries_by_task.get(t["id"])
        row = {
            **t,
            "current_state": ent["state"] if ent else None,
            "current_notes": (ent["notes"] if ent else "") or "",
        }
        by_bucket[t["bucket"]].append(row)

    experiments = []
    if experiment_repo is not None:
        experiments = _decorate_experiments(
            await experiment_repo.get_for_today(target_date)
        )

    start_dt = date.fromisoformat(challenge["start_date"])
    today_fmt = today_local().strftime("%b %d")
    tick_dates = [
        (start_dt + timedelta(days=i)).strftime("%b %d")
        for i in range(C.CHALLENGE_LENGTH_DAYS)
    ]

    tracked_task_ids = {t["id"] for t in tasks if t["bucket"] in C.TRACKED_BUCKETS}
    tracked_total = len(tracked_task_ids)
    tracked_rated = sum(1 for e in target_entries if e["task_id"] in tracked_task_ids)
    total_rated = len(target_entries)

    caught_up_sealed = info["caught_up_sealed"]
    can_seal = (
        tracked_total > 0
        and tracked_rated >= tracked_total
        and not caught_up_sealed
    )
    if can_seal:
        seal_block_reason = ""
    elif caught_up_sealed:
        seal_block_reason = f"DAY {challenge['days_elapsed']} LOCKED · NEXT WINDOW TOMORROW"
    elif tracked_total == 0:
        seal_block_reason = "NO TRACKED TASKS · NOTHING TO LOCK"
    else:
        seal_block_reason = (
            f"{tracked_rated}/{tracked_total} TRACKED TASKS RATED · COMPLETE TO LOCK"
        )

    return {
        "challenge": challenge,
        # header still shows calendar-derived day count
        "days_elapsed": info["calendar_day"],
        "days_total": C.CHALLENGE_LENGTH_DAYS,
        # input-day info
        "target_day_num": info["target_day_num"],
        "target_date": target_date,
        "target_date_fmt": info["target_date_fmt"],
        "is_backfill": info["is_backfill"],
        "days_behind": info["days_behind"],
        "buckets": C.BUCKETS,
        "bucket_labels": C.BUCKET_LABELS,
        "bucket_descriptions": C.BUCKET_DESCRIPTIONS,
        "by_bucket": by_bucket,
        "experiments": experiments,
        "experiment_timeframe_labels": C.EXPERIMENT_TIMEFRAME_LABELS,
        "experiment_verdicts": C.EXPERIMENT_VERDICTS,
        "states": C.STATES,
        "state_icons": C.STATE_ICONS,
        "state_labels": C.STATE_LABELS,
        "state_short": C.STATE_SHORT,
        "today_str": today_str,
        "today_fmt": today_fmt,
        "tick_dates": tick_dates,
        "tracked_rated": tracked_rated,
        "tracked_total": tracked_total,
        "total_rated": total_rated,
        "total_tasks": len(tasks),
        "can_seal": can_seal,
        "seal_block_reason": seal_block_reason,
        "is_sealed_today": caught_up_sealed,
    }


# ── Index dispatcher ────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
):
    active = await challenge_repo.get_active()
    if active is None:
        return RedirectResponse("/challenge/setup", status_code=303)
    return RedirectResponse("/challenge/today", status_code=303)


# ── Setup wizard ────────────────────────────────────────────────────────────

@router.get("/setup", response_class=HTMLResponse)
async def setup_page(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
):
    active = await challenge_repo.get_active()
    return _render(request, "challenge_setup.html", {
        "active": active,
        "buckets": C.BUCKETS,
        "bucket_labels": C.BUCKET_LABELS,
        "bucket_descriptions": C.BUCKET_DESCRIPTIONS,
    })


@router.post("/setup", response_class=HTMLResponse)
async def setup_submit(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    era_repo=Depends(get_challenge_era_repo),
):
    form = await request.form()
    tasks = []
    seen: set[str] = set()
    for bucket in C.BUCKETS:
        names = [v.strip() for v in form.getlist(f"{bucket}[]") if v.strip()]
        for n in names:
            key = n.casefold()
            if key in seen:
                continue
            seen.add(key)
            tasks.append({"name": n, "bucket": bucket})

    if not tasks:
        return RedirectResponse("/challenge/setup", status_code=303)

    anchor_count = sum(1 for t in tasks if t["bucket"] == "anchor")
    if anchor_count == 0:
        return RedirectResponse("/challenge/setup", status_code=303)

    existing = await challenge_repo.get_active()
    if existing:
        return RedirectResponse("/challenge/today", status_code=303)

    era_name = await era_names.pick_era_name(era_repo)
    midweek_adj = era_names.pick_midweek_adjective()
    start_date = today_local().isoformat()

    ch = await challenge_repo.create(era_name, start_date, midweek_adj)
    await task_repo.create_batch(ch["id"], tasks)

    # Compute initial level
    level_id, level_name, _ = level_engine.compute_level(0, midweek_adj)
    await challenge_repo.update_level(ch["id"], level_id, level_name)

    return RedirectResponse("/challenge/today", status_code=303)


# ── Today ───────────────────────────────────────────────────────────────────

@router.get("/today", response_class=HTMLResponse)
async def today_page(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return RedirectResponse("/challenge/setup", status_code=303)

    ctx = await _build_today_context(ch, task_repo, entry_repo, experiment_repo)
    return _render(request, "challenge_today.html", ctx)


@router.post("/today/entry/{task_id}", response_class=HTMLResponse)
async def update_entry(
    request: Request,
    task_id: str,
    state: str = Form(...),
    notes: str = Form(""),
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return HTMLResponse("", status_code=404)

    task = await task_repo.get_by_id(task_id)
    if task is None or task["challenge_id"] != ch["id"]:
        return HTMLResponse("", status_code=404)

    if state not in C.STATES:
        return HTMLResponse("Invalid state", status_code=400)

    info = _target_info(ch)
    if info["caught_up_sealed"]:
        return HTMLResponse("Nothing to fill — come back tomorrow.", status_code=400)
    target_date = info["target_date"]
    # Sealed days are immutable: reject any write whose target_date is already sealed.
    # (By construction target_date is the next unsealed day, so this is a safety net.)
    if info["target_day_num"] <= (ch["days_elapsed"] or 0):
        return HTMLResponse("Day already sealed — entries are locked.", status_code=400)
    await entry_repo.upsert(task_id, ch["id"], target_date, state, notes.strip() or None)

    # Recompute context, re-render single card + OOB seal button refresh
    ctx = await _build_today_context(ch, task_repo, entry_repo, experiment_repo)
    # Find updated task row
    task_row = None
    for b in C.BUCKETS:
        for t in ctx["by_bucket"][b]:
            if t["id"] == task_id:
                task_row = t
                break
    from web.app import templates
    card_html = templates.get_template("challenge_task_card.html").render(
        {**ctx, "task": task_row, "request": request},
    )
    bar_html = templates.get_template("_ch_seal_bar.html").render(
        {**ctx, "oob": True, "request": request},
    )
    return HTMLResponse(card_html + bar_html)


@router.post("/today/seal", response_class=HTMLResponse)
async def seal_day(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
    era_repo=Depends(get_challenge_era_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return HTMLResponse("", status_code=404)

    info = _target_info(ch)
    if info["caught_up_sealed"]:
        ctx = await _build_today_context(ch, task_repo, entry_repo, experiment_repo)
        return _render(request, "challenge_today.html", ctx)

    target_date = info["target_date"]
    tasks = await task_repo.get_by_challenge(ch["id"])
    target_entries = await entry_repo.get_by_date(ch["id"], target_date)
    entries_by_task = {e["task_id"]: e for e in target_entries}

    # Verify all tracked tasks rated for target_date
    for t in tasks:
        if t["bucket"] in C.TRACKED_BUCKETS and t["id"] not in entries_by_task:
            ctx = await _build_today_context(ch, task_repo, entry_repo, experiment_repo)
            return _render(request, "challenge_today.html", ctx)

    # Check reset across tracked tasks (per-task rolling window) — runs every seal
    reset_cause = None
    trigger_task_id = None
    for t in tasks:
        if t["bucket"] not in C.TRACKED_BUCKETS:
            continue
        all_ent = await entry_repo.get_all_for_task(t["id"])
        h = reset_engine.check_hard(all_ent)
        s = reset_engine.check_soft(all_ent)
        if h:
            reset_cause, trigger_task_id = "hard", t["id"]
            break
        if s and reset_cause is None:
            reset_cause, trigger_task_id = "soft", t["id"]

    # Advance exactly one day per seal
    new_days = info["target_day_num"]
    today_str = today_local().isoformat()  # era transition dates use real today
    midweek_adj = ch["midweek_adjective"] or era_names.pick_midweek_adjective()

    if reset_cause:
        trigger_task = next((t for t in tasks if t["id"] == trigger_task_id), None)
        peak_name_id, peak_name, _ = level_engine.compute_level(
            ch["peak_level"], midweek_adj,
        )
        prose = metrics_engine.era_prose(
            ch["era_name"], new_days, peak_name, reset_cause,
            trigger_task["name"] if trigger_task else None,
        )
        await era_repo.create(
            ch["era_name"], ch["start_date"], today_str,
            new_days, ch["peak_level"], reset_cause, trigger_task_id, prose,
        )
        await challenge_repo.mark_reset(ch["id"])
        # Start new era (tasks preserved structurally but tied to old challenge;
        # create new challenge + copy tasks)
        new_era = await era_names.pick_era_name(era_repo)
        new_adj = era_names.pick_midweek_adjective()
        new_ch = await challenge_repo.create(
            new_era, today_str, new_adj,
        )
        task_copies = [{"name": t["name"], "bucket": t["bucket"]} for t in tasks]
        await task_repo.create_batch(new_ch["id"], task_copies)
        lvl_id, lvl_name, _ = level_engine.compute_level(0, new_adj)
        await challenge_repo.update_level(new_ch["id"], lvl_id, lvl_name)
        return _render(request, "challenge_cinematic_reset.html", {
            "old_era": ch["era_name"],
            "new_era": new_era,
            "reset_cause": reset_cause,
            "trigger_task": trigger_task["name"] if trigger_task else None,
            "peak_level_name": peak_name,
            "days_elapsed": new_days,
            "prose": prose,
        })

    # No reset: update days + level
    await challenge_repo.update_days(ch["id"], new_days)
    lvl_id, lvl_name, is_main = level_engine.compute_level(new_days, midweek_adj)
    prev_level = ch["current_level"]
    await challenge_repo.update_level(ch["id"], lvl_id, lvl_name)
    await challenge_repo.update_peak_level(ch["id"], lvl_id)

    # Completion check
    if level_engine.is_complete(new_days):
        prose = metrics_engine.era_prose(
            ch["era_name"], new_days, lvl_name, "completed", None,
        )
        await era_repo.create(
            ch["era_name"], ch["start_date"], today_str,
            new_days, lvl_id, "completed", None, prose,
        )
        await challenge_repo.mark_completed(ch["id"])
        return _render(request, "challenge_cinematic_complete.html", {
            "era": ch["era_name"],
            "days_elapsed": new_days,
            "peak_level_name": lvl_name,
            "prose": prose,
        })

    # Promotion?
    promoted = lvl_id > prev_level
    if promoted and is_main:
        return _render(request, "challenge_cinematic_promote.html", {
            "level_name": lvl_name,
            "days_elapsed": new_days,
            "era": ch["era_name"],
        })
    if promoted and not is_main:
        return _render(request, "challenge_cinematic_midweek.html", {
            "level_name": lvl_name,
            "days_elapsed": new_days,
        })

    # Normal seal
    ch2 = await challenge_repo.get_active()
    ctx = await _build_today_context(ch2, task_repo, entry_repo, experiment_repo)
    ctx["just_sealed"] = True
    ctx["just_sealed_day"] = new_days
    return _render(request, "challenge_today.html", ctx)


# ── Forfeit ─────────────────────────────────────────────────────────────────

@router.post("/forfeit", response_class=HTMLResponse)
async def forfeit(
    request: Request,
    confirm: str = Form(""),
    restart_mode: str = Form("same"),
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    era_repo=Depends(get_challenge_era_repo),
):
    if confirm != "yes":
        return RedirectResponse("/challenge/today", status_code=303)

    ch = await challenge_repo.get_active()
    if ch is None:
        return RedirectResponse("/challenge/setup", status_code=303)

    today_str = today_local().isoformat()
    days_done = _days_elapsed(ch["start_date"])
    midweek_adj = ch["midweek_adjective"] or ""
    _, peak_name, _ = level_engine.compute_level(ch["peak_level"], midweek_adj)
    prose = metrics_engine.era_prose(
        ch["era_name"], days_done, peak_name, "forfeit", None,
    )
    await era_repo.create(
        ch["era_name"], ch["start_date"], today_str,
        days_done, ch["peak_level"], "forfeit", None, prose,
    )
    await challenge_repo.mark_reset(ch["id"])

    if restart_mode == "setup":
        return RedirectResponse("/challenge/setup", status_code=303)

    # Start new era with same tasks.
    tasks = await task_repo.get_by_challenge(ch["id"])
    new_era = await era_names.pick_era_name(era_repo)
    new_adj = era_names.pick_midweek_adjective()
    new_ch = await challenge_repo.create(new_era, today_str, new_adj)
    await task_repo.create_batch(
        new_ch["id"],
        [{"name": t["name"], "bucket": t["bucket"]} for t in tasks],
    )
    lvl_id, lvl_name, _ = level_engine.compute_level(0, new_adj)
    await challenge_repo.update_level(new_ch["id"], lvl_id, lvl_name)

    return _render(request, "challenge_cinematic_forfeit.html", {
        "old_era": ch["era_name"],
        "new_era": new_era,
        "days_elapsed": days_done,
        "peak_level_name": peak_name,
        "prose": prose,
    })


# ── Metrics ─────────────────────────────────────────────────────────────────

@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return RedirectResponse("/challenge/setup", status_code=303)

    tasks = await task_repo.get_by_challenge(ch["id"])
    all_entries = await entry_repo.get_all_for_challenge(ch["id"])

    entries_by_task: dict[str, list] = {t["id"]: [] for t in tasks}
    for e in all_entries:
        entries_by_task.setdefault(e["task_id"], []).append(e)
    for tid in entries_by_task:
        entries_by_task[tid].sort(key=lambda e: e["log_date"])

    task_names = {t["id"]: t["name"] for t in tasks}
    tracked_ids = {t["id"] for t in tasks if t["bucket"] in C.TRACKED_BUCKETS}
    health_map = metrics_engine.build_task_health_map(entries_by_task, tasks)
    survival = metrics_engine.survival_index(health_map)

    entries_by_bucket: dict[str, list] = {b: [] for b in C.BUCKETS}
    for t in tasks:
        entries_by_bucket[t["bucket"]].extend(entries_by_task.get(t["id"], []))

    days_elapsed = _days_elapsed(ch["start_date"])
    enricher_stats = metrics_engine.enricher_engagement(
        entries_by_bucket["enricher"], days_elapsed,
    )
    posture = metrics_engine.bucket_posture(entries_by_bucket)
    callouts = metrics_engine.pattern_callouts(entries_by_task, task_names)

    # Per-task health with names+buckets + last-14 states for sparkline
    health_rows = []
    for t in tasks:
        if t["bucket"] in C.TRACKED_BUCKETS:
            h = health_map.get(t["id"], {})
            last14 = [
                STATE_RANK_for(e) for e in entries_by_task.get(t["id"], [])[-14:]
            ]
            health_rows.append({
                "id": t["id"],
                "name": t["name"],
                "bucket": t["bucket"],
                "spark": last14,
                **h,
            })

    _, cur_level_name, _ = level_engine.compute_level(
        days_elapsed, ch["midweek_adjective"] or "",
    )
    _, peak_name, _ = level_engine.compute_level(
        ch["peak_level"], ch["midweek_adjective"] or "",
    )

    # ── Time-series + behavioral metrics ───────────────────────────────────
    tracked_entries_by_task = {
        tid: sorted(entries_by_task.get(tid, []), key=lambda e: e["log_date"])
        for tid in tracked_ids
    }
    quality_series = metrics_engine.daily_quality_series(
        entries_by_task, tracked_ids,
    )
    m_momentum = metrics_engine.momentum(quality_series)
    m_consistency = metrics_engine.consistency_index(quality_series)
    m_recovery = metrics_engine.recovery_rate(tracked_entries_by_task)
    m_streaks = metrics_engine.streak_runs(quality_series)
    m_weekday = metrics_engine.weekday_posture(quality_series)
    m_keystone = metrics_engine.keystone_task(
        tracked_entries_by_task, quality_series, task_names,
    )
    m_fragile = metrics_engine.fragile_task(health_map, task_names)
    m_velocity = metrics_engine.tier_velocity(days_elapsed, ch["peak_level"])
    m_engagement = metrics_engine.engagement_curve(
        [e for tid in tracked_ids for e in entries_by_task.get(tid, [])]
    )

    # Data-gate countdowns: 0 = ready
    gates = {
        "momentum": max(0, metrics_engine.GATE_MOMENTUM - days_elapsed),
        "consistency": max(0, metrics_engine.GATE_CONSISTENCY - days_elapsed),
        "recovery": max(0, metrics_engine.GATE_RECOVERY - days_elapsed),
        "weekday": max(0, metrics_engine.GATE_WEEKDAY - days_elapsed),
        "task_signal": max(0, metrics_engine.GATE_TASK_SIGNAL - days_elapsed),
        "tier_velocity": max(0, metrics_engine.GATE_TIER_VELOCITY - days_elapsed),
    }

    narrative_state = {
        "era_name": ch["era_name"],
        "survival_pct": int(survival * 100),
        "momentum_dir": m_momentum["direction"] if m_momentum else None,
        "streak_current": m_streaks["current"],
        "streak_peak": m_streaks["peak"],
    }

    sys_status = metrics_engine.system_status(int(survival * 100), health_map)
    sys_verdict = metrics_engine.system_verdict(sys_status, m_momentum, m_fragile)
    sys_directive = metrics_engine.directive(m_fragile, m_keystone, m_momentum)

    # Build tier rail data: main-level boundaries across 90 days
    tier_rail = []
    for week in range(len(C.MAIN_LEVEL_NAMES)):
        day_start = week * 7
        if day_start >= C.CHALLENGE_LENGTH_DAYS:
            break
        tier_rail.append({
            "name": C.MAIN_LEVEL_NAMES[week],
            "day_start": day_start,
            "day_end": min(day_start + 7, C.CHALLENGE_LENGTH_DAYS),
        })

    return _render(request, "challenge_metrics.html", {
        "challenge": ch,
        "days_elapsed": days_elapsed,
        "days_total": C.CHALLENGE_LENGTH_DAYS,
        "survival_index": survival,
        "survival_pct": int(survival * 100),
        "health_rows": health_rows,
        "posture": posture,
        "bucket_labels": C.BUCKET_LABELS,
        "callouts": callouts,
        "enricher": enricher_stats,
        "state_labels": C.STATE_LABELS,
        "state_icons": C.STATE_ICONS,
        "current_level_name": cur_level_name,
        "peak_level_name": peak_name,
        "peak_level": ch["peak_level"],
        # New time-series + behavioral
        "quality_series": quality_series,
        "momentum": m_momentum,
        "consistency": m_consistency,
        "recovery": m_recovery,
        "streaks": m_streaks,
        "weekday": m_weekday,
        "keystone": m_keystone,
        "fragile": m_fragile,
        "tier_velocity": m_velocity,
        "engagement": m_engagement,
        "pulse_quote": metrics_engine.pulse_quote(m_momentum),
        "rhythm_quote": metrics_engine.rhythm_quote(m_weekday),
        "closing_narrative": metrics_engine.closing_narrative(narrative_state),
        "gates": gates,
        "tier_rail": tier_rail,
        "system_status": sys_status,
        "system_verdict": sys_verdict,
        "directive": sys_directive,
    })


def STATE_RANK_for(entry: dict) -> int:
    return C.STATE_RANK.get(entry["state"], 0)


# ── Tiny Experiments ────────────────────────────────────────────────────────

async def _build_experiments_context(challenge: dict, experiment_repo) -> dict:
    experiments = _decorate_experiments(await experiment_repo.get_all())
    entries = await experiment_repo.get_all_entries()
    entries_by_experiment: dict[str, list] = {e["id"]: [] for e in experiments}
    for entry in entries:
        entries_by_experiment.setdefault(entry["experiment_id"], []).append(entry)

    verdict_counts = {key: 0 for key in C.EXPERIMENT_VERDICTS}
    for exp in experiments:
        exp_entries = entries_by_experiment.get(exp["id"], [])
        exp["entries"] = exp_entries
        exp["entry_count"] = len(exp_entries)
        exp["notes_count"] = sum(1 for e in exp_entries if e.get("notes"))
        ranks = [C.STATE_RANK.get(e["state"], 0) for e in exp_entries]
        exp["avg_rank"] = round(sum(ranks) / len(ranks), 2) if ranks else None
        if exp.get("verdict") in verdict_counts:
            verdict_counts[exp["verdict"]] += 1

    running_count = sum(1 for exp in experiments if exp["status"] == "running")
    judged_count = sum(1 for exp in experiments if exp["status"] == "judged")
    abandoned_count = sum(1 for exp in experiments if exp["status"] == "abandoned")
    summary = {
        "total": len(experiments),
        "draft": sum(1 for exp in experiments if exp["status"] == "draft"),
        "running": running_count,
        "judged": judged_count,
        "abandoned": abandoned_count,
        "slots_remaining": max(0, 3 - running_count),
        "entries": len(entries),
        "notes": sum(1 for entry in entries if entry.get("notes")),
    }
    return {
        "challenge": challenge,
        "experiments": experiments,
        "summary": summary,
        "verdict_counts": verdict_counts,
        "states": C.STATES,
        "state_labels": C.STATE_LABELS,
        "state_short": C.STATE_SHORT,
        "experiment_timeframe_labels": C.EXPERIMENT_TIMEFRAME_LABELS,
        "experiment_verdicts": C.EXPERIMENT_VERDICTS,
    }


@router.get("/experiments", response_class=HTMLResponse)
async def experiments_page(
    request: Request,
    challenge_repo=Depends(get_challenge_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return RedirectResponse("/challenge/setup", status_code=303)
    ctx = await _build_experiments_context(ch, experiment_repo)
    return _render(request, "challenge_experiments.html", ctx)


@router.post("/experiments", response_class=HTMLResponse)
async def create_experiment(
    request: Request,
    action: str = Form(""),
    motivation: str = Form(""),
    timeframe: str = Form("week"),
    challenge_repo=Depends(get_challenge_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return RedirectResponse("/challenge/setup", status_code=303)
    action = action.strip()
    motivation = motivation.strip()
    if not action or not motivation or timeframe not in C.EXPERIMENT_TIMEFRAME_DAYS:
        return HTMLResponse("Invalid experiment protocol", status_code=400)
    await experiment_repo.create(ch["id"], action, motivation, timeframe)
    return RedirectResponse("/challenge/experiments", status_code=303)


@router.post("/experiments/{experiment_id}/start", response_class=HTMLResponse)
async def start_experiment(
    request: Request,
    experiment_id: str,
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    exp = await experiment_repo.start(experiment_id, today_local().isoformat())
    if exp is None:
        return HTMLResponse("Could not begin trial", status_code=400)
    return RedirectResponse(
        request.headers.get("referer") or "/challenge/experiments",
        status_code=303,
    )


@router.post("/experiments/{experiment_id}/entry", response_class=HTMLResponse)
async def update_experiment_entry(
    request: Request,
    experiment_id: str,
    state: str = Form(...),
    notes: str = Form(""),
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    ch = await challenge_repo.get_active()
    if ch is None:
        return HTMLResponse("", status_code=404)
    exp = await experiment_repo.get_by_id(experiment_id)
    if exp is None:
        return HTMLResponse("", status_code=404)
    if exp["status"] != "running":
        return HTMLResponse("Trial is not running", status_code=400)
    if state not in C.STATES:
        return HTMLResponse("Invalid state", status_code=400)

    info = _target_info(ch)
    if info["caught_up_sealed"]:
        return HTMLResponse("Nothing to fill — come back tomorrow.", status_code=400)
    if info["target_day_num"] <= (ch["days_elapsed"] or 0):
        return HTMLResponse("Day already sealed — entries are locked.", status_code=400)
    await experiment_repo.upsert_entry(
        experiment_id,
        exp["challenge_id"],
        info["target_date"],
        state,
        notes.strip() or None,
    )
    ctx = await _build_today_context(ch, task_repo, entry_repo, experiment_repo)
    experiment = next((e for e in ctx["experiments"] if e["id"] == experiment_id), None)
    if experiment is None:
        return HTMLResponse("", status_code=404)
    from web.app import templates
    return HTMLResponse(templates.get_template("challenge_experiment_card.html").render(
        {**ctx, "experiment": experiment, "request": request},
    ))


@router.post("/experiments/{experiment_id}/judge", response_class=HTMLResponse)
async def judge_experiment(
    request: Request,
    experiment_id: str,
    verdict: str = Form(...),
    observation_notes: str = Form(""),
    conclusion_notes: str = Form(""),
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    if verdict not in C.EXPERIMENT_VERDICTS:
        return HTMLResponse("Invalid verdict", status_code=400)
    exp = await experiment_repo.judge(
        experiment_id,
        verdict,
        observation_notes.strip() or None,
        conclusion_notes.strip() or None,
    )
    if exp is None:
        return HTMLResponse("Could not archive verdict", status_code=400)
    return RedirectResponse("/challenge/experiments", status_code=303)


@router.post("/experiments/{experiment_id}/abandon", response_class=HTMLResponse)
async def abandon_experiment(
    request: Request,
    experiment_id: str,
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    exp = await experiment_repo.abandon(experiment_id)
    if exp is None:
        return HTMLResponse("Could not abandon trial", status_code=400)
    return RedirectResponse(
        request.headers.get("referer") or "/challenge/experiments",
        status_code=303,
    )


@router.post("/experiments/{experiment_id}/trash", response_class=HTMLResponse)
async def trash_experiment(
    request: Request,
    experiment_id: str,
    experiment_repo=Depends(get_challenge_experiment_repo),
):
    trashed = await experiment_repo.trash_draft(experiment_id)
    if not trashed:
        return HTMLResponse("Could not trash draft", status_code=400)
    return RedirectResponse(
        request.headers.get("referer") or "/challenge/experiments",
        status_code=303,
    )


# ── History ─────────────────────────────────────────────────────────────────

@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    era_repo=Depends(get_challenge_era_repo),
    challenge_repo=Depends(get_challenge_repo),
    task_repo=Depends(get_challenge_task_repo),
    entry_repo=Depends(get_challenge_entry_repo),
):
    eras = await era_repo.get_all()
    active = await challenge_repo.get_active()

    # Anchors for active era
    active_anchors: list[dict] = []
    if active:
        active_tasks = await task_repo.get_by_challenge(active["id"])
        active_entries = await entry_repo.get_all_for_challenge(active["id"])
        today_iso = today_local().isoformat()
        today_day = _days_elapsed(active["start_date"])
        active_anchors = anchor_engine.compute_era_anchors(
            start_date=active["start_date"],
            end_date=today_iso,
            duration_days=max(active.get("days_elapsed") or 0, today_day),
            entries=active_entries,
            tasks=active_tasks,
            reset_cause=None,
            trigger_task_name=None,
            is_active=True,
            today_iso=today_iso,
            today_day_num=today_day,
        )

    # Anchors for archived eras (lookup challenge by start_date)
    era_anchor_map: dict[str, list[dict]] = {}
    for era in eras:
        ch = await challenge_repo.get_by_start_date(era["start_date"])
        if ch is None:
            era_anchor_map[era["id"]] = []
            continue
        ch_tasks = await task_repo.get_by_challenge(ch["id"])
        ch_entries = await entry_repo.get_all_for_challenge(ch["id"])
        trigger_name = None
        if era.get("reset_trigger_task_id"):
            trig = await task_repo.get_by_id(era["reset_trigger_task_id"])
            trigger_name = trig["name"] if trig else None
        era_anchor_map[era["id"]] = anchor_engine.compute_era_anchors(
            start_date=era["start_date"],
            end_date=era["end_date"],
            duration_days=era["duration_days"],
            entries=ch_entries,
            tasks=ch_tasks,
            reset_cause=era["reset_cause"],
            trigger_task_name=trigger_name,
            is_active=False,
        )

    timeline = anchor_engine.cluster_false_starts(eras)

    return _render(request, "challenge_history.html", {
        "eras": eras,
        "active": active,
        "active_anchors": active_anchors,
        "era_anchor_map": era_anchor_map,
        "timeline": timeline,
    })
