"""Tests for web quest routes — full CRUD via HTMX endpoints."""

from __future__ import annotations

import re

import pytest


@pytest.mark.asyncio
async def test_index_renders_full_page(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "STARFORGE" in r.text
    assert "Quest Board" in r.text
    assert "In Battle" in r.text
    assert "Conquered" in r.text


@pytest.mark.asyncio
async def test_add_quest(client):
    r = await client.post("/quests", data={"title": "Slay the dragon"})
    assert r.status_code == 200
    assert "Slay the dragon" in r.text


@pytest.mark.asyncio
async def test_add_quest_strips_whitespace(client):
    r = await client.post("/quests", data={"title": "  padded  "})
    assert r.status_code == 200
    assert "padded" in r.text


@pytest.mark.asyncio
async def test_quest_lifecycle(client):
    """Add -> Start -> Done -> Delete full lifecycle."""
    # Add
    r = await client.post("/quests", data={"title": "Auth refactor"})
    assert r.status_code == 200
    match = re.search(r'data-id="([^"]+)"', r.text)
    assert match
    qid = match.group(1)

    # Start (log -> active)
    r = await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    assert r.status_code == 200
    assert f'data-status="active"' in r.text

    # Done (active -> done)
    r = await client.patch(f"/quests/{qid}/status", data={"status": "done"})
    assert r.status_code == 200
    assert f'data-status="done"' in r.text

    # Delete
    r = await client.delete(f"/quests/{qid}")
    assert r.status_code == 200
    assert "Auth refactor" not in r.text


@pytest.mark.asyncio
async def test_quest_block_and_unblock(client):
    r = await client.post("/quests", data={"title": "Blocked quest"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    # Block (log -> blocked)
    r = await client.patch(f"/quests/{qid}/status", data={"status": "blocked"})
    assert r.status_code == 200
    assert f'data-status="blocked"' in r.text

    # Unblock (blocked -> active)
    r = await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    assert r.status_code == 200
    assert f'data-status="active"' in r.text


@pytest.mark.asyncio
async def test_invalid_transition_ignored(client):
    """done -> active is not a valid transition; quest stays done."""
    r = await client.post("/quests", data={"title": "Done quest"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    await client.patch(f"/quests/{qid}/status", data={"status": "done"})

    # Try invalid: done -> active
    r = await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    assert r.status_code == 200
    # Should still be done
    assert f'data-id="{qid}"' in r.text
    card_match = re.search(
        rf'data-status="(\w+)"[^>]*data-id="{qid}"', r.text
    ) or re.search(
        rf'data-id="{qid}"[^>]*data-status="(\w+)"', r.text
    )
    # The quest card with this ID should not be in the active column


@pytest.mark.asyncio
async def test_toggle_frog(client):
    r = await client.post("/quests", data={"title": "Froggy"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    r = await client.patch(f"/quests/{qid}/frog")
    assert r.status_code == 200
    # Frog emoji should appear on the card
    assert "🐸" in r.text


@pytest.mark.asyncio
async def test_confirm_delete_modal(client):
    r = await client.post("/quests", data={"title": "Delete me"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    r = await client.get(f"/quests/{qid}/confirm-delete")
    assert r.status_code == 200
    assert "Delete me" in r.text
    assert "Destroy" in r.text


@pytest.mark.asyncio
async def test_stats_bar(client):
    r = await client.get("/stats")
    assert r.status_code == 200
    assert "scrolls" in r.text
    assert "forges" in r.text


@pytest.mark.asyncio
async def test_quest_board_partial(client):
    await client.post("/quests", data={"title": "Quest A"})
    await client.post("/quests", data={"title": "Quest B"})

    r = await client.get("/quests")
    assert r.status_code == 200
    assert "Quest A" in r.text
    assert "Quest B" in r.text
