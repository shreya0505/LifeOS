"""Tests for Saga emotion logging and projections."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re

import pytest

from core.config import USER_TZ
from core.saga import saga_metrics
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


@pytest.mark.asyncio
async def test_saga_migration_adds_synced_table(db):
    columns = [r[1] for r in await (await db.execute("PRAGMA table_info(saga_entries)")).fetchall()]
    for column in (
        "id",
        "timestamp",
        "local_date",
        "emotion_family",
        "emotion_label",
        "intensity",
        "note",
        "secondary_emotion_family",
        "secondary_emotion_label",
        "dyad_label",
        "dyad_type",
        "updated_at",
        "deleted_at",
        "sync_revision",
        "sync_origin_device",
    ):
        assert column in columns

    assert "saga_entries" in sync_table_names()

    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity) "
        "VALUES ('s1', '2026-04-25T09:00:00+05:30', '2026-04-25', 'joy', 'joy', 5)"
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
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity, note) "
        "VALUES ('s1', '2026-04-25T09:00:00+05:30', '2026-04-25', 'joy', 'serenity', 3, 'clear')"
    )
    await db1.commit()

    assert (await svc1.push()).status == "ok"
    assert (await svc2.pull()).status == "ok"

    row = await (await db2.execute(
        "SELECT emotion_label, intensity, note FROM saga_entries WHERE id = 's1'"
    )).fetchone()
    assert row == ("serenity", 3, "clear")


@pytest.mark.asyncio
async def test_saga_crud_routes(client, db):
    r = await client.get("/saga")
    assert r.status_code == 200
    assert "What is the tone right now?" in r.text

    r = await client.post("/saga/entries", data={
        "emotion_family": "anger",
        "emotion_label": "annoyance",
        "intensity": "4",
        "note": "too much noise",
    })
    assert r.status_code == 200
    assert "annoyance" in r.text

    entry_id = (await (await db.execute("SELECT id FROM saga_entries")).fetchone())[0]
    r = await client.patch(f"/saga/entries/{entry_id}", data={
        "emotion_family": "trust",
        "emotion_label": "acceptance",
        "intensity": "2",
        "note": "settled",
    })
    assert r.status_code == 200
    assert "acceptance" in r.text

    r = await client.delete(f"/saga/entries/{entry_id}")
    assert r.status_code == 200
    row = await (await db.execute("SELECT COUNT(*) FROM saga_entries")).fetchone()
    assert row[0] == 0


@pytest.mark.asyncio
async def test_saga_today_tab_is_input_only_with_rpg_nav_labels(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity, note) "
        "VALUES ('saga-existing', ?, ?, 'joy', 'joy', 5, 'existing note should stay out of input tab')",
        (f"{day}T09:00:00+05:30", day),
    )
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
async def test_saga_two_emotions_save_primary_dyad(client, db):
    r = await client.post("/saga/entries", data={
        "emotion_family": "joy",
        "emotion_label": "joy",
        "secondary_emotion_family": "trust",
        "secondary_emotion_label": "trust",
        "intensity": "6",
        "note": "warm and steady",
    })
    assert r.status_code == 200
    assert "love / primary" in r.text

    row = await (await db.execute(
        "SELECT secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
        "FROM saga_entries"
    )).fetchone()
    assert row == ("trust", "trust", "love", "primary")


@pytest.mark.asyncio
async def test_saga_two_emotions_save_opposite_without_dyad_label(client, db):
    r = await client.post("/saga/entries", data={
        "emotion_family": "joy",
        "emotion_label": "serenity",
        "secondary_emotion_family": "sadness",
        "secondary_emotion_label": "pensiveness",
        "intensity": "4",
        "note": "both at once",
    })
    assert r.status_code == 200
    assert "Opposites" in r.text

    row = await (await db.execute(
        "SELECT secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type "
        "FROM saga_entries"
    )).fetchone()
    assert row == ("sadness", "pensiveness", None, "opposite")


@pytest.mark.asyncio
async def test_saga_timeline_merges_sources(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type) "
        "VALUES ('s1', ?, ?, 'joy', 'joy', 5, 'trust', 'trust', 'love', 'primary')",
        (f"{day}T09:00:00+05:30", day),
    )
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
        "VALUES ('entry1', 'task1', 'ch1', ?, 'COMPLETED_SATISFACTORY', 'done', ?)",
        (day, f"{day}T11:00:00+05:30"),
    )
    await db.commit()

    r = await client.get("/saga/timeline")
    assert r.status_code == 200
    assert "joy" in r.text
    assert "Ship the draft" in r.text
    assert "Walk" in r.text
    assert "saga-day-section--entries" in r.text
    assert "saga-day-section--quests" in r.text
    assert "saga-day-section--challenges" in r.text
    assert "saga-day-data-row--questlog" in r.text
    assert "saga-day-data-row--hard90" in r.text
    assert "--day-mood-accent: #F6D365" in r.text
    assert "1 entry" in r.text
    assert "latest joy 5/10" in r.text
    assert "1 quest" in r.text
    assert "1 trial" in r.text
    assert "--mood-accent: #F6D365" in r.text
    assert "--dyad-accent: #FF7BA7" in r.text
    assert "saga-mood-pill--emotion" in r.text
    assert "saga-mood-pill--dyad" in r.text
    assert "saga-mood-pill--intensity" in r.text
    assert "love" in r.text
    assert r.text.index("joy") < r.text.index("Ship the draft") < r.text.index("Walk")


def test_saga_timeline_extends_with_page_not_nested_scroll():
    css = (ROOT / "web/static/saga.css").read_text()
    rule = re.search(r"\.saga-timeline\s*\{(?P<body>.*?)\n\}", css, re.S)
    assert rule is not None
    assert "max-height" not in rule.group("body")
    assert "overflow-y: auto" not in rule.group("body")


@pytest.mark.asyncio
async def test_saga_metrics_render(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    for idx, intensity in enumerate((3, 8, 9), start=1):
        await db.execute(
            "INSERT INTO saga_entries "
            "(id, timestamp, local_date, emotion_family, emotion_label, intensity) "
            "VALUES (?, ?, ?, 'fear', 'fear', ?)",
            (f"s{idx}", f"{day}T0{idx}:00:00+05:30", day, intensity),
        )
    await db.commit()

    r = await client.get("/saga/metrics")
    assert r.status_code == 200
    assert "The Field Report" in r.text
    assert "Emotional Debt" in r.text
    assert "Load consumed execution" in r.text
    assert "Mood × Output co-movement" in r.text
    assert "Challenge posture" in r.text
    assert "Emotion Atlas" in r.text


@pytest.mark.asyncio
async def test_saga_metrics_derives_relational_day_archetype(db):
    day = datetime.now(USER_TZ).date()
    today = day.isoformat()
    yesterday = (day - timedelta(days=1)).isoformat()

    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity, "
        "secondary_emotion_family, secondary_emotion_label, dyad_label, dyad_type) "
        "VALUES ('storm-1', ?, ?, 'joy', 'joy', 8, 'trust', 'trust', 'love', 'primary')",
        (f"{today}T09:00:00+05:30", today),
    )
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity) "
        "VALUES ('storm-2', ?, ?, 'joy', 'ecstasy', 9)",
        (f"{today}T18:00:00+05:30", today),
    )
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
        "VALUES ('rel-entry-2', 'rel-improver', 'rel-ch', ?, 'COMPLETED_UNSATISFACTORY', ?)",
        (today, f"{today}T20:05:00+05:30"),
    )
    await db.commit()

    metrics = await saga_metrics(db)
    current = metrics["current"]

    assert current["archetype"] == "Storm Forge"
    assert current["relations"]["emotion_quest"] == "Output held under pressure"
    assert current["relations"]["emotion_challenge"] == "Discipline held under pressure"
    assert current["relations"]["quest_challenge"] == "Aligned progress"
    assert current["saga"]["mood_load"] >= 65
    assert current["quest"]["output_index"] >= 55
    assert current["challenge"]["score"] >= 75
