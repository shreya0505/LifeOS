"""Syncable SQLite table metadata."""

from __future__ import annotations

from dataclasses import dataclass


SYNC_META_COLUMNS = {
    "updated_at",
    "deleted_at",
    "sync_revision",
    "sync_origin_device",
}


@dataclass(frozen=True)
class SyncTable:
    name: str
    pk: str
    duplicable: bool = False


SYNC_TABLES: tuple[SyncTable, ...] = (
    SyncTable("workspaces", "id"),
    SyncTable("challenges", "id"),
    SyncTable("challenge_holidays", "id"),
    SyncTable("challenge_tasks", "id"),
    SyncTable("challenge_entries", "id"),
    SyncTable("challenge_eras", "id"),
    SyncTable("challenge_experiments", "id"),
    SyncTable("challenge_experiment_entries", "id"),
    SyncTable("quests", "id", duplicable=True),
    SyncTable("artifact_keys", "id"),
    SyncTable("pomo_sessions", "id"),
    SyncTable("pomo_segments", "id"),
    SyncTable("trophy_records", "id"),
    SyncTable("saga_entries", "id"),
    SyncTable("saga_legacy_entries", "id"),
)

SYNC_TABLE_BY_NAME = {table.name: table for table in SYNC_TABLES}


def sync_table_names() -> list[str]:
    return [table.name for table in SYNC_TABLES]
