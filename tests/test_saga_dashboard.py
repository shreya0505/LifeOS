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


async def _insert_pomo(db, session_id: str, day: str, quest_id: str = "q-focus", pomos: int = 3, interruptions: int = 0):
    await db.execute(
        "INSERT INTO pomo_sessions "
        "(id, quest_id, quest_title, started_at, ended_at, actual_pomos, status, streak_peak, total_interruptions, workspace_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, 'work')",
        (
            session_id,
            quest_id,
            "Focused work",
            f"{day}T09:00:00+05:30",
            f"{day}T11:00:00+05:30",
            pomos,
            pomos,
            interruptions,
        ),
    )
    for lap in range(pomos):
        await db.execute(
            "INSERT INTO pomo_segments "
            "(session_id, type, lap, cycle, completed, interruptions, started_at, ended_at, workspace_id) "
            "VALUES (?, 'work', ?, 1, 1, ?, ?, ?, 'work')",
            (
                session_id,
                lap,
                interruptions if lap == 0 else 0,
                f"{day}T{9 + lap:02d}:00:00+05:30",
                f"{day}T{9 + lap:02d}:25:00+05:30",
            ),
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
        "narrative",
        "grimoire",
        "scatter",
        "archetype_distribution",
        "streaks",
        "best_day",
        "mood_grid",
        "meta_analysis",
        "meta_summary",
    }
    assert expected.issubset(dashboard.keys())
    assert len(dashboard["mood_grid"]) == 196
    assert set(dashboard["timeseries"].keys()) >= {"mood_load", "avg_energy", "avg_pleasantness"}
    assert [item["quadrant"] for item in dashboard["quadrant_stream"]["series"]] == ["yellow", "red", "green", "blue"]
    assert [item["label"] for item in dashboard["quadrant_stream"]["series"]] == ["Radiance", "Hellfire", "Sanctuary", "Abyss"]
    assert set(dashboard["meta_analysis"].keys()) >= {"emotion_load", "recovery", "mood_map"}
    assert all(len(kpi["spark"]) == 7 for kpi in dashboard["headline"]["kpis"].values())
    assert dashboard["narrative"]["grain"] == "week"
    assert "state_sentence" in dashboard["narrative"]
    assert isinstance(dashboard["narrative"]["signals"], list)
    assert set(dashboard["grimoire"].keys()) >= {
        "verdict",
        "pillars",
        "recommendations",
        "tendencies",
        "charts",
        "missing_data",
    }
    assert [pillar["key"] for pillar in dashboard["grimoire"]["pillars"]] == [
        "daily_execution",
        "long_game",
        "evolution",
        "emotional_climate",
    ]
    assert set(dashboard["grimoire"]["charts"].keys()) >= {
        "timeline_heartbeat",
        "relationships",
        "correlation_matrix",
    }
    assert [item["key"] for item in dashboard["grimoire"]["charts"]["relationships"]] == [
        "mood_daily",
        "mood_long",
        "curiosity_long",
    ]
    for relationship in dashboard["grimoire"]["charts"]["relationships"][:2]:
        assert relationship["x_min"] == -7
        assert relationship["x_max"] == 7
    emotional = next(pillar for pillar in dashboard["grimoire"]["pillars"] if pillar["key"] == "emotional_climate")
    component_labels = [component["label"] for component in emotional["explainer"]["components"]]
    assert component_labels == ["Adaptive valence", "Low acute load", "Stability", "Pleasant access"]
    correlation = dashboard["grimoire"]["charts"]["correlation_matrix"]
    assert correlation["series"]
    first_cell = correlation["series"][0]["data"][0]
    assert set(first_cell.keys()) >= {"metric_x", "metric_y", "y", "paired_days"}


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
    assert "How am I doing this week" in full.text
    assert "What should I improve?" in full.text
    assert "What are my trends or tendencies?" in full.text
    assert "chart-timeline-heartbeat" in full.text
    assert "chart-relationship-truth" in full.text
    assert "chart-correlation-map" in full.text
    assert "How to read:" in full.text
    assert "Strong positive" in full.text
    assert "Curved pattern" in full.text
    assert full.text.count("saga-chart-card saga-grid__span-12") >= 3
    assert "chart-systems-matrix" not in full.text
    assert "chart-focus-quality" not in full.text
    assert "chart-bucket-risk" not in full.text

    fragment = await client.get("/saga/metrics?window=7", headers={"HX-Request": "true"})
    assert fragment.status_code == 200
    assert "<!DOCTYPE html>" not in fragment.text
    assert 'class="saga-dashboard saga-dashboard--grimoire"' in fragment.text

    grain = await client.get("/saga/metrics?grain=quarter", headers={"HX-Request": "true"})
    assert grain.status_code == 200
    assert "How am I doing this quarter" in grain.text
    assert 'id="saga-payload-90"' in grain.text


