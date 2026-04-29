from __future__ import annotations

import aiosqlite
import pytest

from core.maintenance.clear_data import SCOPE_TABLES, PendingLocalChangesError, clear_scope
from core.sync.config import SyncConfig
from core.sync.service import SyncService
from core.sync.store import MemoryObjectStore
from web.db import migrate


def _config(device: str, enabled: bool = True) -> SyncConfig:
    return SyncConfig(
        enabled=enabled,
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


async def _db(path):
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await migrate(conn)
    return conn


async def _insert_saga(conn, entry_id: str, word: str = "focused"):
    await conn.execute(
        "INSERT INTO saga_entries "
        "(id, timestamp, local_date, energy, pleasantness, quadrant, mood_word, note) "
        "VALUES (?, '2026-04-29T09:00:00Z', '2026-04-29', 3, 2, 'yellow', ?, 'note')",
        (entry_id, word),
    )
    await conn.commit()


async def _insert_challenge_with_tiny_experiment(conn):
    await conn.execute(
        "INSERT INTO challenges (id, era_name, start_date, midweek_adjective) "
        "VALUES ('ch1', 'Linked Era', '2026-04-29', 'Clear')"
    )
    await conn.execute(
        "INSERT INTO challenge_experiments "
        "(id, challenge_id, action, motivation, timeframe, status, started_at, ends_at) "
        "VALUES ('exp1', 'ch1', 'One tiny protocol', 'Keep links valid', 'week', "
        "'running', '2026-04-29', '2026-05-05')"
    )
    await conn.execute(
        "INSERT INTO challenge_experiment_entries "
        "(id, experiment_id, challenge_id, log_date, state, notes) "
        "VALUES ('expe1', 'exp1', 'ch1', '2026-04-29', 'STARTED', 'linked')"
    )
    await conn.commit()


async def _count(conn, table: str) -> int:
    row = await (await conn.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()
    return row[0]


async def _fk_failures(conn):
    return await (await conn.execute("PRAGMA foreign_key_check")).fetchall()


def test_clear_scopes_encode_challenge_tiny_relationship():
    assert "challenge_experiment_entries" in SCOPE_TABLES["challenge"]
    assert "challenge_experiments" in SCOPE_TABLES["challenge"]
    assert SCOPE_TABLES["challenge"].index("challenge_experiment_entries") < SCOPE_TABLES["challenge"].index("challenge_experiments")
    assert SCOPE_TABLES["tiny_experiments"] == ("challenge_experiment_entries", "challenge_experiments")


@pytest.mark.asyncio
async def test_challenge_clear_also_deletes_linked_tiny_experiment_data(tmp_path):
    db_path = tmp_path / "challenge.db"
    db = await _db(db_path)
    try:
        await _insert_challenge_with_tiny_experiment(db)

        result = await clear_scope(
            str(db_path),
            "challenge",
            config=_config("work-laptop", enabled=False),
        )

        assert result.sync_enabled is False
        assert await _count(db, "challenge_experiment_entries") == 0
        assert await _count(db, "challenge_experiments") == 0
        assert await _count(db, "challenges") == 0
        assert await _fk_failures(db) == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_tiny_experiment_clear_leaves_parent_challenge_data_consistent(tmp_path):
    db_path = tmp_path / "tiny.db"
    db = await _db(db_path)
    try:
        await _insert_challenge_with_tiny_experiment(db)

        result = await clear_scope(
            str(db_path),
            "tiny_experiments",
            config=_config("work-laptop", enabled=False),
        )

        assert result.sync_enabled is False
        assert await _count(db, "challenge_experiment_entries") == 0
        assert await _count(db, "challenge_experiments") == 0
        assert await _count(db, "challenges") == 1
        assert await _fk_failures(db) == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_tiny_experiment_restore_refuses_orphan_remote_rows(tmp_path):
    store = MemoryObjectStore()
    db1_path = tmp_path / "remote.db"
    db2_path = tmp_path / "local.db"
    db1 = await _db(db1_path)
    db2 = await _db(db2_path)
    try:
        await _insert_challenge_with_tiny_experiment(db1)
        pushed = await SyncService(db1, _config("personal-laptop"), store).push()
        assert pushed.status == "ok"

        with pytest.raises(RuntimeError):
            await clear_scope(
                str(db2_path),
                "tiny_experiments",
                config=_config("work-laptop"),
                store=store,
            )

        assert await _count(db2, "challenge_experiment_entries") == 0
        assert await _count(db2, "challenge_experiments") == 0
        assert await _fk_failures(db2) == []
    finally:
        await db1.close()
        await db2.close()


@pytest.mark.asyncio
async def test_clear_scope_with_sync_restores_remote_rows_without_queueing_deletes(tmp_path):
    store = MemoryObjectStore()
    db1_path = tmp_path / "one.db"
    db2_path = tmp_path / "two.db"
    db1 = await _db(db1_path)
    db2 = await _db(db2_path)
    try:
        svc1 = SyncService(db1, _config("personal-laptop"), store)
        svc2 = SyncService(db2, _config("work-laptop"), store)
        await svc1.register_device()
        await svc2.register_device()

        await _insert_saga(db1, "saga-1", "bright")
        pushed = await svc1.push()
        assert pushed.status == "ok"
        pulled = await svc2.pull()
        assert pulled.status == "ok"

        result = await clear_scope(
            str(db2_path),
            "saga",
            config=_config("work-laptop"),
            store=store,
        )

        assert result.sync_enabled is True
        assert result.restore_result is not None
        assert result.restore_result.status == "ok"
        row = await (await db2.execute("SELECT mood_word FROM saga_entries WHERE id = 'saga-1'")).fetchone()
        assert row == ("bright",)
        pending_delete = await (await db2.execute(
            "SELECT COUNT(*) FROM sync_changes "
            "WHERE table_name = 'saga_entries' AND op = 'DELETE' AND sent_at IS NULL"
        )).fetchone()
        assert pending_delete == (0,)
    finally:
        await db1.close()
        await db2.close()


@pytest.mark.asyncio
async def test_clear_scope_refuses_unsynced_local_changes_when_sync_enabled(tmp_path):
    db_path = tmp_path / "local.db"
    db = await _db(db_path)
    try:
        await _insert_saga(db, "local-only", "tense")

        with pytest.raises(PendingLocalChangesError):
            await clear_scope(
                str(db_path),
                "saga",
                config=_config("work-laptop"),
                store=MemoryObjectStore(),
            )

        row = await (await db.execute("SELECT mood_word FROM saga_entries WHERE id = 'local-only'")).fetchone()
        assert row == ("tense",)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_clear_scope_can_explicitly_discard_unsynced_changes(tmp_path):
    db_path = tmp_path / "discard.db"
    db = await _db(db_path)
    try:
        await _insert_saga(db, "local-only", "tense")

        result = await clear_scope(
            str(db_path),
            "saga",
            discard_unsynced=True,
            config=_config("work-laptop"),
            store=MemoryObjectStore(),
        )

        assert result.sync_enabled is True
        row = await (await db.execute("SELECT id FROM saga_entries WHERE id = 'local-only'")).fetchone()
        assert row is None
        pending = await (await db.execute(
            "SELECT COUNT(*) FROM sync_changes WHERE table_name = 'saga_entries' AND sent_at IS NULL"
        )).fetchone()
        assert pending == (0,)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sync_run_skips_while_clear_lock_is_active(tmp_path):
    db_path = tmp_path / "locked.db"
    db = await _db(db_path)
    try:
        await db.execute(
            "INSERT INTO sync_runtime (key, value) VALUES ('clear_lock', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        await db.commit()

        result = await SyncService(db, _config("work-laptop"), MemoryObjectStore()).run()

        assert result.status == "locked"
        assert result.message == "Clear/restore is in progress; sync skipped."
    finally:
        await db.close()
