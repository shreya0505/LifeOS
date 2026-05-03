"""Tests for Hard 90 Challenge — engines, backend repos, and HTTP routes."""

from __future__ import annotations

import pytest
from datetime import timedelta

from core.challenge import level_engine, metrics_engine, reset_engine
from core.challenge.config import CHALLENGE_LENGTH_DAYS
from core.storage.challenge_backend import (
    SqliteChallengeEntryRepo,
    SqliteChallengeEraRepo,
    SqliteChallengeExperimentRepo,
    SqliteChallengeHolidayRepo,
    SqliteChallengeRepo,
    SqliteChallengeTaskRepo,
)
from core.utils import today_local


# ── level_engine (pure) ──────────────────────────────────────────────────────

def test_level_day0_is_initiate():
    lid, name, is_main = level_engine.compute_level(0, "Relentless")
    assert name == "Initiate"
    assert is_main


def test_level_midweek_uses_adjective():
    lid, name, is_main = level_engine.compute_level(3, "Relentless")
    assert "Relentless" in name
    assert not is_main


def test_level_week2_main():
    lid, name, is_main = level_engine.compute_level(14, "X")
    assert name == "Wanderer"
    assert is_main


def test_level_completion():
    lid, name, is_main = level_engine.compute_level(CHALLENGE_LENGTH_DAYS, "X")
    assert name == "Godbound"
    assert is_main
    assert lid == 26


def test_is_complete_at_90():
    assert level_engine.is_complete(90)


def test_is_not_complete_at_89():
    assert not level_engine.is_complete(89)


def test_level_id_monotonic():
    prev_id = -1
    for d in range(0, 91, 7):
        lid, _, _ = level_engine.compute_level(d, "X")
        assert lid > prev_id
        prev_id = lid


# ── reset_engine (pure) ──────────────────────────────────────────────────────

def _e(state: str) -> dict:
    return {"state": state}


def test_check_hard_triggers_on_3_not_done():
    entries = [_e("NOT_DONE")] * 3
    assert reset_engine.check_hard(entries)


def test_check_hard_no_trigger_below_window():
    entries = [_e("NOT_DONE")] * 2
    assert not reset_engine.check_hard(entries)


def test_check_hard_no_trigger_mixed():
    entries = [_e("NOT_DONE"), _e("NOT_DONE"), _e("STARTED")]
    assert not reset_engine.check_hard(entries)


def test_check_soft_triggers_on_7_not_done_or_started():
    entries = [_e("NOT_DONE"), _e("STARTED")] * 3 + [_e("NOT_DONE")]
    assert reset_engine.check_soft(entries)


def test_check_soft_no_trigger_partial_breaks_streak():
    entries = [_e("NOT_DONE")] * 6 + [_e("PARTIAL")]
    assert not reset_engine.check_soft(entries)


def test_check_soft_no_trigger_below_window():
    entries = [_e("NOT_DONE")] * 6
    assert not reset_engine.check_soft(entries)


def test_enricher_never_resets():
    hard, soft = reset_engine.check_reset([_e("NOT_DONE")] * 10, "enricher", "NOT_DONE")
    assert not hard and not soft


# ── SqliteChallengeRepo ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_challenge_create_and_get_active(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era of Sovereign Awakening", today, "Relentless")
    assert ch["status"] == "active"
    assert ch["days_elapsed"] == 0

    active = await repo.get_active()
    assert active is not None
    assert active["id"] == ch["id"]


@pytest.mark.asyncio
async def test_challenge_get_active_none_when_empty(db):
    repo = SqliteChallengeRepo(db)
    assert await repo.get_active() is None


