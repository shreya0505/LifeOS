"""Tests for Phase 3 web routes: chronicle, trophies, dashboard."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
import pytest_asyncio

from core import clock
from core.trophy_compute import compute_trophies


# ── Helpers ──────────────────────────────────────────────────────────────


async def _add_quest(client, title: str = "Test Quest", activate: bool = True) -> str:
    """Add a quest and optionally move it to active. Returns quest_id."""
    r = await client.post("/quests", data={"title": title})
    match = re.search(r'data-id="([^"]+)"', r.text)
    qid = match.group(1)
    if activate:
        await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    return qid


async def _complete_pomo(client, quest_id: str, charge: str = "Work", deed: str = "Done"):
    """Run a full pomo cycle: start -> charge -> complete-early -> deed -> end."""
    import web.pomos.engine as engine_mod
    import web.db as db_mod

    await client.post("/pomos/start", data={"quest_id": quest_id})
    await client.post("/pomos/charge", data={"charge": charge})
    await client.post("/pomos/complete-early")
    await client.post("/pomos/deed", data={"deed": deed, "forge_type": ""})
    await client.post("/pomos/break", data={"choice": "end"})


@pytest.fixture(autouse=True)
def _reset_pomo_engine(tmp_path, monkeypatch):
    """Reset the pomo engine singleton and point at test DB."""
    import web.pomos.engine as engine_mod
    import web.db as db_mod

    engine_mod._engine = None
    engine_mod._sync_repo = None
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    yield
    if engine_mod._sync_repo is not None:
        engine_mod._sync_repo.close()
    engine_mod._engine = None
    engine_mod._sync_repo = None


# ── Chronicle ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chronicle_empty(client):
    r = await client.get("/chronicle")
    assert r.status_code == 200
    assert "chronicle-panel" in r.text
    assert "heatmap" in r.text
    assert "No forges today" in r.text


@pytest.mark.asyncio
async def test_chronicle_with_pomo(client):
    qid = await _add_quest(client)
    await _complete_pomo(client, qid, charge="Fix the bug", deed="Bug fixed")

    r = await client.get("/chronicle")
    assert r.status_code == 200
    assert "Fix the bug" in r.text
    assert "Bug fixed" in r.text
    assert "tl-entry" in r.text


@pytest.mark.asyncio
async def test_chronicle_heatmap_has_cells(client):
    r = await client.get("/chronicle")
    assert r.status_code == 200
    assert "heatmap__cell" in r.text
    # Should have legend swatches
    assert "heatmap__legend" in r.text


# ── Trophies ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trophies_empty(client):
    r = await client.get("/trophies")
    assert r.status_code == 200
    assert "trophy-panel" in r.text
    # All should be locked
    assert "Locked" in r.text


@pytest.mark.asyncio
async def test_trophies_with_pomo(client):
    qid = await _add_quest(client)
    await _complete_pomo(client, qid, charge="Deep work", deed="Work done")

    r = await client.get("/trophies")
    assert r.status_code == 200
    assert "valor-card" in r.text
    # Forge Master should have at least bronze (1 pomo)
    assert "Forge Master" in r.text


@pytest.mark.asyncio
async def test_trophies_shows_all_seven(client):
    r = await client.get("/trophies")
    assert r.status_code == 200
    for name in ["Frog Slayer", "Forge Master", "Dawn Forge",
                 "Berserker", "Ghost Mode", "Deep Siege", "Sabbath", "Zero Debt",
                 "Doomfire Slayer", "Ancient Bane", "First Strike", "Triage Rite",
                 "Deep Priority"]:
        assert name in r.text


@pytest.mark.asyncio
async def test_trophies_frog_slayer_unlocks(client):
    """Mark a frog quest done — Frog Slayer should unlock."""
    qid = await _add_quest(client, title="Dreaded Task")
    # Toggle frog
    await client.patch(f"/quests/{qid}/frog")
    # Mark done
    await client.patch(f"/quests/{qid}/status", data={"status": "done"})

    r = await client.get("/trophies")
    assert r.status_code == 200
    # Should have at least a bronze frog slayer
    assert "Frog Slayer" in r.text
    assert "Bronze" in r.text or "Earned" in r.text


def _quest_for_trophy(
    *,
    title: str = "Quest",
    status: str = "done",
    priority: int = 4,
    created_days_ago: int = 0,
    completed_offset_seconds: int | None = 0,
) -> dict:
    now = clock.utcnow()
    completed_at = (
        (now + timedelta(seconds=completed_offset_seconds)).isoformat()
        if completed_offset_seconds is not None
        else None
    )
    return {
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "status": status,
        "frog": False,
        "created_at": (now - timedelta(days=created_days_ago)).isoformat(),
        "started_at": None,
        "completed_at": completed_at,
        "abandoned_at": None,
        "priority": priority,
        "project": None,
        "labels": [],
        "artifacts": {},
    }


def _trophy_by_id(result: dict, trophy_id: str) -> dict:
    return next(t for t in result["trophies"] if t["id"] == trophy_id)


def test_trophy_compute_doomfire_slayer_unlocks_for_p0_completion():
    result, _ = compute_trophies(
        [],
        [_quest_for_trophy(title="Urgent", priority=0)],
        {},
    )

    assert _trophy_by_id(result, "doomfire_slayer")["tier"] == "bronze"


def test_trophy_compute_ancient_bane_unlocks_for_old_completion():
    result, _ = compute_trophies(
        [],
        [_quest_for_trophy(title="Old Debt", priority=2, created_days_ago=15)],
        {},
    )

    assert _trophy_by_id(result, "ancient_bane")["tier"] == "earned"


def test_trophy_compute_first_strike_requires_first_completion_high_priority():
    result, _ = compute_trophies(
        [],
        [
            _quest_for_trophy(title="High First", priority=1, completed_offset_seconds=0),
            _quest_for_trophy(title="Low Later", priority=4, completed_offset_seconds=60),
        ],
        {},
    )

    assert _trophy_by_id(result, "first_strike")["tier"] == "earned"


def test_trophy_compute_triage_rite_blocks_stale_high_priority():
    stale_result, _ = compute_trophies(
        [],
        [_quest_for_trophy(title="Stale P0", status="active", priority=0, created_days_ago=5, completed_offset_seconds=None)],
        {},
    )
    fresh_result, _ = compute_trophies(
        [],
        [_quest_for_trophy(title="Fresh P1", status="active", priority=1, created_days_ago=1, completed_offset_seconds=None)],
        {},
    )

    assert _trophy_by_id(stale_result, "triage_rite")["tier"] == "locked"
    assert _trophy_by_id(fresh_result, "triage_rite")["tier"] == "earned"


def test_trophy_compute_deep_priority_maps_session_by_quest_id():
    now = clock.utcnow()
    quest = _quest_for_trophy(title="Priority Focus", status="active", priority=1, completed_offset_seconds=None)
    session = {
        "id": "s1",
        "quest_id": quest["id"],
        "quest_title": "Renamed Elsewhere",
        "started_at": now.isoformat(),
        "status": "completed",
        "actual_pomos": 2,
        "segments": [
            {
                "type": "work",
                "started_at": (now + timedelta(minutes=i * 30)).isoformat(),
                "ended_at": (now + timedelta(minutes=i * 30 + 25)).isoformat(),
                "completed": True,
                "forge_type": "",
                "interruptions": 0,
            }
            for i in range(2)
        ],
    }

    result, _ = compute_trophies([session], [quest], {})

    assert _trophy_by_id(result, "deep_priority")["tier"] == "earned"


@pytest.mark.asyncio
async def test_trophies_priority_age_war_room_names_render(client):
    r = await client.get("/trophies")
    assert r.status_code == 200
    for name in [
        "Priority Loadout",
        "High-Priority Pressure",
        "Priority Burn Rate",
        "Age Burn Rate",
        "Neglect Index",
    ]:
        assert name in r.text


# ── Dashboard ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_renders(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "War Room" in r.text
    assert "Battlefield Report" in r.text
    assert "Forge Report" in r.text


@pytest.mark.asyncio
async def test_dashboard_shows_metrics(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    # Should show quest metric names (RPG-themed)
    assert "Battle Tempo" in r.text
    assert "Victory Rate" in r.text
    # Should show pomo metric names (RPG-themed)
    assert "Forge Hours" in r.text
    assert "Berserker Fury" in r.text
    # Should show priority/age system-health metrics
    assert "Doomfire Pressure" in r.text
    assert "Neglect Index" in r.text
    assert "Priority Burn" in r.text
    assert "Old Debt Cleared" in r.text


@pytest.mark.asyncio
async def test_dashboard_has_close_button(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "Return to Quest Board" in r.text


# ── Sidebar Integration ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_sidebar_loads_panels(client):
    """The index page sidebar should have HTMX triggers for chronicle and trophies."""
    r = await client.get("/")
    assert r.status_code == 200
    assert 'hx-get="/chronicle"' in r.text
    assert 'hx-get="/trophies"' in r.text
    # Dashboard is accessed via 'd' keyboard shortcut, not a tab button
