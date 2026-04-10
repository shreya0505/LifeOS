"""Tests for the web pomo flow — charge/timer/deed/break lifecycle."""

from __future__ import annotations

import re

import pytest
import pytest_asyncio

import web.pomos.engine as engine_mod
import web.db as db_mod
from core.pomo_engine import PomoEngine
from core.storage.sync_sqlite_backend import SyncSqlitePomoRepo


@pytest.fixture(autouse=True)
def _reset_engine(tmp_path, monkeypatch):
    """Reset the singleton engine and point it at the test DB."""
    engine_mod._engine = None
    engine_mod._sync_repo = None
    # Ensure engine uses the same DB as the async connection
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    yield
    if engine_mod._sync_repo is not None:
        engine_mod._sync_repo.close()
    engine_mod._engine = None
    engine_mod._sync_repo = None


async def _add_active_quest(client) -> str:
    """Helper: add a quest and move it to active. Returns quest_id."""
    r = await client.post("/quests", data={"title": "Test Quest"})
    match = re.search(r'data-id="([^"]+)"', r.text)
    qid = match.group(1)
    await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    return qid


# ── Start session ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_pomo_session(client):
    qid = await _add_active_quest(client)
    r = await client.post("/pomos/start", data={"quest_id": qid})
    assert r.status_code == 200
    assert "Test Quest" in r.text
    assert "charge" in r.text.lower() or "forged" in r.text.lower()


@pytest.mark.asyncio
async def test_start_pomo_requires_active_quest(client):
    # Add quest but don't activate it
    r = await client.post("/quests", data={"title": "Inactive Quest"})
    match = re.search(r'data-id="([^"]+)"', r.text)
    qid = match.group(1)
    r = await client.post("/pomos/start", data={"quest_id": qid})
    assert r.status_code == 400


# ── Charge ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_charge(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})

    r = await client.post("/pomos/charge", data={"charge": "Fix the auth bug"})
    assert r.status_code == 200
    assert "Fix the auth bug" in r.text
    # Should be in timer mode now
    assert "pomodoroTimer" in r.text or "timer" in r.text.lower()


@pytest.mark.asyncio
async def test_charge_without_session(client):
    r = await client.post("/pomos/charge", data={"charge": "No session"})
    assert r.status_code == 400


# ── Deed ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_deed_after_early_complete(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Build feature"})

    # Complete early (Swiftblade)
    r = await client.post("/pomos/complete-early")
    assert r.status_code == 200
    # Should be in deed mode
    assert "claimed" in r.text.lower() or "deed" in r.text.lower()

    # Submit deed
    r = await client.post("/pomos/deed", data={"deed": "Feature built", "forge_type": ""})
    assert r.status_code == 200
    # Should be in break choice mode
    assert "rest" in r.text.lower() or "break" in r.text.lower()


@pytest.mark.asyncio
async def test_deed_with_hollow_forge(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Try something"})
    await client.post("/pomos/complete-early")

    r = await client.post("/pomos/deed", data={"deed": "Meh session", "forge_type": "hollow"})
    assert r.status_code == 200
    assert "Hollow" in r.text or "hollow" in r.text.lower()


@pytest.mark.asyncio
async def test_deed_with_berserker_forge(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Go hard"})
    await client.post("/pomos/complete-early")

    r = await client.post("/pomos/deed", data={"deed": "Crushed it", "forge_type": "berserker"})
    assert r.status_code == 200
    assert "BERSERKER" in r.text or "berserker" in r.text.lower()


# ── Break choice ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_break_skip(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})
    await client.post("/pomos/complete-early")
    await client.post("/pomos/deed", data={"deed": "Done", "forge_type": ""})

    r = await client.post("/pomos/break", data={"choice": "skip"})
    assert r.status_code == 200
    # Should be back at charge gate
    assert "forged" in r.text.lower() or "charge" in r.text.lower()


@pytest.mark.asyncio
async def test_break_end_session(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})
    await client.post("/pomos/complete-early")
    await client.post("/pomos/deed", data={"deed": "Done", "forge_type": ""})

    r = await client.post("/pomos/break", data={"choice": "end"})
    assert r.status_code == 200
    assert '<div class="pomo-overlay" id="pomo-panel">' in r.text
    assert "summary-ritual" in r.text or "Return to Quest Board" in r.text


@pytest.mark.asyncio
async def test_break_short(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})
    await client.post("/pomos/complete-early")
    await client.post("/pomos/deed", data={"deed": "Done", "forge_type": ""})

    r = await client.post("/pomos/break", data={"choice": "short"})
    assert r.status_code == 200
    # Should be in timer mode for break
    assert "pomodoroTimer" in r.text or "Break" in r.text


# ── Interrupt ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interrupt(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})

    r = await client.post("/pomos/interrupt", data={"reason": "Phone call"})
    assert r.status_code == 200
    assert '<div class="pomo-overlay" id="pomo-panel">' in r.text
    assert "summary-ritual" in r.text or "Return to Quest Board" in r.text


# ── Stop session ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_session(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})

    r = await client.post("/pomos/stop")
    assert r.status_code == 200
    assert '<div class="pomo-overlay" id="pomo-panel">' in r.text
    assert "summary-ritual" in r.text or "Return to Quest Board" in r.text


@pytest.mark.asyncio
async def test_stop_without_session(client):
    r = await client.post("/pomos/stop")
    assert r.status_code == 400


# ── Receipt ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_receipt_empty(client):
    r = await client.get("/pomos/receipt")
    assert r.status_code == 200
    assert "No completed" in r.text or "receipt" in r.text.lower()


@pytest.mark.asyncio
async def test_receipt_after_pomo(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Build feature"})
    await client.post("/pomos/complete-early")
    await client.post("/pomos/deed", data={"deed": "Feature built", "forge_type": ""})
    await client.post("/pomos/break", data={"choice": "end"})

    r = await client.get("/pomos/receipt")
    assert r.status_code == 200
    assert "Build feature" in r.text
    assert "Feature built" in r.text


# ── Full lifecycle ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pomo_lifecycle(client):
    """Start -> charge -> early complete -> deed -> skip break -> charge -> stop."""
    qid = await _add_active_quest(client)

    # Start
    r = await client.post("/pomos/start", data={"quest_id": qid})
    assert r.status_code == 200

    # Charge 1
    r = await client.post("/pomos/charge", data={"charge": "First pomo work"})
    assert r.status_code == 200

    # Complete early
    r = await client.post("/pomos/complete-early")
    assert r.status_code == 200

    # Deed 1
    r = await client.post("/pomos/deed", data={"deed": "First pomo done", "forge_type": ""})
    assert r.status_code == 200

    # Skip break
    r = await client.post("/pomos/break", data={"choice": "skip"})
    assert r.status_code == 200

    # Charge 2
    r = await client.post("/pomos/charge", data={"charge": "Second pomo work"})
    assert r.status_code == 200

    # Stop session
    r = await client.post("/pomos/stop")
    assert r.status_code == 200
    assert "summary-ritual" in r.text or "Return to Quest Board" in r.text


# ── Pomo status ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pomo_status_no_session(client):
    r = await client.get("/pomos/status")
    assert r.status_code == 200
    assert r.text.strip() == ""


@pytest.mark.asyncio
async def test_pomo_status_active(client):
    qid = await _add_active_quest(client)
    await client.post("/pomos/start", data={"quest_id": qid})
    await client.post("/pomos/charge", data={"charge": "Work"})

    r = await client.get("/pomos/status")
    assert r.status_code == 200
    assert "Test Quest" in r.text
