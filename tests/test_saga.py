"""Tests for Saga mood logging and projections."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re

import pytest

from core.config import USER_TZ
from core.saga import saga_metrics, timeline_days
from core.storage.saga_backend import mood_catalog
from core.sync.config import SyncConfig
from core.sync.schema import sync_table_names
from core.sync.service import SyncService
from core.sync.store import MemoryObjectStore


ROOT = Path(__file__).resolve().parents[1]


def _sync_config(device: str) -> SyncConfig:
    return SyncConfig(
        enabled=True,
        provider="r2",
        device_name=device,
        bucket="life-os-sync-prod",
        prefix="lifeos/prod",
        endpoint="https://example.r2.cloudflarestorage.com",
        region="auto",
        access_key_id="key",
        secret_access_key="secret",
        encryption_passphrase="a-very-long-test-passphrase",
        auto_enabled=False,
        interval_seconds=0,
        ui_poll_seconds=60,
        show_prompts=True,
    )


async def _insert_saga(db, entry_id: str, day: str, energy: int = 3, pleasantness: int = -2, word: str = "frustrated", hour: int = 9):
    quadrant = "yellow" if energy > 0 and pleasantness > 0 else "red" if energy > 0 else "green" if pleasantness > 0 else "blue"
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entry_id, f"{day}T{hour:02d}:00:00+05:30", day, energy, pleasantness, quadrant, word),
    )


def test_saga_mood_catalog_has_100_nonzero_quadrant_cells():
    catalog = mood_catalog()
    assert len(catalog) == 100
    assert all(cell["energy"] != 0 and cell["pleasantness"] != 0 for cell in catalog)
    by_coords = {(cell["energy"], cell["pleasantness"]): cell for cell in catalog}
    assert by_coords[(5, -5)]["quadrant"] == "red"
    assert by_coords[(5, -5)]["word"] == "enraged"
    assert by_coords[(5, 5)]["quadrant"] == "yellow"
    assert by_coords[(5, 5)]["word"] == "ecstatic"
    assert by_coords[(-5, 5)]["quadrant"] == "green"
    assert by_coords[(-5, -5)]["quadrant"] == "blue"


@pytest.mark.asyncio
async def test_saga_migration_adds_synced_table(db):
    columns = [r[1] for r in await (await db.execute("PRAGMA table_info(saga_entries)")).fetchall()]
    for column in (
        "id",
        "timestamp",
        "local_date",
        "energy",
        "pleasantness",
        "quadrant",
        "mood_word",
        "note",
        "updated_at",
        "deleted_at",
        "sync_revision",
        "sync_origin_device",
    ):
        assert column in columns

    assert "saga_entries" in sync_table_names()

    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word) "
        "VALUES ('s1', '2026-04-25T09:00:00+05:30', '2026-04-25', 4, -3, 'red', 'anxious')"
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT table_name, record_id, op FROM sync_changes WHERE table_name = 'saga_entries'"
    )).fetchone()
    assert row == ("saga_entries", "s1", "INSERT")


@pytest.mark.asyncio
async def test_saga_entries_sync(sync_db):
    store = MemoryObjectStore()
    db1 = await sync_db("saga-one")
    db2 = await sync_db("saga-two")
    svc1 = SyncService(db1, _sync_config("personal-laptop"), store)
    svc2 = SyncService(db2, _sync_config("work-laptop"), store)
    await svc1.register_device()
    await svc2.register_device()

    await db1.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note) "
        "VALUES ('s1', '2026-04-25T09:00:00+05:30', '2026-04-25', -2, 4, 'green', 'balanced', 'clear')"
    )
    await db1.commit()

    assert (await svc1.push()).status == "ok"
    assert (await svc2.pull()).status == "ok"

    row = await (await db2.execute(
        "SELECT energy, pleasantness, quadrant, mood_word, note FROM saga_entries WHERE id = 's1'"
    )).fetchone()
    assert row == (-2, 4, "green", "balanced", "clear")


@pytest.mark.asyncio
async def test_saga_crud_routes(client, db):
    r = await client.get("/saga")
    assert r.status_code == 200
    assert "What is the weather inside?" in r.text

    r = await client.post("/saga/entries", data={
        "energy": "3",
        "pleasantness": "-2",
        "mood_word": "frustrated",
        "note": "too much noise",
    })
    assert r.status_code == 200
    assert "frustrated" in r.text
    assert "red" in r.text

    row = await (await db.execute("SELECT id, quadrant FROM saga_entries")).fetchone()
    entry_id = row[0]
    assert row[1] == "red"

    r = await client.patch(f"/saga/entries/{entry_id}", data={
        "energy": "-2",
        "pleasantness": "3",
        "mood_word": "relieved",
        "note": "settled",
    })
    assert r.status_code == 200
    assert "relieved" in r.text
    row = await (await db.execute("SELECT quadrant FROM saga_entries WHERE id = ?", (entry_id,))).fetchone()
    assert row[0] == "green"

    r = await client.delete(f"/saga/entries/{entry_id}")
    assert r.status_code == 200
    row = await (await db.execute("SELECT COUNT(*) FROM saga_entries")).fetchone()
    assert row[0] == 0


@pytest.mark.asyncio
async def test_saga_rejects_zero_coordinate(client, db):
    r = await client.post("/saga/entries", data={
        "energy": "0",
        "pleasantness": "-2",
        "mood_word": "flat",
        "note": "",
    })
    assert r.status_code == 400
    assert "Energy must be one of -5..-1 or 1..5." in r.text


@pytest.mark.asyncio
async def test_saga_today_tab_is_input_only_with_rpg_nav_labels(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    await _insert_saga(db, "saga-existing", day, -2, 3, "relieved")
    await db.execute("UPDATE saga_entries SET note = 'existing note should stay out of input tab' WHERE id = 'saga-existing'")
    await db.commit()

    r = await client.get("/saga")

    assert r.status_code == 200
    assert ">Campfire</button>" in r.text
    assert ">Chronicle</button>" in r.text
    assert ">Grimoire</button>" in r.text
    assert ">Today</button>" not in r.text
    assert ">Timeline</button>" not in r.text
    assert ">Metrics</button>" not in r.text
    assert ">Stats</button>" not in r.text
    assert ">Oracle</button>" not in r.text
    assert "saga-today-notes" not in r.text
    assert "existing note should stay out of input tab" not in r.text


@pytest.mark.asyncio
async def test_saga_timeline_merges_sources(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    await _insert_saga(db, "s1", day, 4, 3, "joyful")
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, created_at, completed_at, workspace_id) "
        "VALUES ('q1', 'Ship the draft', 'done', 0, ?, ?, 'work')",
        (f"{day}T08:00:00+05:30", f"{day}T10:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('ch1', 'Test Era', ?, 'Bright')",
        (day,),
    )
    await db.execute(
        "INSERT INTO challenge_tasks (id, challenge_id, name, bucket) "
        "VALUES ('task1', 'ch1', 'Walk', 'anchor')"
    )
    await db.execute(
        "INSERT INTO challenge_entries "
        "(id, task_id, challenge_id, log_date, state, notes, created_at) "
        "VALUES ('entry1', 'task1', 'ch1', ?, 'COMPLETED_SATISFACTORY', 'walk felt calm', ?)",
        (day, f"{day}T11:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenge_experiments "
        "(id, challenge_id, action, motivation, timeframe, status, started_at, ends_at, created_at) "
        "VALUES ('exp1', 'ch1', 'Quiet morning protocol', 'test the calmer start', 'day', 'running', ?, ?, ?)",
        (day, day, f"{day}T07:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state, notes, created_at) "
        "VALUES ('exp-entry1', 'exp1', 'ch1', ?, 'STARTED', 'felt promising', ?)",
        (day, f"{day}T12:00:00+05:30"),
    )
    await db.commit()

    timeline = await timeline_days(db)
    current = timeline["days"][0]
    assert current["entries"][1]["type"] == "challenge_reflection"
    assert current["challenge_reflections"][0]["task_title"] == "Walk"
    assert current["entries"][1]["note_html"] == "<p>walk felt calm</p>"
    assert "notes" not in current["challenges"][0]
    assert len(current["challenges_done"]) == 1
    assert current["experiments"][0]["action"] == "Quiet morning protocol"

    r = await client.get("/saga/timeline")
    assert r.status_code == 200
    assert "joyful" in r.text
    assert "Ship the draft" in r.text
    assert "Walk" in r.text
    assert "walk felt calm" in r.text
    assert "challenge reflection" in r.text
    assert "Tiny Experiments" in r.text
    assert "Quiet morning protocol" in r.text
    assert "saga-day-section--entries" in r.text
    assert "saga-day-section--quests" in r.text
    assert "saga-day-section--challenges" in r.text
    assert "saga-day-section--experiments" in r.text
    assert "saga-day-data-row--questlog" in r.text
    assert "saga-day-data-row--hard90" in r.text
    assert "--day-mood-accent: #F4C430" in r.text
    assert "2 entries" in r.text
    assert "latest joyful E:4 P:3" in r.text
    assert "1 quest" in r.text
    assert "1 trial" in r.text
    assert "1 experiment" in r.text
    assert "--quadrant-accent: #F4C430" in r.text
    assert "saga-mood-pill--quadrant" in r.text
    assert "saga-mood-pill--coords" in r.text
    assert r.text.index("joyful") < r.text.index("Ship the draft")
    assert r.text.index("challenge reflection") < r.text.index("saga-day-section--quests")


def test_saga_timeline_extends_with_page_not_nested_scroll():
    css = (ROOT / "web/static/saga.css").read_text()
    rule = re.search(r"\.saga-timeline\s*\{(?P<body>.*?)\n\}", css, re.S)
    assert rule is not None
    assert "max-height" not in rule.group("body")
    assert "overflow-y: auto" not in rule.group("body")


@pytest.mark.asyncio
async def test_saga_metrics_render(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    for idx, coords in enumerate(((3, -2, "frustrated"), (4, -4, "terrified"), (5, -5, "enraged")), start=1):
        await _insert_saga(db, f"s{idx}", day, coords[0], coords[1], coords[2], hour=idx)
    await db.commit()

    r = await client.get("/saga/metrics")
    assert r.status_code == 200
    assert "The Field Report" in r.text
    assert "Red Spillover" in r.text
    assert "Mood load consumed execution" in r.text
    assert "Mood × Output co-movement" in r.text
    assert "Energy × Pleasantness drift" in r.text
    assert "Challenge posture" in r.text
    assert "Mood Atlas" in r.text


@pytest.mark.asyncio
async def test_saga_metrics_derives_relational_day_archetype(db):
    day = datetime.now(USER_TZ).date()
    today = day.isoformat()
    yesterday = (day - timedelta(days=1)).isoformat()

    await _insert_saga(db, "storm-1", today, 5, -5, "enraged", hour=9)
    await _insert_saga(db, "storm-2", today, 4, -4, "terrified", hour=18)
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, priority, created_at, completed_at, workspace_id) "
        "VALUES ('q-prev', 'Yesterday baseline', 'done', 0, 4, ?, ?, 'work')",
        (f"{yesterday}T08:00:00+05:30", f"{yesterday}T10:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, priority, created_at, completed_at, workspace_id) "
        "VALUES ('q-today-1', 'Ship high leverage work', 'done', 1, 1, ?, ?, 'work')",
        (f"{today}T08:00:00+05:30", f"{today}T10:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO quests (id, title, status, frog, priority, created_at, completed_at, workspace_id) "
        "VALUES ('q-today-2', 'Close support loop', 'done', 0, 2, ?, ?, 'work')",
        (f"{today}T11:00:00+05:30", f"{today}T12:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('rel-ch', 'Relational Era', ?, 'Bright')",
        (today,),
    )
    await db.execute(
        "INSERT INTO challenge_tasks (id, challenge_id, name, bucket) "
        "VALUES ('rel-anchor', 'rel-ch', 'Walk', 'anchor')"
    )
    await db.execute(
        "INSERT INTO challenge_tasks (id, challenge_id, name, bucket) "
        "VALUES ('rel-improver', 'rel-ch', 'Study', 'improver')"
    )
    await db.execute(
        "INSERT INTO challenge_entries "
        "(id, task_id, challenge_id, log_date, state, created_at) "
        "VALUES ('rel-entry-1', 'rel-anchor', 'rel-ch', ?, 'COMPLETED_SATISFACTORY', ?)",
        (today, f"{today}T20:00:00+05:30"),
    )
    await db.execute(
        "INSERT INTO challenge_entries "
        "(id, task_id, challenge_id, log_date, state, created_at) "
        "VALUES ('rel-entry-2', 'rel-improver', 'rel-ch', ?, 'COMPLETED_SATISFACTORY', ?)",
        (today, f"{today}T20:05:00+05:30"),
    )
    await db.commit()

    metrics = await saga_metrics(db)
    current = metrics["current"]

    assert current["archetype"] == "Red Forge"
    assert current["relations"]["emotion_quest"] == "Output held under mood load"
    assert current["relations"]["emotion_challenge"] == "Discipline held under load"
    assert current["relations"]["quest_challenge"] == "Aligned progress"
    assert current["saga"]["mood_load"] >= 65
    assert current["quest"]["output_index"] >= 55
    assert current["challenge"]["score"] >= 75
