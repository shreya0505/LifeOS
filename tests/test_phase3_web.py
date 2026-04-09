"""Tests for Phase 3 web routes: chronicle, trophies, dashboard."""

from __future__ import annotations

import re

import pytest
import pytest_asyncio


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
    assert "1 today" in r.text


@pytest.mark.asyncio
async def test_chronicle_heatmap_has_cells(client):
    r = await client.get("/chronicle")
    assert r.status_code == 200
    assert "heatmap__cell" in r.text
    # Should have legend
    assert "less" in r.text
    assert "more" in r.text


# ── Trophies ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trophies_empty(client):
    r = await client.get("/trophies")
    assert r.status_code == 200
    assert "trophy-panel" in r.text
    # All should be locked
    assert "🔒" in r.text


@pytest.mark.asyncio
async def test_trophies_with_pomo(client):
    qid = await _add_quest(client)
    await _complete_pomo(client, qid, charge="Deep work", deed="Work done")

    r = await client.get("/trophies")
    assert r.status_code == 200
    assert "trophy-card" in r.text
    # Scribe should have at least bronze (1 documented pomo)
    assert "Scribe" in r.text


@pytest.mark.asyncio
async def test_trophies_shows_all_seven(client):
    r = await client.get("/trophies")
    assert r.status_code == 200
    for name in ["Frog Slayer", "Swamp Clearer", "Forge Master",
                 "Untouchable", "Quest Closer", "Scribe", "Ironclad"]:
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
    assert "🥉" in r.text or "🥈" in r.text or "🏆" in r.text


# ── Dashboard ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_renders(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "War Room Dashboard" in r.text
    assert "Quest Metrics" in r.text
    assert "Pomo Metrics" in r.text


@pytest.mark.asyncio
async def test_dashboard_shows_metrics(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    # Should show quest metric names
    assert "Weekly Velocity" in r.text
    assert "Completion Rate" in r.text
    # Should show pomo metric names
    assert "Weekly Focus Time" in r.text
    assert "Berserker Rate" in r.text


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
    assert 'hx-get="/dashboard"' in r.text
