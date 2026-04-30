from __future__ import annotations

import pytest
import pytest_asyncio
import aiosqlite

from core.sync.config import SyncConfig, SyncConfigError, load_sync_config
from core.sync.crypto import SyncDecryptError, decrypt_json, encrypt_json
from core.sync.schema import sync_table_names
from core.sync.service import SyncService
from core.sync.store import MemoryObjectStore
from web.db import migrate


def _config(device: str) -> SyncConfig:
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


def test_sync_config_requires_values_when_enabled():
    with pytest.raises(SyncConfigError):
        load_sync_config({"SYNC_ENABLED": "true", "SYNC_PROVIDER": "r2"})

    cfg = load_sync_config({"SYNC_ENABLED": "false"})
    assert cfg.enabled is False


def test_sync_crypto_rejects_wrong_passphrase():
    payload = encrypt_json({"hello": "world"}, "correct horse battery staple")
    assert decrypt_json(payload, "correct horse battery staple") == {"hello": "world"}
    with pytest.raises(SyncDecryptError):
        decrypt_json(payload, "wrong horse battery staple")


def test_sync_tables_include_tiny_experiments():
    names = sync_table_names()
    assert "challenge_experiments" in names
    assert "challenge_experiment_entries" in names
    assert "challenge_holidays" in names


@pytest.mark.asyncio
async def test_push_pull_bootstraps_hard_90_tables(sync_db):
    store = MemoryObjectStore()
    db1 = await sync_db("one")
    db2 = await sync_db("two")
    svc1 = SyncService(db1, _config("personal-laptop"), store)
    svc2 = SyncService(db2, _config("work-laptop"), store)
    await svc1.register_device()
    await svc2.register_device()

    await db1.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('ch1', 'Test Era', '2026-04-24', 'Bright')"
    )
    await db1.execute(
        "INSERT INTO challenge_tasks (id, challenge_id, name, bucket) "
        "VALUES ('task1', 'ch1', 'Workout', 'anchor')"
    )
    await db1.execute(
        "INSERT INTO challenge_entries (id, task_id, challenge_id, log_date, state, notes) "
        "VALUES ('entry1', 'task1', 'ch1', '2026-04-24', 'STARTED', 'begun')"
    )
    await db1.execute(
        "INSERT INTO challenge_entries (id, task_id, challenge_id, log_date, state, notes) "
        "VALUES ('entry-note', 'task1', 'ch1', '2026-04-25', NULL, 'captured before rating')"
    )
    await db1.execute(
        "INSERT INTO challenge_holidays (id, challenge_id, log_date, reason) "
        "VALUES ('holiday1', 'ch1', '2026-04-26', 'travel')"
    )
    await db1.execute(
        "INSERT INTO challenge_experiments "
        "(id, challenge_id, action, motivation, timeframe, status, started_at, ends_at) "
        "VALUES ('exp1', 'ch1', 'No-scroll morning', 'Focus should rise', 'week', "
        "'running', '2026-04-24', '2026-04-30')"
    )
    await db1.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state, notes) "
        "VALUES ('expe1', 'exp1', 'ch1', '2026-04-24', 'PARTIAL', 'signal')"
    )
    await db1.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state, notes) "
        "VALUES ('expe-note', 'exp1', 'ch1', '2026-04-25', NULL, 'field note before rating')"
    )
    await db1.commit()

    pushed = await svc1.push()
    assert pushed.status == "ok"

    pulled = await svc2.pull()
    assert pulled.status == "ok"

    row = await (await db2.execute("SELECT era_name FROM challenges WHERE id = 'ch1'")).fetchone()
    assert row[0] == "Test Era"
    row = await (await db2.execute("SELECT state FROM challenge_entries WHERE id = 'entry1'")).fetchone()
    assert row[0] == "STARTED"
    row = await (await db2.execute("SELECT state, notes FROM challenge_entries WHERE id = 'entry-note'")).fetchone()
    assert row == (None, "captured before rating")
    row = await (await db2.execute("SELECT reason FROM challenge_holidays WHERE id = 'holiday1'")).fetchone()
    assert row == ("travel",)
    row = await (await db2.execute("SELECT action FROM challenge_experiments WHERE id = 'exp1'")).fetchone()
    assert row[0] == "No-scroll morning"
    row = await (await db2.execute("SELECT state FROM challenge_experiment_entries WHERE id = 'expe1'")).fetchone()
    assert row[0] == "PARTIAL"
    row = await (await db2.execute("SELECT state, notes FROM challenge_experiment_entries WHERE id = 'expe-note'")).fetchone()
    assert row == (None, "field note before rating")


@pytest.mark.asyncio
async def test_tiny_experiment_writes_queue_sync_changes(db):
    await db.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('ch1', 'Test Era', '2026-04-24', 'Bright')"
    )
    await db.execute(
        "INSERT INTO challenge_experiments "
        "(id, challenge_id, action, motivation, timeframe) "
        "VALUES ('exp1', 'ch1', 'No-scroll morning', 'Focus should rise', 'day')"
    )
    await db.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state) "
        "VALUES ('expe1', 'exp1', 'ch1', '2026-04-24', 'STARTED')"
    )
    await db.commit()
    rows = await (await db.execute(
        "SELECT table_name FROM sync_changes "
        "WHERE table_name IN ('challenge_experiments', 'challenge_experiment_entries') "
        "ORDER BY table_name"
    )).fetchall()
    assert [r[0] for r in rows] == [
        "challenge_experiment_entries",
        "challenge_experiments",
    ]


