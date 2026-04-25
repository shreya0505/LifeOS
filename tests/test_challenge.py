"""Tests for Hard 90 Challenge — engines, backend repos, and HTTP routes."""

from __future__ import annotations

import pytest

from core.challenge import level_engine, reset_engine
from core.challenge.config import CHALLENGE_LENGTH_DAYS
from core.storage.challenge_backend import (
    SqliteChallengeEntryRepo,
    SqliteChallengeEraRepo,
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
async def test_challenge_metrics_renders(client):
    await client.post(
        "/challenge/setup",
        data={"anchor[]": "Morning run", "improver[]": "Read"},
    )
    r = await client.get("/challenge/metrics")
    assert r.status_code == 200
    assert "Day" in r.text


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