@pytest.mark.asyncio
async def test_challenge_update_days(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era X", today, "Relentless")
    await repo.update_days(ch["id"], 5)
    active = await repo.get_active()
    assert active["days_elapsed"] == 5
    assert active["days_remaining"] == 85


@pytest.mark.asyncio
async def test_challenge_update_level(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era X", today, "Relentless")
    await repo.update_level(ch["id"], 3, "Relentless Wanderer")
    active = await repo.get_active()
    assert active["current_level"] == 3
    assert active["current_level_name"] == "Relentless Wanderer"


@pytest.mark.asyncio
async def test_challenge_holiday_repo_creates_once_and_queues_sync(db):
    ch_repo = SqliteChallengeRepo(db)
    holiday_repo = SqliteChallengeHolidayRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "Relentless")

    first = await holiday_repo.create(ch["id"], today, "travel")
    second = await holiday_repo.create(ch["id"], today, "travel again")

    assert second["id"] == first["id"]
    assert await holiday_repo.dates_for_challenge(ch["id"]) == {today}
    rows = await (await db.execute(
        "SELECT table_name FROM sync_changes WHERE table_name = 'challenge_holidays'"
    )).fetchall()
    assert rows


def test_holiday_cadence_one_day_stays_neutral():
    cadence = metrics_engine.holiday_cadence(
        [{"log_date": "2026-01-03"}],
        "2026-01-01",
        "2026-01-10",
    )

    assert cadence["count"] == 1
    assert cadence["ratio_pct"] == 10
    assert cadence["load_score"] == 0
    assert cadence["label"] == "Neutral"


def test_holiday_cadence_exact_twenty_percent_stays_neutral():
    cadence = metrics_engine.holiday_cadence(
        [{"log_date": "2026-01-03"}, {"log_date": "2026-01-08"}],
        "2026-01-01",
        "2026-01-10",
    )

    assert cadence["ratio_pct"] == 20
    assert cadence["load_score"] == 0


def test_holiday_cadence_above_twenty_percent_raises_load():
    cadence = metrics_engine.holiday_cadence(
        [{"log_date": "2026-01-02"}, {"log_date": "2026-01-05"}, {"log_date": "2026-01-08"}],
        "2026-01-01",
        "2026-01-10",
    )

    assert cadence["ratio_pct"] == 30
    assert cadence["longest_streak"] == 1
    assert cadence["load_score"] > 0


def test_holiday_cadence_three_day_streak_raises_load():
    cadence = metrics_engine.holiday_cadence(
        [{"log_date": "2026-01-01"}, {"log_date": "2026-01-02"}, {"log_date": "2026-01-03"}],
        "2026-01-01",
        "2026-01-30",
    )

    assert cadence["ratio_pct"] == 10
    assert cadence["longest_streak"] == 3
    assert cadence["load_score"] > 0


def test_holidays_do_not_change_survival_or_task_health_scores():
    entries_by_task = {"anchor-1": []}
    tasks = [{"id": "anchor-1", "bucket": "anchor"}]
    health = metrics_engine.build_task_health_map(entries_by_task, tasks)
    before = metrics_engine.survival_index(health)
    cadence = metrics_engine.holiday_cadence(
        [{"log_date": "2026-01-01"}, {"log_date": "2026-01-02"}, {"log_date": "2026-01-03"}],
        "2026-01-01",
        "2026-01-10",
    )
    after = metrics_engine.survival_index(health)

    assert cadence["load_score"] > 0
    assert health["anchor-1"]["hard_progress"] == 0
    assert health["anchor-1"]["soft_progress"] == 0
    assert before == after == 1.0


@pytest.mark.asyncio
async def test_challenge_peak_level_never_regresses(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era X", today, "Relentless")
    await repo.update_peak_level(ch["id"], 5)
    await repo.update_peak_level(ch["id"], 2)
    active = await repo.get_active()
    assert active["peak_level"] == 5


@pytest.mark.asyncio
async def test_challenge_mark_reset(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era X", today, "Relentless")
    await repo.mark_reset(ch["id"])
    assert await repo.get_active() is None


@pytest.mark.asyncio
async def test_challenge_mark_completed(db):
    repo = SqliteChallengeRepo(db)
    today = today_local().isoformat()
    ch = await repo.create("Era X", today, "Relentless")
    await repo.mark_completed(ch["id"])
    # completed → no longer 'active'
    assert await repo.get_active() is None
    row = await repo.get_by_id(ch["id"])
    assert row["status"] == "completed"
    assert row["is_completed"]


# ── SqliteChallengeTaskRepo ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_create_batch_and_get(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    tasks = [
        {"name": "Morning run", "bucket": "anchor"},
        {"name": "Read", "bucket": "improver"},
        {"name": "Journal", "bucket": "enricher"},
    ]
    created = await t_repo.create_batch(ch["id"], tasks)
    assert len(created) == 3

    fetched = await t_repo.get_by_challenge(ch["id"])
    assert len(fetched) == 3
    # anchors come first
    assert fetched[0]["bucket"] == "anchor"


@pytest.mark.asyncio
async def test_task_get_by_id(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    [task] = await t_repo.create_batch(ch["id"], [{"name": "Run", "bucket": "anchor"}])
    fetched = await t_repo.get_by_id(task["id"])
    assert fetched["name"] == "Run"


@pytest.mark.asyncio
async def test_task_get_by_id_missing(db):
    t_repo = SqliteChallengeTaskRepo(db)
    assert await t_repo.get_by_id("nope") is None


# ── SqliteChallengeEntryRepo ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_entry_upsert_creates(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    e_repo = SqliteChallengeEntryRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    [task] = await t_repo.create_batch(ch["id"], [{"name": "Run", "bucket": "anchor"}])

    entry = await e_repo.upsert(task["id"], ch["id"], today, "COMPLETED_SATISFACTORY", None)
    assert entry["state"] == "COMPLETED_SATISFACTORY"
    assert entry["notes"] is None


@pytest.mark.asyncio
async def test_entry_upsert_updates_existing(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    e_repo = SqliteChallengeEntryRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    [task] = await t_repo.create_batch(ch["id"], [{"name": "Run", "bucket": "anchor"}])

    await e_repo.upsert(task["id"], ch["id"], today, "STARTED", None)
    updated = await e_repo.upsert(task["id"], ch["id"], today, "COMPLETED_SATISFACTORY", "felt good")
    assert updated["state"] == "COMPLETED_SATISFACTORY"
    assert updated["notes"] == "felt good"


@pytest.mark.asyncio
async def test_entry_upsert_allows_notes_before_rating(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    e_repo = SqliteChallengeEntryRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    [task] = await t_repo.create_batch(ch["id"], [{"name": "Run", "bucket": "anchor"}])

    partial = await e_repo.upsert(task["id"], ch["id"], today, None, "rough morning")
    assert partial["state"] is None
    assert partial["notes"] == "rough morning"

    rated = await e_repo.upsert(task["id"], ch["id"], today, "PARTIAL", "rough morning")
    assert rated["state"] == "PARTIAL"
    assert rated["notes"] == "rough morning"


@pytest.mark.asyncio
async def test_entry_get_by_date(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    e_repo = SqliteChallengeEntryRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    tasks = await t_repo.create_batch(ch["id"], [
        {"name": "A", "bucket": "anchor"},
        {"name": "B", "bucket": "improver"},
    ])
    for t in tasks:
        await e_repo.upsert(t["id"], ch["id"], today, "COMPLETED_SATISFACTORY", None)

    entries = await e_repo.get_by_date(ch["id"], today)
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_entry_get_all_for_task_chronological(db):
    ch_repo = SqliteChallengeRepo(db)
    t_repo = SqliteChallengeTaskRepo(db)
    e_repo = SqliteChallengeEntryRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    [task] = await t_repo.create_batch(ch["id"], [{"name": "Run", "bucket": "anchor"}])

    dates = ["2026-04-01", "2026-04-02", "2026-04-03"]
    for d in dates:
        await e_repo.upsert(task["id"], ch["id"], d, "COMPLETED_SATISFACTORY", None)

    all_e = await e_repo.get_all_for_task(task["id"])
    assert [e["log_date"] for e in all_e] == dates


@pytest.mark.asyncio
async def test_today_entry_route_allows_notes_before_rating_and_queues_sync(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    ch = await SqliteChallengeRepo(db).get_active()
    [task] = await SqliteChallengeTaskRepo(db).get_by_challenge(ch["id"])

    response = await client.post(
        f"/challenge/today/entry/{task['id']}",
        data={"notes": "captured before choosing a verdict"},
    )

    assert response.status_code == 200
    row = await (await db.execute(
        "SELECT state, notes FROM challenge_entries WHERE task_id = ?",
        (task["id"],),
    )).fetchone()
    assert row == (None, "captured before choosing a verdict")
    assert "0/1 rated" in response.text
    sync_row = await (await db.execute(
        "SELECT table_name FROM sync_changes WHERE table_name = 'challenge_entries'"
    )).fetchone()
    assert sync_row == ("challenge_entries",)


@pytest.mark.asyncio
async def test_holiday_deletes_existing_logs_freezes_progress_and_extends_trial(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    ch = await SqliteChallengeRepo(db).get_active()
    [task] = await SqliteChallengeTaskRepo(db).get_by_challenge(ch["id"])
    today = today_local().isoformat()

    await client.post(
        f"/challenge/today/entry/{task['id']}",
        data={"state": "COMPLETED_SATISFACTORY", "notes": "would be deleted"},
    )
    exp_repo = SqliteChallengeExperimentRepo(db)
    exp = await exp_repo.create(ch["id"], "No scroll", "Focus rises", "week")
    await exp_repo.start(exp["id"], today)
    await exp_repo.upsert_entry(exp["id"], ch["id"], today, "STARTED", "signal")

    response = await client.post("/challenge/today/holiday", data={"reason": "travel"})

    assert response.status_code == 200
    active = await SqliteChallengeRepo(db).get_active()
    assert active["days_elapsed"] == 0
    assert active["days_remaining"] == 90
    assert "Holiday marked" in response.text
    assert "Next challenge day" in response.text
    assert await SqliteChallengeHolidayRepo(db).dates_for_challenge(ch["id"]) == {today}
    entry_count = await (await db.execute("SELECT COUNT(*) FROM challenge_entries")).fetchone()
    exp_entry_count = await (await db.execute("SELECT COUNT(*) FROM challenge_experiment_entries")).fetchone()
    assert entry_count[0] == 0
    assert exp_entry_count[0] == 0
    updated = await exp_repo.get_by_id(exp["id"])
    assert updated["ends_at"] == (today_local() + timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_holidays_do_not_break_anchor_reset_window(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    ch_repo = SqliteChallengeRepo(db)
    task_repo = SqliteChallengeTaskRepo(db)
    ch = await ch_repo.get_active()
    start_date = (today_local() - timedelta(days=4)).isoformat()
    await db.execute("UPDATE challenges SET start_date = ? WHERE id = ?", (start_date, ch["id"]))
    await db.commit()
    [task] = await task_repo.get_by_challenge(ch["id"])

    for _ in range(2):
        await client.post(
            f"/challenge/today/entry/{task['id']}",
            data={"state": "NOT_DONE"},
        )
        sealed = await client.post("/challenge/today/seal")
        assert sealed.status_code == 200
        await client.post("/challenge/today/holiday", data={"reason": "rest"})

    await client.post(
        f"/challenge/today/entry/{task['id']}",
        data={"state": "NOT_DONE"},
    )
    reset = await client.post("/challenge/today/seal")

    assert reset.status_code == 200
    assert "era ends" in reset.text.lower()
    active = await ch_repo.get_active()
    assert active is not None
    assert active["start_date"] == (today_local() + timedelta(days=1)).isoformat()


# ── SqliteChallengeEraRepo ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_era_create_and_get_all(db):
    era_repo = SqliteChallengeEraRepo(db)
    era = await era_repo.create(
        "Era of Sovereign Awakening", "2026-01-01", "2026-01-15",
        15, 4, "hard", None, "The era fell.",
    )
    assert era["era_name"] == "Era of Sovereign Awakening"
    assert era["reset_cause"] == "hard"

    all_eras = await era_repo.get_all()
    assert len(all_eras) == 1
    assert all_eras[0]["id"] == era["id"]


@pytest.mark.asyncio
async def test_era_used_names(db):
    era_repo = SqliteChallengeEraRepo(db)
    await era_repo.create("Era A", "2026-01-01", "2026-01-10", 10, 0, "forfeit", None, "")
    await era_repo.create("Era B", "2026-01-11", "2026-01-20", 10, 0, "forfeit", None, "")
    names = await era_repo.used_names()
    assert names == {"Era A", "Era B"}


# ── SqliteChallengeExperimentRepo ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_experiment_create_start_entry_and_judge(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")

    exp = await exp_repo.create(ch["id"], "No-scroll morning", "Focus should rise", "week")
    assert exp["status"] == "draft"
    assert exp["timeframe"] == "week"

    started = await exp_repo.start(exp["id"], today)
    assert started["status"] == "running"
    assert started["started_at"] == today
    assert started["ends_at"] is not None

    entry = await exp_repo.upsert_entry(
        exp["id"], ch["id"], today, "COMPLETED_SATISFACTORY", "clean signal",
    )
    assert entry["state"] == "COMPLETED_SATISFACTORY"
    assert entry["notes"] == "clean signal"

    judged = await exp_repo.judge(exp["id"], "success", "worked", "keep it")
    assert judged["status"] == "judged"
    assert judged["verdict"] == "success"
    assert judged["observation_notes"] == "worked"
    assert judged["conclusion_notes"] == "keep it"


@pytest.mark.asyncio
async def test_experiment_entry_allows_notes_before_rating(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")
    exp = await exp_repo.create(ch["id"], "No-scroll morning", "Focus should rise", "week")

    partial = await exp_repo.upsert_entry(exp["id"], ch["id"], today, None, "felt noisy")
    assert partial["state"] is None
    assert partial["notes"] == "felt noisy"

    rated = await exp_repo.upsert_entry(exp["id"], ch["id"], today, "STARTED", "felt noisy")
    assert rated["state"] == "STARTED"
    assert rated["notes"] == "felt noisy"


@pytest.mark.asyncio
async def test_experiment_abandon_frees_running_slot_and_trash_removes_draft(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")

    running = await exp_repo.create(ch["id"], "Running Action", "Motive", "week")
    await exp_repo.start(running["id"], today)
    abandoned = await exp_repo.abandon(running["id"])
    assert abandoned["status"] == "abandoned"
    assert await exp_repo.running_count() == 0

    draft = await exp_repo.create(ch["id"], "Draft Action", "Motive", "day")
    assert await exp_repo.trash_draft(draft["id"])
    assert await exp_repo.get_by_id(draft["id"]) is None


@pytest.mark.asyncio
async def test_experiment_fixed_duration_math(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    ch = await ch_repo.create("Era X", "2026-04-01", "R")

    expected = {
        "day": "2026-04-01",
        "weekend": "2026-04-02",
        "week": "2026-04-07",
        "month": "2026-04-30",
    }
    for timeframe, ends_at in expected.items():
        exp = await exp_repo.create(ch["id"], f"Action {timeframe}", "Motive", timeframe)
        started = await exp_repo.start(exp["id"], "2026-04-01")
        assert started["ends_at"] == ends_at
        await exp_repo.judge(exp["id"], "success", None, None)


@pytest.mark.asyncio
async def test_experiment_running_limit_blocks_fourth(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    today = today_local().isoformat()
    ch = await ch_repo.create("Era X", today, "R")

    experiments = [
        await exp_repo.create(ch["id"], f"Action {idx}", "Motive", "day")
        for idx in range(4)
    ]
    for exp in experiments[:3]:
        assert await exp_repo.start(exp["id"], today) is not None
    assert await exp_repo.running_count() == 3
    assert await exp_repo.start(experiments[3]["id"], today) is None


# ── HTTP routes ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_challenge_index_redirects_to_setup_when_no_active(client):
    r = await client.get("/challenge", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"].endswith("/challenge/setup")


@pytest.mark.asyncio
async def test_challenge_setup_page_renders(client):
    r = await client.get("/challenge/setup")
    assert r.status_code == 200
    assert "Anchors" in r.text
    assert "Improvers" in r.text
    assert "Enrichers" in r.text


@pytest.mark.asyncio
async def test_challenge_setup_rejects_no_anchors(client):
    r = await client.post(
        "/challenge/setup",
        data={"improver[]": "Read"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"].endswith("/challenge/setup")


@pytest.mark.asyncio
async def test_challenge_setup_creates_challenge(client):
    r = await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run", "improver[]": "Read"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"].endswith("/challenge/today")


@pytest.mark.asyncio
async def test_challenge_today_renders(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    r = await client.get("/challenge/today")
    assert r.status_code == 200
    assert "Morning run" in r.text


@pytest.mark.asyncio
async def test_challenge_today_redirects_to_setup_when_no_active(client):
    r = await client.get("/challenge/today", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/challenge/setup" in r.headers["location"]


@pytest.mark.asyncio
async def test_challenge_entry_update(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    today_page = await client.get("/challenge/today")
    assert today_page.status_code == 200

    import re
    task_id_match = re.search(r'/challenge/today/entry/([a-f0-9]+)', today_page.text)
    assert task_id_match, "No entry endpoint found in today page"
    task_id = task_id_match.group(1)

    r = await client.post(
        f"/challenge/today/entry/{task_id}",
        data={"state": "COMPLETED_SATISFACTORY"},
    )
    assert r.status_code == 200
    assert "COMPLETED_SATISFACTORY" in r.text or "✓" in r.text


@pytest.mark.asyncio
async def test_challenge_entry_rejects_invalid_state(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    today_page = await client.get("/challenge/today")
    import re
    task_id = re.search(r'/challenge/today/entry/([a-f0-9]+)', today_page.text).group(1)

    r = await client.post(
        f"/challenge/today/entry/{task_id}",
        data={"state": "BOGUS_STATE"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_challenge_entry_unknown_task_404(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    r = await client.post(
        "/challenge/today/entry/deadbeef",
        data={"state": "COMPLETED_SATISFACTORY"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_challenge_experiments_page_create_start_judge_flow(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )

    page = await client.get("/challenge/experiments")
    assert page.status_code == 200
    assert "Protocol Action" in page.text

    created = await client.post(
        "/challenge/experiments",
        data={
            "action": "No-scroll morning",
            "motivation": "Focus should rise",
            "timeframe": "week",
        },
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)

    page = await client.get("/challenge/experiments")
    assert "No-scroll morning" in page.text
    assert "Protocol Draft" in page.text

    import re
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    started = await client.post(
        f"/challenge/experiments/{exp_id}/start",
        headers={"referer": "http://test/challenge/experiments"},
        follow_redirects=False,
    )
    assert started.status_code in (302, 303)

    judged = await client.post(
        f"/challenge/experiments/{exp_id}/judge",
        data={
            "verdict": "partial_success",
            "observation_notes": "good signal",
            "conclusion_notes": "keep smaller",
        },
        follow_redirects=False,
    )
    assert judged.status_code in (302, 303)

    page = await client.get("/challenge/experiments")
    assert "Partial Discovery" in page.text
    assert "good signal" in page.text


@pytest.mark.asyncio
async def test_challenge_experiment_trash_and_abandon_routes(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    await client.post(
        "/challenge/experiments",
        data={"action": "Draft trial", "motivation": "Maybe useful", "timeframe": "day"},
    )
    page = await client.get("/challenge/experiments")
    import re
    draft_id = re.search(r"/challenge/experiments/([a-f0-9]+)/trash", page.text).group(1)
    trashed = await client.post(
        f"/challenge/experiments/{draft_id}/trash",
        follow_redirects=False,
    )
    assert trashed.status_code in (302, 303)
    page = await client.get("/challenge/experiments")
    assert "Draft trial" not in page.text

    await client.post(
        "/challenge/experiments",
        data={"action": "Running trial", "motivation": "Maybe useful", "timeframe": "day"},
    )
    page = await client.get("/challenge/experiments")
    running_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{running_id}/start")
    abandoned = await client.post(
        f"/challenge/experiments/{running_id}/abandon",
        follow_redirects=False,
    )
    assert abandoned.status_code in (302, 303)
    page = await client.get("/challenge/experiments")
    assert "Abandoned Trial" in page.text


@pytest.mark.asyncio
async def test_challenge_experiment_rejects_invalid_inputs(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    r = await client.post(
        "/challenge/experiments",
        data={"action": "A", "motivation": "B", "timeframe": "year"},
    )
    assert r.status_code == 400

    r = await client.post("/challenge/experiments/deadbeef/judge", data={"verdict": "maybe"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_running_experiment_appears_on_today_and_accepts_daily_entry(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    await client.post(
        "/challenge/experiments",
        data={
            "action": "No-scroll morning",
            "motivation": "Focus should rise",
            "timeframe": "day",
        },
    )
    page = await client.get("/challenge/experiments")
    import re
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    today_page = await client.get("/challenge/today")
    assert "Tiny Experiments" in today_page.text
    assert "No-scroll morning" in today_page.text
    assert f"/challenge/experiments/{exp_id}/entry" in today_page.text

    r = await client.post(
        f"/challenge/experiments/{exp_id}/entry",
        data={"state": "PARTIAL", "notes": "noticed the itch"},
    )
    assert r.status_code == 200
    assert "PARTIAL" in r.text or "noticed the itch" in r.text


@pytest.mark.asyncio
async def test_experiment_entries_do_not_gate_day_seal(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    await client.post(
        "/challenge/experiments",
        data={
            "action": "No-scroll morning",
            "motivation": "Focus should rise",
            "timeframe": "week",
        },
    )
    page = await client.get("/challenge/experiments")
    import re
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    today_page = await client.get("/challenge/today")
    task_id = re.search(r"/challenge/today/entry/([a-f0-9]+)", today_page.text).group(1)
    await client.post(
        f"/challenge/today/entry/{task_id}",
        data={"state": "COMPLETED_SATISFACTORY"},
    )
    sealed = await client.post("/challenge/today/seal")
    assert sealed.status_code == 200
    assert "Day 1 sealed" in sealed.text or "sealed" in sealed.text.lower()


@pytest.mark.asyncio
async def test_experiment_stays_linked_to_original_era_after_forfeit(client, db):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    await client.post(
        "/challenge/experiments",
        data={
            "action": "Weekend prototype",
            "motivation": "Validate the premise",
            "timeframe": "weekend",
        },
    )
    page = await client.get("/challenge/experiments")
    import re
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    exp_repo = SqliteChallengeExperimentRepo(db)
    before = await exp_repo.get_by_id(exp_id)
    await client.post("/challenge/forfeit", data={"confirm": "yes", "restart_mode": "same"})

    ch_repo = SqliteChallengeRepo(db)
    active = await ch_repo.get_active()
    after = await exp_repo.get_by_id(exp_id)
    assert after["challenge_id"] == before["challenge_id"]
    assert after["challenge_id"] != active["id"]

    today_page = await client.get("/challenge/today")
    assert "Weekend prototype" in today_page.text


@pytest.mark.asyncio
async def test_challenge_metrics_renders(client, db):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run", "improver[]": "Read"},
    )
    ch = await SqliteChallengeRepo(db).get_active()
    await SqliteChallengeHolidayRepo(db).create(ch["id"], today_local().isoformat(), "travel")

    r = await client.get("/challenge/metrics")
    assert r.status_code == 200
    assert "Day" in r.text
    assert "HOLIDAY CADENCE" in r.text
    assert "projected extension +1d" in r.text


@pytest.mark.asyncio
async def test_challenge_metrics_redirects_without_active(client):
    r = await client.get("/challenge/metrics", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/challenge/setup" in r.headers["location"]


@pytest.mark.asyncio
async def test_challenge_history_renders(client):
    r = await client.get("/challenge/history")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_challenge_forfeit_no_confirm_redirects(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    r = await client.post(
        "/challenge/forfeit",
        data={"confirm": ""},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert "/challenge/today" in r.headers["location"]


@pytest.mark.asyncio
async def test_challenge_forfeit_confirmed_resets_and_starts_same_challenges(client, db):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run", "improver[]": "Read"},
    )
    r = await client.post(
        "/challenge/forfeit",
        data={"confirm": "yes", "restart_mode": "same"},
    )
    assert r.status_code == 200
    # Forfeit cinematic renders
    assert "Relinquish" in r.text or "Forfeit" in r.text or "relinquish" in r.text.lower()

    ch_repo = SqliteChallengeRepo(db)
    task_repo = SqliteChallengeTaskRepo(db)
    active = await ch_repo.get_active()
    assert active is not None
    assert active["start_date"] == (today_local() + timedelta(days=1)).isoformat()
    tasks = await task_repo.get_by_challenge(active["id"])
    assert {t["name"] for t in tasks} == {"Morning run", "Read"}


@pytest.mark.asyncio
async def test_challenge_forfeit_confirmed_can_restart_with_setup(client, db):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run"},
    )
    r = await client.post(
        "/challenge/forfeit",
        data={"confirm": "yes", "restart_mode": "setup"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"].endswith("/challenge/setup")

    ch_repo = SqliteChallengeRepo(db)
    assert await ch_repo.get_active() is None


@pytest.mark.asyncio
async def test_future_start_challenge_rejects_entries_and_experiment_start(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    await client.post(
        "/challenge/forfeit",
        data={"confirm": "yes", "restart_mode": "same"},
    )
    ch = await SqliteChallengeRepo(db).get_active()
    [task] = await SqliteChallengeTaskRepo(db).get_by_challenge(ch["id"])

    entry_response = await client.post(
        f"/challenge/today/entry/{task['id']}",
        data={"state": "COMPLETED_SATISFACTORY"},
    )
    assert entry_response.status_code == 400

    exp_repo = SqliteChallengeExperimentRepo(db)
    exp = await exp_repo.create(ch["id"], "No scroll", "Focus rises", "day")
    start_response = await client.post(f"/challenge/experiments/{exp['id']}/start")
    assert start_response.status_code == 400
