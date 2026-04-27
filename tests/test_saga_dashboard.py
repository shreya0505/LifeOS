"""Tests for the Saga Mood Meter dashboard payload."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.config import USER_TZ
from core.saga import saga_dashboard


def _day(offset: int = 0) -> str:
    return (datetime.now(USER_TZ).date() + timedelta(days=offset)).isoformat()


async def _insert_saga(
    db,
    entry_id: str,
    day: str,
    energy: int = 3,
    pleasantness: int = -2,
    word: str = "frustrated",
    hour: int = 9,
):
    quadrant = "yellow" if energy > 0 and pleasantness > 0 else "red" if energy > 0 else "green" if pleasantness > 0 else "blue"
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entry_id, f"{day}T{hour:02d}:00:00+05:30", day, energy, pleasantness, quadrant, word),
    )


async def _insert_quest(db, quest_id: str, day: str, frog: int = 0, priority: int = 1):
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, priority, created_at, completed_at, workspace_id) "
        "VALUES (?, ?, 'done', ?, ?, ?, ?, 'work')",
        (quest_id, f"Quest {quest_id}", frog, priority, f"{day}T08:00:00+05:30", f"{day}T10:00:00+05:30"),
    )


async def _challenge_setup(db):
    today = _day()
    await db.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('dash-ch', 'Dashboard Era', ?, 'Bright')",
        (today,),
    )
    for bucket in ("anchor", "improver", "enricher"):
        await db.execute(
            "INSERT INTO challenge_tasks (id, challenge_id, name, bucket) "
            "VALUES (?, 'dash-ch', ?, ?)",
            (f"task-{bucket}", bucket.title(), bucket),
        )


async def _insert_challenge(db, entry_id: str, day: str, bucket: str = "anchor", state: str = "COMPLETED_SATISFACTORY"):
    await db.execute(
        "INSERT INTO challenge_entries "
        "(id, task_id, challenge_id, log_date, state, created_at) "
        "VALUES (?, ?, 'dash-ch', ?, ?, ?)",
        (entry_id, f"task-{bucket}", day, state, f"{day}T20:00:00+05:30"),
    )


@pytest.mark.asyncio
async def test_saga_dashboard_shape_and_mood_meter_metrics(db):
    dashboard = await saga_dashboard(db, 7)

    expected = {
        "window_days",
        "headline",
        "recent_arc",
        "today_card",
        "timeseries",
        "quadrant_stream",
        "heatmap",
        "challenge_bucket_series",
        "risk_signals",
        "scatter",
        "archetype_distribution",
        "streaks",
        "best_day",
        "mood_grid",
        "meta_analysis",
        "meta_summary",
    }
    assert expected.issubset(dashboard.keys())
    assert len(dashboard["mood_grid"]) == 100
    assert set(dashboard["timeseries"].keys()) >= {"mood_load", "avg_energy", "avg_pleasantness"}
    assert [item["quadrant"] for item in dashboard["quadrant_stream"]["series"]] == ["yellow", "red", "green", "blue"]
    assert set(dashboard["meta_analysis"].keys()) >= {"emotion_load", "recovery", "mood_map"}
    assert all(len(kpi["spark"]) == 7 for kpi in dashboard["headline"]["kpis"].values())


@pytest.mark.asyncio
async def test_saga_dashboard_windows_match_timeseries_length(db):
    for window in (7, 35, 90, 365):
        dashboard = await saga_dashboard(db, window)
        assert len(dashboard["timeseries"]["dates"]) == window


@pytest.mark.asyncio
async def test_saga_metrics_route_window_fallback_and_modes(client):
    full = await client.get("/saga/metrics?window=999")
    assert full.status_code == 200
    assert "<!DOCTYPE html>" in full.text
    assert "The Field Report" in full.text
    assert "Mood Atlas" in full.text

    fragment = await client.get("/saga/metrics?window=7", headers={"HX-Request": "true"})
    assert fragment.status_code == 200
    assert "<!DOCTYPE html>" not in fragment.text
    assert 'class="saga-dashboard"' in fragment.text


@pytest.mark.asyncio
async def test_saga_dashboard_empty_db_is_complete(db):
    dashboard = await saga_dashboard(db, 35)

    assert dashboard["headline"]["archetype"] == "No Signal"
    assert dashboard["total_entries"] == 0
    assert dashboard["meta_analysis"]["capture"]["coverage_pct"] == 0
    assert dashboard["meta_summary"]["confidence"] == "low"


@pytest.mark.asyncio
async def test_saga_dashboard_streaks(db):
    await _challenge_setup(db)
    for offset in range(-4, 1):
        day = _day(offset)
        await _insert_saga(db, f"s{offset}", day, -2, 3, "calm")
        await _insert_quest(db, f"q{offset}", day, frog=1 if offset >= -2 else 0)
        await _insert_challenge(db, f"c{offset}", day, "anchor", "COMPLETED_SATISFACTORY")
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    assert dashboard["streaks"]["capture"]["current"] == 5
    assert dashboard["streaks"]["challenge"]["current"] == 5
    assert dashboard["streaks"]["frog"]["current"] == 3
    assert dashboard["meta_analysis"]["capture"]["entries_per_active_day"] == 1


@pytest.mark.asyncio
async def test_saga_dashboard_risk_volatility_rising(db):
    for idx, offset in enumerate(range(-13, 1)):
        day = _day(offset)
        if idx < 7:
            await _insert_saga(db, f"calm-a-{idx}", day, -2, 3, "calm", hour=9)
            await _insert_saga(db, f"calm-b-{idx}", day, -2, 3, "calm", hour=18)
        else:
            await _insert_saga(db, f"storm-a-{idx}", day, 5, -5, "enraged", hour=9)
            await _insert_saga(db, f"storm-b-{idx}", day, -5, -5, "despondent", hour=18)
    await db.commit()

    dashboard = await saga_dashboard(db, 35)

    assert any(signal["headline"] == "Volatility rising" for signal in dashboard["risk_signals"])


@pytest.mark.asyncio
async def test_saga_dashboard_quadrant_stream_and_mood_grid(db):
    today = _day()
    await _insert_saga(db, "red", today, 5, -5, "enraged", hour=9)
    await _insert_saga(db, "yellow", today, 5, 5, "ecstatic", hour=10)
    await _insert_saga(db, "green", today, -5, 5, "blissful", hour=11)
    await _insert_saga(db, "blue", today, -5, -5, "despondent", hour=12)
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    stream = {item["quadrant"]: item["data"][-1] for item in dashboard["quadrant_stream"]["series"]}
    assert stream == {"yellow": 1, "red": 1, "green": 1, "blue": 1}
    grid = {(cell["energy"], cell["pleasantness"]): cell for cell in dashboard["mood_grid"]}
    assert grid[(5, -5)]["quadrant"] == "red"
    assert grid[(5, 5)]["quadrant"] == "yellow"
    assert grid[(-5, 5)]["quadrant"] == "green"
    assert grid[(-5, -5)]["quadrant"] == "blue"
    assert dashboard["total_entries"] == 4
    assert dashboard["total_mood_mentions"] == 4
