"""Shared sync-aware clear-data helper for LifeOS web data."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import sqlite3
from typing import Iterable

import aiosqlite

from core.sync.config import SyncConfig, load_sync_config
from core.sync.service import SyncResult, SyncService
from core.sync.store import ObjectStore, build_store


SCOPE_TABLES: dict[str, tuple[str, ...]] = {
    "questlog": ("pomo_segments", "pomo_sessions", "trophy_records", "artifact_keys", "quests"),
    "challenge": (
        "challenge_experiment_entries",
        "challenge_experiments",
        "challenge_entries",
        "challenge_holidays",
        "challenge_tasks",
        "challenge_eras",
        "challenges",
    ),
    "tiny_experiments": ("challenge_experiment_entries", "challenge_experiments"),
    "saga": ("saga_entries", "saga_legacy_entries"),
}
SCOPE_TABLES["all"] = (
    *SCOPE_TABLES["challenge"],
    *SCOPE_TABLES["questlog"],
    *SCOPE_TABLES["saga"],
)


class PendingLocalChangesError(RuntimeError):
    def __init__(self, pending: int, scope: str) -> None:
        self.pending = pending
        self.scope = scope
        super().__init__(
            f"{pending} unsynced local change(s) exist for scope '{scope}'. "
            "Sync first to preserve them, or rerun with discard explicitly enabled."
        )


class ForeignKeyIntegrityError(RuntimeError):
    def __init__(self, failures: list[tuple]) -> None:
        self.failures = failures
        preview = "; ".join(str(failure) for failure in failures[:5])
        super().__init__(f"Clear would leave inconsistent linked data: {preview}")


@dataclass(frozen=True)
class ClearDataResult:
    scope: str
    tables: tuple[str, ...]
    deleted_counts: dict[str, int]
    sync_enabled: bool
    restore_result: SyncResult | None


def tables_for_scope(scope: str) -> tuple[str, ...]:
    normalized = _normalize_scope(scope)
    return SCOPE_TABLES[normalized]


def _normalize_scope(scope: str) -> str:
    normalized = scope.strip().lower().replace("-", "_")
    aliases = {
        "quests": "questlog",
        "tiny": "tiny_experiments",
        "experiments": "tiny_experiments",
        "tiny_expts": "tiny_experiments",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SCOPE_TABLES:
        allowed = ", ".join(sorted(SCOPE_TABLES))
        raise ValueError(f"scope must be one of: {allowed}")
    return normalized


async def clear_scope(
    db_path: str,
    scope: str,
    *,
    discard_unsynced: bool = False,
    config: SyncConfig | None = None,
    store: ObjectStore | None = None,
) -> ClearDataResult:
    """Clear local data for a scope, then restore it from remote sync if enabled."""
    normalized_scope = _normalize_scope(scope)
    tables = SCOPE_TABLES[normalized_scope]
    config = config if config is not None else load_sync_config()

    db = await aiosqlite.connect(db_path)
    try:
        await db.execute("PRAGMA foreign_keys=OFF")
        sync_enabled = bool(config.enabled)
        if sync_enabled:
            pending = await _pending_unsent_count(db, tables)
            if pending and not discard_unsynced:
                raise PendingLocalChangesError(pending, normalized_scope)

        await _set_runtime(db, "clear_lock", "1")
        await db.commit()
        try:
            await _set_runtime(db, "suppress", "1")
            deleted_counts = {}
            for table in tables:
                deleted_counts[table] = await _table_count(db, table)
                await _delete_table(db, table)

            await _cleanup_sync_metadata(db, tables)
            await _assert_fk_integrity(db, tables)
            await db.commit()

            restore_result = None
            if sync_enabled:
                await db.execute("PRAGMA foreign_keys=ON")
                restore_store = store if store is not None else build_store(config)
                restore_result = await SyncService(db, config, restore_store).restore_tables(tables)
                if restore_result.status != "ok":
                    raise RuntimeError(restore_result.message or "Remote restore failed.")
                await _assert_fk_integrity(db, tables)

            return ClearDataResult(
                scope=normalized_scope,
                tables=tables,
                deleted_counts=deleted_counts,
                sync_enabled=sync_enabled,
                restore_result=restore_result,
            )
        finally:
            await _set_runtime(db, "suppress", "0")
            await _set_runtime(db, "clear_lock", "0")
            await db.commit()
    finally:
        await db.close()


async def _pending_unsent_count(db: aiosqlite.Connection, tables: Iterable[str]) -> int:
    if not await _table_exists(db, "sync_changes"):
        return 0
    placeholders = ",".join("?" for _ in tables)
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM sync_changes WHERE sent_at IS NULL AND table_name IN ({placeholders})",
        tuple(tables),
    )
    row = await cursor.fetchone()
    return int(row[0] if row else 0)


async def _cleanup_sync_metadata(db: aiosqlite.Connection, tables: Iterable[str]) -> None:
    table_tuple = tuple(tables)
    if await _table_exists(db, "sync_changes"):
        placeholders = ",".join("?" for _ in table_tuple)
        await db.execute(f"DELETE FROM sync_changes WHERE table_name IN ({placeholders})", table_tuple)
    if await _table_exists(db, "sync_conflicts"):
        placeholders = ",".join("?" for _ in table_tuple)
        await db.execute(f"DELETE FROM sync_conflicts WHERE table_name IN ({placeholders})", table_tuple)
    if await _table_exists(db, "sync_state"):
        await db.execute("UPDATE sync_state SET value = '' WHERE key = 'last_error'")


async def _set_runtime(db: aiosqlite.Connection, key: str, value: str) -> None:
    if not await _table_exists(db, "sync_runtime"):
        return
    await db.execute(
        "INSERT INTO sync_runtime (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return await cursor.fetchone() is not None


async def _table_count(db: aiosqlite.Connection, table: str) -> int:
    if not await _table_exists(db, table):
        return 0
    cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
    row = await cursor.fetchone()
    return int(row[0] if row else 0)


async def _delete_table(db: aiosqlite.Connection, table: str) -> None:
    if await _table_exists(db, table):
        await db.execute(f"DELETE FROM {table}")


async def _assert_fk_integrity(db: aiosqlite.Connection, tables: Iterable[str]) -> None:
    failures = []
    for table in tables:
        if not await _table_exists(db, table):
            continue
        cursor = await db.execute(f"PRAGMA foreign_key_check({table})")
        failures.extend(await cursor.fetchall())
    if failures:
        raise ForeignKeyIntegrityError(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear local LifeOS web data without propagating remote deletes.")
    parser.add_argument("--db", required=True, help="Path to the SQLite database.")
    parser.add_argument("--scope", required=True, choices=sorted(SCOPE_TABLES), help="Data scope to clear.")
    parser.add_argument(
        "--discard-unsynced",
        action="store_true",
        help="Explicitly discard unsynced local changes in the selected scope.",
    )
    return parser.parse_args()


def _print_result(result: ClearDataResult) -> None:
    print(f"Scope: {result.scope}")
    for table in result.tables:
        print(f"  deleted {result.deleted_counts.get(table, 0)} row(s) from {table}")
    if result.sync_enabled:
        restore = result.restore_result
        message = restore.message if restore else "No restore result."
        print(f"Remote restore: {message}")
    else:
        print("Sync disabled: local data cleared only.")
    print("No remote deletes were queued.")


def main() -> int:
    args = _parse_args()
    try:
        result = asyncio.run(
            clear_scope(
                args.db,
                args.scope,
                discard_unsynced=args.discard_unsynced,
            )
        )
    except PendingLocalChangesError as exc:
        print(str(exc))
        return 2
    except (ForeignKeyIntegrityError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"Clear failed: {exc}")
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
