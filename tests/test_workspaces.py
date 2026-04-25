"""Workspace boundary tests for QuestLog."""

from __future__ import annotations

import re

import pytest

from core.storage.sqlite_backend import SqlitePomoRepo, SqliteTrophyPRRepo


async def _workspace_id_by_name(db, name: str) -> str:
    row = await (await db.execute("SELECT id FROM workspaces WHERE name = ?", (name,))).fetchone()
    assert row is not None
    return row[0]


@pytest.mark.asyncio
async def test_migration_seeds_work_workspace(db):
    row = await (await db.execute("SELECT id, name, icon, color FROM workspaces WHERE id = 'work'")).fetchone()
    assert row == ("work", "Work", "folder", "blue")

    for table in ("quests", "artifact_keys", "pomo_sessions", "pomo_segments", "trophy_records"):
        columns = [r[1] for r in await (await db.execute(f"PRAGMA table_info({table})")).fetchall()]
        assert "workspace_id" in columns


@pytest.mark.asyncio
async def test_workspace_switch_isolates_board_and_new_quests(client, db):
    r = await client.post("/quests", data={"title": "Work task"})
    assert r.status_code == 200
    assert "Work task" in r.text

    r = await client.post("/workspaces", data={"name": "Home", "icon": "moon", "color": "green"})
    assert r.status_code == 200
    assert r.headers["hx-refresh"] == "true"
    home_id = await _workspace_id_by_name(db, "Home")

    r = await client.get("/quests")
    assert r.status_code == 200
    assert "Work task" not in r.text

    r = await client.post("/quests", data={"title": "Home task"})
    assert r.status_code == 200
    assert "Home task" in r.text
    assert "Work task" not in r.text

    row = await (await db.execute("SELECT workspace_id FROM quests WHERE title = 'Home task'")).fetchone()
    assert row[0] == home_id

    r = await client.post("/workspaces/select", data={"workspace_id": "work"})
    assert r.status_code == 200
    r = await client.get("/quests")
    assert "Work task" in r.text
    assert "Home task" not in r.text


@pytest.mark.asyncio
async def test_cross_workspace_quest_mutation_is_ignored(client, db):
    r = await client.post("/quests", data={"title": "Boundary task"})
    qid = re.search(r'data-id="([^"]+)"', r.text).group(1)

    await client.post("/workspaces", data={"name": "Startup", "icon": "hammer", "color": "amber"})
    r = await client.patch(f"/quests/{qid}/status", data={"status": "active"})
    assert r.status_code == 200
    assert "Boundary task" not in r.text

    row = await (await db.execute("SELECT status, workspace_id FROM quests WHERE id = ?", (qid,))).fetchone()
    assert row == ("log", "work")


@pytest.mark.asyncio
async def test_pomos_and_trophies_store_workspace_id(db):
    await db.execute(
        "INSERT INTO workspaces (id, name, icon, color, sort_order) VALUES ('home', 'Home', 'moon', 'green', 20)"
    )
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, created_at, workspace_id) "
        "VALUES ('qhome', 'Home quest', 'active', 0, '2026-04-25T00:00:00Z', 'home')"
    )
    await db.commit()

    pomo_repo = SqlitePomoRepo(db)
    session = await pomo_repo.start_session("qhome", "Home quest", workspace_id="home")
    await pomo_repo.add_segment(
        session["id"], "work", 0, 0, True, 0,
        "2026-04-25T00:00:00Z", "2026-04-25T00:25:00Z",
    )
    row = await (await db.execute("SELECT workspace_id FROM pomo_segments WHERE session_id = ?", (session["id"],))).fetchone()
    assert row[0] == "home"

    trophy_repo = SqliteTrophyPRRepo(db, "home")
    await trophy_repo.save_prs({"forge_master": {"best": 2, "date": "2026-04-25", "detail": "2 pomos"}})
    row = await (await db.execute("SELECT workspace_id FROM trophy_records WHERE trophy_id = 'forge_master'")).fetchone()
    assert row[0] == "home"