@pytest.mark.asyncio
async def test_saga_dashboard_empty_db_is_complete(db):
    dashboard = await saga_dashboard(db, 35)

    assert dashboard["headline"]["archetype"] == "No Signal"
    assert dashboard["total_entries"] == 0
    assert dashboard["meta_analysis"]["capture"]["coverage_pct"] == 0
    assert dashboard["meta_summary"]["confidence"] == "low"
    assert any(item["kind"] == "saga" for item in dashboard["grimoire"]["missing_data"])
    assert dashboard["grimoire"]["verdict"]["label"] == "Data Thin"
    heartbeat = dashboard["grimoire"]["charts"]["timeline_heartbeat"]
    assert all(value is None for series in heartbeat["series"] for value in series["data"])


@pytest.mark.asyncio
async def test_grimoire_detects_long_game_neglect_when_output_is_high(db):
    await _challenge_setup(db)
    today = _day()
    await _insert_saga(db, "steady-yellow", today, 4, 4, "joyful")
    for idx in range(4):
        await _insert_quest(db, f"high-output-{idx}", today, frog=1 if idx == 0 else 0, priority=0)
    await _insert_pomo(db, "focus-neglect", today, quest_id="high-output-0", pomos=4)
    await _insert_challenge(db, "miss-anchor", today, "anchor", "NOT_DONE")
    await _insert_challenge(db, "miss-improver", today, "improver", "PARTIAL")
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    assert dashboard["grimoire"]["verdict"]["label"] in {"Long Game Neglect", "Productive Drift"}
    long_game = next(p for p in dashboard["grimoire"]["pillars"] if p["key"] == "long_game")
    daily = next(p for p in dashboard["grimoire"]["pillars"] if p["key"] == "daily_execution")
    assert daily["score"] > long_game["score"]
    assert any("Anchor" in rec["title"] for rec in dashboard["grimoire"]["recommendations"])


@pytest.mark.asyncio
async def test_grimoire_counts_failed_experiment_participation(db):
    today = _day()
    await db.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('exp-ch', 'Experiment Era', ?, 'Bright')",
        (today,),
    )
    await db.execute(
        "INSERT INTO challenge_experiments "
        "(id, challenge_id, action, motivation, timeframe, status, started_at, ends_at, verdict, created_at) "
        "VALUES ('exp-failed', 'exp-ch', 'Test a no-phone morning', 'check energy', 'day', 'judged', ?, ?, 'failed_premise', ?)",
        (today, today, f"{today}T07:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state, notes, created_at) "
        "VALUES ('exp-failed-entry', 'exp-failed', 'exp-ch', ?, 'PARTIAL', 'Premise was wrong but useful.', ?)",
        (today, f"{today}T20:00:00+05:30"),
    )
    await db.commit()

    dashboard = await saga_dashboard(db, 7)
    evolution = next(p for p in dashboard["grimoire"]["pillars"] if p["key"] == "evolution")

    assert evolution["score"] > 0
    assert "1 trial" in evolution["headline"]


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
            await _insert_saga(db, f"storm-a-{idx}", day, 7, -7, "uncontainable", hour=9)
            await _insert_saga(db, f"storm-b-{idx}", day, -7, -7, "obliterated", hour=18)
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
    assert grid[(7, -7)]["quadrant"] == "red"
    assert grid[(7, 7)]["quadrant"] == "yellow"
    assert grid[(-7, 7)]["quadrant"] == "green"
    assert grid[(-7, -7)]["quadrant"] == "blue"
    assert grid[(5, -5)]["quadrant"] == "red"
    assert grid[(5, 5)]["quadrant"] == "yellow"
    assert grid[(-5, 5)]["quadrant"] == "green"
    assert grid[(-5, -5)]["quadrant"] == "blue"
    assert dashboard["total_entries"] == 4
    assert dashboard["total_mood_mentions"] == 4


@pytest.mark.asyncio
async def test_saga_dashboard_pleasant_access_improves_emotional_climate(db):
    yesterday = _day(-1)
    today = _day()
    await _insert_saga(db, "low-grade", yesterday, 3, -2, "nervous", hour=9)
    await db.commit()

    first = await saga_dashboard(db, 7)
    first_emotional = next(p for p in first["grimoire"]["pillars"] if p["key"] == "emotional_climate")
    first_pleasant_access = next(
        component for component in first_emotional["explainer"]["components"]
        if component["label"] == "Pleasant access"
    )

    await _insert_saga(db, "relief", today, -2, 3, "relieved", hour=13)
    await db.commit()

    second = await saga_dashboard(db, 7)
    second_emotional = next(p for p in second["grimoire"]["pillars"] if p["key"] == "emotional_climate")
    pleasant_access = next(
        component for component in second_emotional["explainer"]["components"]
        if component["label"] == "Pleasant access"
    )

    assert second_emotional["score"] > first_emotional["score"]
    assert pleasant_access["score"] > first_pleasant_access["score"]
