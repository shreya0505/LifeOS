"""Tests for core/storage/sqlite_backend.py — repo protocol implementations."""

from __future__ import annotations

import pytest
import pytest_asyncio

from core.storage.sqlite_backend import (
    SqliteQuestRepo,
    SqlitePomoRepo,
    SqliteTrophyPRRepo,
)


# ── Quest Repo ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quest_add_and_load(db):
    repo = SqliteQuestRepo(db)
    quest = await repo.add("Slay the dragon")
    assert quest["title"] == "Slay the dragon"
    assert quest["status"] == "log"
    assert quest["frog"] is False

    all_quests = await repo.load_all()
    assert len(all_quests) == 1
    assert all_quests[0]["id"] == quest["id"]


@pytest.mark.asyncio
async def test_quest_update_status(db):
    repo = SqliteQuestRepo(db)
    quest = await repo.add("Fix the auth bug")

    updated = await repo.update_status(quest["id"], "active")
    assert updated["status"] == "active"
    assert updated["started_at"] is not None

    done = await repo.update_status(quest["id"], "done")
    assert done["status"] == "done"
    assert done["completed_at"] is not None


@pytest.mark.asyncio
async def test_quest_update_nonexistent(db):
    repo = SqliteQuestRepo(db)
    result = await repo.update_status("nonexistent", "active")
    assert result is None


@pytest.mark.asyncio
async def test_quest_abandon(db):
    repo = SqliteQuestRepo(db)
    quest = await repo.add("Temporary quest")
    abandoned = await repo.abandon(quest["id"])
    assert abandoned["title"] == "Temporary quest"
    assert abandoned["status"] == "abandoned"
    assert abandoned["abandoned_at"] is not None

    all_quests = await repo.load_all()
    assert len(all_quests) == 1
    assert all_quests[0]["status"] == "abandoned"


@pytest.mark.asyncio
async def test_quest_abandon_nonexistent(db):
    repo = SqliteQuestRepo(db)
    result = await repo.abandon("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_quest_toggle_frog(db):
    repo = SqliteQuestRepo(db)
    quest = await repo.add("Froggy quest")
    assert quest["frog"] is False

    toggled = await repo.toggle_frog(quest["id"])
    assert toggled["frog"] is True

    toggled2 = await repo.toggle_frog(quest["id"])
    assert toggled2["frog"] is False


@pytest.mark.asyncio
async def test_quest_toggle_frog_nonexistent(db):
    repo = SqliteQuestRepo(db)
    result = await repo.toggle_frog("nonexistent")
    assert result is None


# ── Pomo Repo ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pomo_start_session(db):
    # Need a quest first for FK
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Auth refactor")

    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])
    assert session["quest_id"] == quest["id"]
    assert session["quest_title"] == quest["title"]
    assert session["status"] == "running"
    assert session["segments"] == []
    assert session["actual_pomos"] == 0


@pytest.mark.asyncio
async def test_pomo_add_segment(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Build feature")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    updated = await repo.add_segment(
        session_id=session["id"],
        seg_type="work",
        lap=0,
        cycle=0,
        completed=True,
        interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
        charge="Fix the bug",
    )
    assert len(updated["segments"]) == 1
    assert updated["actual_pomos"] == 1
    assert updated["segments"][0]["charge"] == "Fix the bug"


