"""Focused tests for Hard 90 tiny experiment verdict capture."""

from __future__ import annotations

from datetime import timedelta
import re

import pytest

from core.challenge import metrics_engine
from core.storage.challenge_backend import (
    SqliteChallengeExperimentRepo,
    SqliteChallengeRepo,
)
from core.utils import today_local


@pytest.mark.parametrize(
    ("entries", "duration_days", "expected"),
    [
        ([{"state": "COMPLETED_SATISFACTORY"}], 4, "failed_premise"),
        (
            [
                {"state": "COMPLETED_SATISFACTORY"},
                {"state": "COMPLETED_SATISFACTORY"},
                {"state": "COMPLETED_SATISFACTORY"},
                {"state": "COMPLETED_UNSATISFACTORY"},
            ],
            4,
            "success",
        ),
        (
            [
                {"state": "PARTIAL"},
                {"state": "STARTED"},
                {"state": "PARTIAL"},
            ],
            3,
            "partial_success",
        ),
        (
            [
                {"state": "NOT_DONE"},
                {"state": "STARTED"},
            ],
            2,
            "failed_process",
        ),
    ],
)
def test_suggest_verdict_covers_each_branch(entries, duration_days, expected):
    assert metrics_engine.suggest_verdict(entries, duration_days) == expected


@pytest.mark.asyncio
async def test_overdue_experiment_renders_pending_verdict_ui_and_today_banner(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    await client.post(
        "/challenge/experiments",
        data={
            "action": "No-scroll morning",
            "motivation": "Focus should rise",
            "timeframe": "day",
        },
    )
    page = await client.get("/challenge/experiments")
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    challenge = await SqliteChallengeRepo(db).get_active()
    exp_repo = SqliteChallengeExperimentRepo(db)
    yesterday = (today_local() - timedelta(days=1)).isoformat()
    await exp_repo.upsert_entry(
        exp_id,
        challenge["id"],
        yesterday,
        "COMPLETED_SATISFACTORY",
        "Quiet morning felt materially better.",
    )
    await db.execute(
        "UPDATE challenge_experiments SET started_at = ?, ends_at = ? WHERE id = ?",
        (yesterday, yesterday, exp_id),
    )
    await db.commit()

    experiments_page = await client.get("/challenge/experiments")
    assert "Verdict Pending" in experiments_page.text
    assert "Record Verdict" in experiments_page.text
    assert "Quiet morning felt materially better." in experiments_page.text
    assert 'value="success" selected' in experiments_page.text
    assert f"/challenge/experiments/{exp_id}/extend" in experiments_page.text

    today_page = await client.get("/challenge/today")
    assert "VERDICT PENDING" in today_page.text
    assert "/challenge/experiments" in today_page.text


@pytest.mark.asyncio
async def test_abandon_experiment_persists_reason_as_conclusion(client):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    await client.post(
        "/challenge/experiments",
        data={
            "action": "Evening shutdown",
            "motivation": "Sleep should improve",
            "timeframe": "day",
        },
    )
    page = await client.get("/challenge/experiments")
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    archived = await client.post(
        f"/challenge/experiments/{exp_id}/abandon",
        data={"reason": "Signal was confounded by travel."},
        follow_redirects=False,
    )
    assert archived.status_code in (302, 303)

    page = await client.get("/challenge/experiments")
    assert "Abandoned Trial" in page.text
    assert "[abandoned] Signal was confounded by travel." in page.text


@pytest.mark.asyncio
async def test_extend_experiment_moves_end_date_forward(client, db):
    await client.post("/challenge/setup", data={"anchor[]": "Morning run"})
    await client.post(
        "/challenge/experiments",
        data={
            "action": "Weekend prototype",
            "motivation": "Validate the premise",
            "timeframe": "weekend",
        },
    )
    page = await client.get("/challenge/experiments")
    exp_id = re.search(r"/challenge/experiments/([a-f0-9]+)/start", page.text).group(1)
    await client.post(f"/challenge/experiments/{exp_id}/start")

    old_end = (today_local() - timedelta(days=1)).isoformat()
    await db.execute(
        "UPDATE challenge_experiments SET started_at = ?, ends_at = ? WHERE id = ?",
        (old_end, old_end, exp_id),
    )
    await db.commit()

    extended = await client.post(
        f"/challenge/experiments/{exp_id}/extend",
        follow_redirects=False,
    )
    assert extended.status_code in (302, 303)

    exp = await SqliteChallengeExperimentRepo(db).get_by_id(exp_id)
    expected_end = (today_local() + timedelta(days=1)).isoformat()
    assert exp["ends_at"] == expected_end


@pytest.mark.asyncio
async def test_overdue_running_experiments_do_not_block_starting_new_trial(db):
    ch_repo = SqliteChallengeRepo(db)
    exp_repo = SqliteChallengeExperimentRepo(db)
    today = today_local().isoformat()
    old_day = (today_local() - timedelta(days=2)).isoformat()
    challenge = await ch_repo.create("Era X", today, "R")

    experiments = [
        await exp_repo.create(challenge["id"], f"Past trial {idx}", "Motive", "day")
        for idx in range(3)
    ]
    for exp in experiments:
        assert await exp_repo.start(exp["id"], old_day) is not None

    new_exp = await exp_repo.create(challenge["id"], "Fresh trial", "Motive", "day")
    assert await exp_repo.start(new_exp["id"], today) is not None
