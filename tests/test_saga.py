"""Tests for Saga emotion logging and projections."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.config import USER_TZ
from core.sync.config import SyncConfig
from core.sync.schema import sync_table_names
from core.sync.service import SyncService
from core.sync.store import MemoryObjectStore


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
async def test_saga_timeline_merges_sources(client, db):
    day = datetime.now(USER_TZ).date().isoformat()
    await db.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, emotion_family, emotion_label, intensity) "
        "VALUES ('s1', ?, ?, 'joy', 'joy', 5)",
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
    assert r.text.index("joy") < r.text.index("Ship the draft") < r.text.index("Walk")


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
    assert "Reflection metrics" in r.text
    assert "Fear" in r.text
    assert "3 entries" in r.text
