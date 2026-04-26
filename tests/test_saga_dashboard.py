"""Tests for the Saga behavioral dashboard payload."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.config import USER_TZ
from core.saga import saga_dashboard


def _day(offset: int = 0) -> str:
    return (datetime.now(USER_TZ).date() + timedelta(days=offset)).isoformat()


async def _insert_saga(db, entry_id: str, day: str, family: str = "joy", label: str = "joy", intensity: int = 5, hour: int = 9, **extra):
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            f"{day}T{hour:02d}:00:00+05:30",
            day,
            family,
            label,
            intensity,
            extra.get("secondary_family"),
            extra.get("secondary_label"),
            extra.get("dyad_label"),
            extra.get("dyad_type"),
        ),
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
async def test_saga_dashboard_shape_and_meta_analysis(db):
    dashboard = await saga_dashboard(db, 7)

    expected = {
        "window_days",
        "headline",
        "recent_arc",
        "today_card",
        "timeseries",
        "family_stream",
        "heatmap",
        "challenge_bucket_series",
        "risk_signals",
        "scatter",
        "archetype_distribution",
        "streaks",
        "best_day",
        "meta_analysis",
        "meta_summary",
    }
    assert expected.issubset(dashboard.keys())
    assert set(dashboard["meta_analysis"].keys()) >= {
        "capture",
        "emotion_load",
        "output_coupling",
        "challenge_integrity",
        "alignment",
        "recovery",
        "rhythm",
        "archetypes",
        "dyads",
        "summary_flags",
    }
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
    assert "The Field Report · 7d" in full.text

    fragment = await client.get("/saga/metrics?window=7", headers={"HX-Request": "true"})
    assert fragment.status_code == 200
    assert "<!DOCTYPE html>" not in fragment.text
    assert 'class="saga-dashboard"' in fragment.text
    assert "The Field Report · 7d" in fragment.text


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
        await _insert_saga(db, f"s{offset}", day, "joy", "joy", 5)
        await _insert_quest(db, f"q{offset}", day, frog=1 if offset >= -2 else 0)
        await _insert_challenge(db, f"c{offset}", day, "anchor", "COMPLETED_SATISFACTORY")
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    assert dashboard["streaks"]["capture"]["current"] == 5
    assert dashboard["streaks"]["capture"]["best"] == 5
    assert dashboard["streaks"]["challenge"]["current"] == 5
    assert dashboard["streaks"]["frog"]["current"] == 3
    assert dashboard["meta_analysis"]["capture"]["entries_per_active_day"] == 1


@pytest.mark.asyncio
async def test_saga_dashboard_risk_volatility_rising(db):
    for idx, offset in enumerate(range(-13, 1)):
        day = _day(offset)
        if idx < 7:
            await _insert_saga(db, f"calm-a-{idx}", day, "fear", "fear", 4, hour=9)
            await _insert_saga(db, f"calm-b-{idx}", day, "fear", "fear", 4, hour=18)
        else:
            await _insert_saga(db, f"storm-a-{idx}", day, "fear", "fear", 1, hour=9)
            await _insert_saga(db, f"storm-b-{idx}", day, "fear", "terror", 10, hour=18)
    await db.commit()

    dashboard = await saga_dashboard(db, 35)

    assert any(signal["headline"] == "Volatility rising" for signal in dashboard["risk_signals"])


@pytest.mark.asyncio
async def test_saga_dashboard_risk_bucket_decline(db):
    await _challenge_setup(db)
    for idx, offset in enumerate(range(-13, 1)):
        day = _day(offset)
        state = "COMPLETED_SATISFACTORY" if idx < 7 else "PARTIAL"
        await _insert_challenge(db, f"bucket-{idx}", day, "anchor", state)
    await db.commit()

    dashboard = await saga_dashboard(db, 35)

    assert any(signal["kind"] == "bucket_decline" for signal in dashboard["risk_signals"])
    assert "anchor" in dashboard["meta_analysis"]["challenge_integrity"]["bucket_decline_flags"]


@pytest.mark.asyncio
async def test_saga_dashboard_capture_gap_risk(db):
    await _insert_saga(db, "gap-old", _day(-6), "sadness", "sadness", 4)
    await _insert_saga(db, "gap-now", _day(), "joy", "joy", 4)
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    assert dashboard["meta_analysis"]["capture"]["longest_gap"] >= 3
    assert any(signal["kind"] == "capture_gap" for signal in dashboard["risk_signals"])


@pytest.mark.asyncio
async def test_saga_dashboard_dyads(db):
    today = _day()
    await _insert_saga(
        db,
        "dyad-love",
        today,
        "joy",
        "joy",
        6,
        secondary_family="trust",
        secondary_label="trust",
        dyad_label="love",
        dyad_type="primary",
    )
    await _insert_saga(
        db,
        "dyad-opposite",
        today,
        "joy",
        "serenity",
        4,
        secondary_family="sadness",
        secondary_label="pensiveness",
        dyad_type="opposite",
    )
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    assert dashboard["opposite_count"] == 1
    assert dashboard["meta_analysis"]["dyads"]["dyad_count"] == 2
    assert dashboard["top_dyads"][0]["count"] >= 1


@pytest.mark.asyncio
async def test_saga_dashboard_counts_secondary_emotions_in_family_metrics(db):
    today = _day()
    await _insert_saga(
        db,
        "multi-emotion",
        today,
        "joy",
        "joy",
        6,
        secondary_family="trust",
        secondary_label="trust",
        dyad_label="love",
        dyad_type="primary",
    )
    await db.commit()

    dashboard = await saga_dashboard(db, 7)

    stream = {item["family"]: item["data"][-1] for item in dashboard["family_stream"]["series"]}
    distribution = {item["family"]: item["count"] for item in dashboard["distribution"]}
    top_labels = {item["label"]: item["count"] for item in dashboard["top_labels"]}
    wheel_counts = {
        (cell["family"], cell["label"]): cell["count"]
        for cell in dashboard["wheel"]
    }
    today_stack = {
        (item["family"], item["label"])
        for item in dashboard["today_card"]["emotion_stack"]
    }

    assert stream["joy"] == 1
    assert stream["trust"] == 1
    assert distribution["joy"] == 1
    assert distribution["trust"] == 1
    assert top_labels["joy"] == 1
    assert top_labels["trust"] == 1
    assert wheel_counts[("joy", "joy")] == 1
    assert wheel_counts[("trust", "trust")] == 1
    assert ("joy", "joy") in today_stack
    assert ("trust", "trust") in today_stack
    assert dashboard["total_entries"] == 1
    assert dashboard["total_emotion_mentions"] == 2