@pytest.mark.asyncio
async def test_pull_queues_same_row_conflict(sync_db):
    store = MemoryObjectStore()
    db1 = await sync_db("one")
    db2 = await sync_db("two")
    svc1 = SyncService(db1, _config("personal-laptop"), store)
    svc2 = SyncService(db2, _config("work-laptop"), store)
    await svc1.register_device()
    await svc2.register_device()

    await db1.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('ch1', 'Original', '2026-04-24', 'Bright')"
    )
    await db1.commit()
    await svc1.push()
    await svc2.pull()

    await db1.execute("UPDATE challenges SET era_name = 'Remote Edit' WHERE id = 'ch1'")
    await db1.commit()
    await svc1.push()

    await db2.execute("UPDATE challenges SET era_name = 'Local Edit' WHERE id = 'ch1'")
    await db2.commit()
    pulled = await svc2.pull()

    assert pulled.conflicts == 1
    conflicts = await svc2.open_conflicts()
    assert any(
        c["table_name"] == "challenges" and c["record_id"] == "ch1"
        for c in conflicts
    )


@pytest.mark.asyncio
async def test_pull_skips_legacy_saga_rows_without_mood_meter_coords(sync_db):
    store = MemoryObjectStore()
    db = await sync_db("legacy-saga")
    cfg = _config("work-laptop")
    svc = SyncService(db, cfg, store)
    await svc.register_device()

    await store.put_bytes(
        "bootstrap.json.enc",
        encrypt_json(
            {
                "version": 1,
                "device": "old-laptop",
                "created_at": "2026-04-28T00:00:00Z",
                "tables": {
                    "saga_entries": [
                        {
                            "id": "old-saga",
                            "timestamp": "2026-04-28T09:00:00Z",
                            "local_date": "2026-04-28",
                            "emotion_family": "joy",
                            "emotion_label": "calm",
                            "intensity": 5,
                            "created_at": "2026-04-28T09:00:00Z",
                            "updated_at": "2026-04-28T09:00:00Z",
                            "sync_revision": 1,
                            "sync_origin_device": "old-laptop",
                        }
                    ]
                },
            },
            cfg.encryption_passphrase,
        ),
    )
    await store.put_json(
        "manifest.json",
        {
            "version": 1,
            "bootstrap_key": "bootstrap.json.enc",
            "bundles": [],
            "updated_at": "2026-04-28T00:00:00Z",
        },
    )

    result = await svc.pull()

    assert result.status == "ok"
    row = await (await db.execute("SELECT COUNT(*) FROM saga_entries")).fetchone()
    assert row == (0,)


@pytest.mark.asyncio
async def test_pull_derives_missing_saga_quadrant_from_coords(sync_db):
    store = MemoryObjectStore()
    db = await sync_db("partial-saga")
    cfg = _config("work-laptop")
    svc = SyncService(db, cfg, store)
    await svc.register_device()

    await store.put_bytes(
        "bootstrap.json.enc",
        encrypt_json(
            {
                "version": 1,
                "device": "other-laptop",
                "created_at": "2026-04-28T00:00:00Z",
                "tables": {
                    "saga_entries": [
                        {
                            "id": "partial-saga",
                            "timestamp": "2026-04-28T09:00:00Z",
                            "local_date": "2026-04-28",
                            "energy": 4,
                            "pleasantness": -2,
                            "created_at": "2026-04-28T09:00:00Z",
                            "updated_at": "2026-04-28T09:00:00Z",
                            "sync_revision": 1,
                            "sync_origin_device": "other-laptop",
                        }
                    ]
                },
            },
            cfg.encryption_passphrase,
        ),
    )
    await store.put_json(
        "manifest.json",
        {
            "version": 1,
            "bootstrap_key": "bootstrap.json.enc",
            "bundles": [],
            "updated_at": "2026-04-28T00:00:00Z",
        },
    )

    result = await svc.pull()

    assert result.status == "ok"
    row = await (await db.execute(
        "SELECT energy, pleasantness, quadrant, mood_word FROM saga_entries WHERE id = 'partial-saga'"
    )).fetchone()
    assert row == (4, -2, "red", "red")


@pytest.mark.asyncio
async def test_pull_skips_any_remote_row_that_violates_local_constraints(sync_db):
    store = MemoryObjectStore()
    db = await sync_db("invalid-row")
    cfg = _config("work-laptop")
    svc = SyncService(db, cfg, store)
    await svc.register_device()

    await store.put_bytes(
        "bootstrap.json.enc",
        encrypt_json(
            {
                "version": 1,
                "device": "old-laptop",
                "created_at": "2026-04-28T00:00:00Z",
                "tables": {
                    "challenges": [
                        {
                            "id": "bad-challenge",
                            "start_date": "2026-04-28",
                            "created_at": "2026-04-28T00:00:00Z",
                            "sync_revision": 1,
                            "sync_origin_device": "old-laptop",
                        }
                    ]
                },
            },
            cfg.encryption_passphrase,
        ),
    )
    await store.put_json(
        "manifest.json",
        {
            "version": 1,
            "bootstrap_key": "bootstrap.json.enc",
            "bundles": [],
            "updated_at": "2026-04-28T00:00:00Z",
        },
    )

    result = await svc.pull()

    assert result.status == "ok"
    row = await (await db.execute("SELECT COUNT(*) FROM challenges WHERE id = 'bad-challenge'")).fetchone()
    assert row == (0,)
