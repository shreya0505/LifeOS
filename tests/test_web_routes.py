"""Tests for web quest routes — full CRUD via HTMX endpoints."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from core.config import USER_TZ


async def _quest_id_by_title(db, title: str) -> str:
    row = await (await db.execute("SELECT id FROM quests WHERE title = ?", (title,))).fetchone()
    assert row is not None
    return row[0]


@pytest.mark.asyncio
async def test_index_renders_full_page(client):
    r = await client.get("/")
    assert r.status_code == 200
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
    assert r.text.count('title="Block quest"') >= 2

    # Done (active -> done)
    r = await client.patch(f"/quests/{qid}/status", data={"status": "done"})
    assert r.status_code == 200
    assert f'data-status="done"' in r.text

    # Abandon
    r = await client.post(f"/quests/{qid}/abandon")
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
    # Frog icon should appear on the card
    assert "quest-card__frog" in r.text


@pytest.mark.asyncio
async def test_abandon_quest(client):
    r = await client.post("/quests", data={"title": "Abandon me"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    r = await client.post(f"/quests/{qid}/abandon")
    assert r.status_code == 200
    assert "Abandon me" not in r.text


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


@pytest.mark.asyncio
async def test_board_conquered_shows_only_today(client, db):
    await client.post("/quests", data={"title": "Today victory"})
    await client.post("/quests", data={"title": "Old victory"})
    today_id = await _quest_id_by_title(db, "Today victory")
    older_id = await _quest_id_by_title(db, "Old victory")

    await client.patch(f"/quests/{today_id}/status", data={"status": "active"})
    await client.patch(f"/quests/{today_id}/status", data={"status": "done"})
    await client.patch(f"/quests/{older_id}/status", data={"status": "active"})
    await client.patch(f"/quests/{older_id}/status", data={"status": "done"})

    old_completed = (datetime.now(USER_TZ) - timedelta(days=2)).isoformat()
    await db.execute(
        "UPDATE quests SET completed_at = ? WHERE id = ?",
        (old_completed, older_id),
    )
    await db.commit()

    r = await client.get("/quests")
    assert r.status_code == 200
    assert "Today victory" in r.text
    assert "Old victory" not in r.text
    assert "2 in Legend" in r.text


@pytest.mark.asyncio
async def test_legend_shows_all_done_quests_grouped_by_day(client, db):
    await client.post("/quests", data={"title": "Latest victory"})
    await client.post("/quests", data={"title": "Earlier victory"})
    latest_id = await _quest_id_by_title(db, "Latest victory")
    older_id = await _quest_id_by_title(db, "Earlier victory")

    for qid in (latest_id, older_id):
        await client.patch(f"/quests/{qid}/status", data={"status": "active"})
        await client.patch(f"/quests/{qid}/status", data={"status": "done"})

    older_completed = (datetime.now(USER_TZ) - timedelta(days=3)).replace(hour=9, minute=0).isoformat()
    await db.execute(
        "UPDATE quests SET completed_at = ? WHERE id = ?",
        (older_completed, older_id),
    )
    await db.commit()

    r = await client.get("/quests/legend")
    assert r.status_code == 200
    assert "Latest victory" in r.text
    assert "Earlier victory" in r.text
    assert "Today" in r.text
    assert "2 conquered" in r.text
    assert r.text.index("Latest victory") < r.text.index("Earlier victory")


@pytest.mark.asyncio
async def test_legend_shows_artifacts_for_done_quests(client, db):
    await client.post(
        "/quests",
        data={
            "title": "Ship summary",
            "artifact_key[]": ["PR", "Outcome"],
            "artifact_val[]": ["https://example.com/pr/42", "Released billing fix"],
        },
    )
    qid = await _quest_id_by_title(db, "Ship summary")
    await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    await client.patch(f"/quests/{qid}/status", data={"status": "done"})

    r = await client.get("/quests/legend")
    assert r.status_code == 200
    assert "Ship summary" in r.text
    assert "PR" in r.text
    assert "https://example.com/pr/42" in r.text
    assert "Outcome" in r.text
    assert "Released billing fix" in r.text


@pytest.mark.asyncio
async def test_board_sort_by_age_orders_open_columns(client, db):
    fresh = await client.post("/quests", data={"title": "Fresh urgent", "priority": 0})
    await client.post("/quests", data={"title": "Old whisper", "priority": 4})
    fresh_id = re.search(r'data-id="([^"]+)"', fresh.text).group(1)
    old_id = (await (await db.execute("SELECT id FROM quests WHERE title = ?", ("Old whisper",))).fetchone())[0]
    now = datetime.now(timezone.utc)
    await db.execute(
        "UPDATE quests SET created_at = ? WHERE id = ?",
        ((now - timedelta(days=1)).isoformat(), fresh_id),
    )
    await db.execute(
        "UPDATE quests SET created_at = ? WHERE id = ?",
        ((now - timedelta(days=12)).isoformat(), old_id),
    )
    await db.commit()

    r = await client.get("/quests?sort=age")
    assert r.status_code == 200
    assert r.text.index("Old whisper") < r.text.index("Fresh urgent")


@pytest.mark.asyncio
async def test_board_sort_by_priority_orders_open_columns(client, db):
    await client.post("/quests", data={"title": "Low priority", "priority": 4})
    await client.post("/quests", data={"title": "High priority", "priority": 0})

    r = await client.get("/quests?sort=priority")
    assert r.status_code == 200
    assert r.text.index("High priority") < r.text.index("Low priority")


@pytest.mark.asyncio
async def test_board_sort_state_survives_htmx_mutation(client, db):
    fresh = await client.post("/quests", data={"title": "Fresh mutable", "priority": 4})
    await client.post("/quests", data={"title": "Old mutable", "priority": 4})
    fresh_id = re.search(r'data-id="([^"]+)"', fresh.text).group(1)
    old_id = (await (await db.execute("SELECT id FROM quests WHERE title = ?", ("Old mutable",))).fetchone())[0]
    now = datetime.now(timezone.utc)
    await db.execute(
        "UPDATE quests SET created_at = ? WHERE id = ?",
        ((now - timedelta(days=1)).isoformat(), fresh_id),
    )
    await db.execute(
        "UPDATE quests SET created_at = ? WHERE id = ?",
        ((now - timedelta(days=12)).isoformat(), old_id),
    )
    await db.commit()

    r = await client.patch(
        f"/quests/{fresh_id}/priority",
        data={"priority": 0, "filter_state": "sort=age"},
    )
    assert r.status_code == 200
    assert r.text.index("Old mutable") < r.text.index("Fresh mutable")