@pytest.mark.asyncio
async def test_pomo_hollow_not_counted(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Test quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    # Hollow forge should not increment actual_pomos
    updated = await repo.add_segment(
        session_id=session["id"],
        seg_type="work",
        lap=0,
        cycle=0,
        completed=True,
        interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
        forge_type="hollow",
    )
    assert updated["actual_pomos"] == 0


@pytest.mark.asyncio
async def test_pomo_update_deed(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    await repo.add_segment(
        session_id=session["id"],
        seg_type="work", lap=0, cycle=0,
        completed=True, interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
        charge="Do the thing",
    )

    await repo.update_segment_deed(session["id"], 0, "Did the thing")
    updated = await repo.get_session(session["id"])
    assert updated["segments"][0]["deed"] == "Did the thing"


@pytest.mark.asyncio
async def test_pomo_update_deed_hollow_decrements(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    await repo.add_segment(
        session_id=session["id"],
        seg_type="work", lap=0, cycle=0,
        completed=True, interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
        charge="Work",
    )
    # Now mark as hollow via deed update
    await repo.update_segment_deed(session["id"], 0, "Meh", forge_type="hollow")
    updated = await repo.get_session(session["id"])
    assert updated["actual_pomos"] == 0


@pytest.mark.asyncio
async def test_pomo_end_session(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    await repo.add_segment(
        session_id=session["id"],
        seg_type="work", lap=0, cycle=0,
        completed=True, interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
    )

    ended = await repo.end_session(session["id"])
    assert ended["status"] == "completed"
    assert ended["ended_at"] is not None


@pytest.mark.asyncio
async def test_pomo_end_session_no_pomos(db):
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    ended = await repo.end_session(session["id"])
    assert ended["status"] == "stopped"


@pytest.mark.asyncio
async def test_pomo_load_all_nested_structure(db):
    """load_all must return sessions with nested segments lists."""
    quest_repo = SqliteQuestRepo(db)
    quest = await quest_repo.add("Quest")
    repo = SqlitePomoRepo(db)
    session = await repo.start_session(quest["id"], quest["title"])

    await repo.add_segment(
        session_id=session["id"],
        seg_type="work", lap=0, cycle=0,
        completed=True, interruptions=0,
        started_at="2026-04-09T10:00:00Z",
        ended_at="2026-04-09T10:25:00Z",
        charge="Work hard",
        deed="Worked hard",
    )
    await repo.add_segment(
        session_id=session["id"],
        seg_type="short_break", lap=0, cycle=0,
        completed=True, interruptions=0,
        started_at="2026-04-09T10:25:00Z",
        ended_at="2026-04-09T10:30:00Z",
    )

    all_sessions = await repo.load_all()
    assert len(all_sessions) == 1
    assert len(all_sessions[0]["segments"]) == 2
    assert all_sessions[0]["segments"][0]["type"] == "work"
    assert all_sessions[0]["segments"][1]["type"] == "short_break"


# ── Trophy PR Repo ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trophy_pr_save_and_load(db):
    repo = SqliteTrophyPRRepo(db)
    prs = await repo.load_prs()
    assert prs == {}

    new_prs = {
        "iron_will": {"best": "5", "date": "2026-04-09", "detail": "5 pomos"},
        "frog_slayer": {"best": "3", "date": "2026-04-08", "detail": None},
    }
    await repo.save_prs(new_prs)

    loaded = await repo.load_prs()
    assert len(loaded) == 2
    assert loaded["iron_will"]["best"] == 5
    assert loaded["frog_slayer"]["date"] == "2026-04-08"


@pytest.mark.asyncio
async def test_trophy_pr_overwrite(db):
    repo = SqliteTrophyPRRepo(db)
    await repo.save_prs({"a": {"best": "1", "date": "2026-01-01", "detail": None}})
    await repo.save_prs({"b": {"best": "2", "date": "2026-02-01", "detail": None}})

    loaded = await repo.load_prs()
    assert "a" not in loaded
    assert "b" in loaded


@pytest.mark.asyncio
async def test_trophy_pr_save_is_idempotent_for_sync(db):
    repo = SqliteTrophyPRRepo(db)
    prs = {"a": {"best": "1", "date": "2026-01-01", "detail": None}}
    await repo.save_prs(prs)
    before = await (await db.execute("SELECT COUNT(*) FROM sync_changes")).fetchone()

    await repo.save_prs(prs)
    after = await (await db.execute("SELECT COUNT(*) FROM sync_changes")).fetchone()

    assert after[0] == before[0]
