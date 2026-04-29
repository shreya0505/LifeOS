"""SQLite logical sync service."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from core.sync.config import SyncConfig
from core.sync.crypto import decrypt_json, encrypt_json
from core.sync.schema import SYNC_TABLES, SYNC_TABLE_BY_NAME, SyncTable
from core.sync.store import ObjectStore


MANIFEST_KEY = "manifest.json"
BOOTSTRAP_KEY = "bootstrap.json.enc"

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _hash_row(row: dict | None) -> str:
    if row is None:
        return ""
    public = {
        k: v for k, v in row.items()
        if k not in {"updated_at", "sync_revision", "sync_origin_device"}
    }
    return hashlib.sha256(_dumps(public).encode("utf-8")).hexdigest()


def _normalize_workspace_row(table: SyncTable, row: dict | None) -> dict | None:
    """Accept pre-workspace sync rows by assigning them to Work."""
    if row is None:
        return None
    if table.name == "saga_entries":
        return _normalize_saga_row(row)
    normalized = dict(row)
    if table.name in {"quests", "artifact_keys", "pomo_sessions", "pomo_segments", "trophy_records"}:
        normalized["workspace_id"] = normalized.get("workspace_id") or "work"
    if table.name == "artifact_keys" and not normalized.get("id") and normalized.get("name"):
        normalized["id"] = f"{normalized.get('workspace_id', 'work')}:{normalized['name']}"
    if table.name == "trophy_records" and not normalized.get("id") and normalized.get("trophy_id"):
        normalized["id"] = f"{normalized.get('workspace_id', 'work')}:{normalized['trophy_id']}"
    return normalized


def _normalize_saga_row(row: dict) -> dict | None:
    """Accept only rows compatible with the current Mood Meter schema.

    Remote sync can still contain pre-Mood-Meter Saga rows from the old
    Plutchik model. Migration 012 intentionally dropped those rows locally, so
    sync should skip them rather than failing the whole pull on NOT NULL
    constraints for energy/pleasantness.
    """
    normalized = dict(row)
    try:
        energy = int(normalized.get("energy"))
        pleasantness = int(normalized.get("pleasantness"))
    except (TypeError, ValueError):
        logger.warning(
            "sync.saga.skip_legacy_row id=%s reason=missing_mood_meter_coords keys=%s",
            normalized.get("id"),
            sorted(normalized.keys()),
        )
        return None

    if energy == 0 or pleasantness == 0 or not -5 <= energy <= 5 or not -5 <= pleasantness <= 5:
        logger.warning(
            "sync.saga.skip_invalid_row id=%s energy=%s pleasantness=%s",
            normalized.get("id"),
            energy,
            pleasantness,
        )
        return None

    normalized["energy"] = energy
    normalized["pleasantness"] = pleasantness
    normalized["quadrant"] = normalized.get("quadrant") or _saga_quadrant(energy, pleasantness)
    normalized["mood_word"] = (
        normalized.get("mood_word")
        or normalized.get("emotion_label")
        or normalized.get("quadrant")
        or "unknown"
    )
    return normalized


def _saga_quadrant(energy: int, pleasantness: int) -> str:
    if energy > 0 and pleasantness > 0:
        return "yellow"
    if energy > 0:
        return "red"
    if pleasantness > 0:
        return "green"
    return "blue"


@dataclass
class SyncResult:
    action: str
    status: str
    message: str = ""
    bundles_pulled: int = 0
    changes_pushed: int = 0
    conflicts: int = 0


class SyncService:
    def __init__(self, db: aiosqlite.Connection, config: SyncConfig, store: ObjectStore) -> None:
        self.db = db
        self.config = config
        self.store = store

    async def register_device(self) -> None:
        logger.info("sync.device.register.start device=%s", self.config.device_name)
        await self._set_state("device_name", self.config.device_name)
        await self.db.execute(
            "INSERT INTO sync_devices (name) VALUES (?) "
            "ON CONFLICT(name) DO UPDATE SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (self.config.device_name,),
        )
        await self.db.commit()
        logger.info("sync.device.register.ok device=%s", self.config.device_name)

    async def status(self) -> dict:
        await self._drop_prebootstrap_stale_deletes()
        changes, _ = await self._pending_changes()
        pending = len(changes)
        conflicts = await self._scalar("SELECT COUNT(*) FROM sync_conflicts WHERE status = 'open'")
        logger.info(
            "sync.status device=%s pending=%s conflicts=%s",
            self.config.device_name,
            pending or 0,
            conflicts or 0,
        )
        return {
            "enabled": self.config.enabled,
            "device_name": self.config.device_name,
            "pending_changes": pending or 0,
            "open_conflicts": conflicts or 0,
            "last_pull_at": await self._get_state("last_pull_at", ""),
            "last_push_at": await self._get_state("last_push_at", ""),
            "last_error": await self._get_state("last_error", ""),
        }

    async def push(self) -> SyncResult:
        run_id = await self._start_run("push")
        logger.info("sync.push.start run_id=%s device=%s", run_id, self.config.device_name)
        try:
            locked = await self._clear_locked()
            if locked:
                result = SyncResult("push", "locked", "Clear/restore is in progress; sync push skipped.")
                await self._finish_run(run_id, result)
                logger.info("sync.push.locked run_id=%s", run_id)
                return result
            await self.register_device()
            manifest = await self._load_manifest()
            if not manifest.get("bootstrap_key"):
                logger.info("sync.push.bootstrap.missing run_id=%s", run_id)
                await self._upload_bootstrap(manifest)

            changes, max_change_id = await self._pending_changes()
            logger.info(
                "sync.push.pending run_id=%s effective_changes=%s max_change_id=%s",
                run_id,
                len(changes),
                max_change_id,
            )
            if not changes:
                await self._set_state("last_push_at", _now())
                result = SyncResult("push", "ok", "No local changes to push.")
                await self._finish_run(run_id, result)
                logger.info("sync.push.ok run_id=%s changes=0", run_id)
                return result

            bundle_id = uuid.uuid4().hex
            now = _now()
            key = f"bundles/{now[:4]}/{now[5:7]}/{bundle_id}.json.enc"
            bundle = {
                "version": 1,
                "id": bundle_id,
                "device": self.config.device_name,
                "created_at": now,
                "changes": changes,
            }
            await self.store.put_bytes(
                key,
                encrypt_json(bundle, self.config.encryption_passphrase),
                "application/octet-stream",
            )
            logger.info(
                "sync.push.bundle.uploaded run_id=%s bundle_id=%s key=%s changes=%s",
                run_id,
                bundle_id,
                key,
                len(changes),
            )
            manifest.setdefault("bundles", []).append({
                "id": bundle_id,
                "key": key,
                "device": self.config.device_name,
                "created_at": now,
                "change_count": len(changes),
            })
            manifest["updated_at"] = now
            await self.store.put_json(MANIFEST_KEY, manifest)
            logger.info(
                "sync.push.manifest.updated run_id=%s bundle_count=%s bootstrap=%s",
                run_id,
                len(manifest.get("bundles", [])),
                bool(manifest.get("bootstrap_key")),
            )
            await self.db.execute(
                "UPDATE sync_changes SET sent_at = ?, remote_bundle_id = ? "
                "WHERE sent_at IS NULL AND id <= ?",
                (now, bundle_id, max_change_id),
            )
            await self._set_state("last_push_at", now)
            await self._set_state("last_error", "")
            await self.db.commit()
            result = SyncResult("push", "ok", f"Pushed {len(changes)} change(s).", changes_pushed=len(changes))
            await self._finish_run(run_id, result)
            logger.info("sync.push.ok run_id=%s changes=%s bundle_id=%s", run_id, len(changes), bundle_id)
            return result
        except Exception as exc:
            logger.exception("sync.push.error run_id=%s", run_id)
            result = SyncResult("push", "error", str(exc))
            await self._set_state("last_error", f"Push failed: {exc}")
            await self._finish_run(run_id, result)
            return result

    async def pull(self) -> SyncResult:
        run_id = await self._start_run("pull")
        logger.info("sync.pull.start run_id=%s device=%s", run_id, self.config.device_name)
        try:
            locked = await self._clear_locked()
            if locked:
                result = SyncResult("pull", "locked", "Clear/restore is in progress; sync pull skipped.")
                await self._finish_run(run_id, result)
                logger.info("sync.pull.locked run_id=%s", run_id)
                return result
            await self.register_device()
            manifest = await self._load_manifest()
            if not manifest:
                result = SyncResult("pull", "ok", "No remote sync state found.")
                await self._finish_run(run_id, result)
                logger.info("sync.pull.ok run_id=%s remote_state=missing", run_id)
                return result

            bundles_pulled = 0
            conflicts = 0
            if manifest.get("bootstrap_key") and await self._get_state("applied_bootstrap", "0") != "1":
                logger.info("sync.pull.bootstrap.fetch run_id=%s key=%s", run_id, manifest["bootstrap_key"])
                payload = await self.store.get_bytes(manifest["bootstrap_key"])
                if payload:
                    snapshot = decrypt_json(payload, self.config.encryption_passphrase)
                    logger.info(
                        "sync.pull.bootstrap.decrypted run_id=%s device=%s tables=%s",
                        run_id,
                        snapshot.get("device", ""),
                        {name: len(rows) for name, rows in snapshot.get("tables", {}).items()},
                    )
                    snapshot_conflicts = await self._apply_snapshot(snapshot)
                    conflicts += snapshot_conflicts
                    logger.info(
                        "sync.pull.bootstrap.applied run_id=%s conflicts=%s",
                        run_id,
                        snapshot_conflicts,
                    )
                    await self._set_state("applied_bootstrap", "1")
                else:
                    logger.warning("sync.pull.bootstrap.missing run_id=%s key=%s", run_id, manifest["bootstrap_key"])

            applied = set(json.loads(await self._get_state("applied_bundles", "[]") or "[]"))
            for entry in sorted(manifest.get("bundles", []), key=lambda item: item.get("created_at", "")):
                bundle_id = entry["id"]
                if bundle_id in applied:
                    logger.info("sync.pull.bundle.skip_already_applied run_id=%s bundle_id=%s", run_id, bundle_id)
                    continue
                if entry.get("device") == self.config.device_name:
                    logger.info("sync.pull.bundle.skip_own run_id=%s bundle_id=%s", run_id, bundle_id)
                    applied.add(bundle_id)
                    continue
                logger.info(
                    "sync.pull.bundle.fetch run_id=%s bundle_id=%s key=%s device=%s",
                    run_id,
                    bundle_id,
                    entry.get("key"),
                    entry.get("device"),
                )
                payload = await self.store.get_bytes(entry["key"])
                if payload is None:
                    logger.warning("sync.pull.bundle.missing run_id=%s bundle_id=%s key=%s", run_id, bundle_id, entry["key"])
                    continue
                bundle = decrypt_json(payload, self.config.encryption_passphrase)
                logger.info(
                    "sync.pull.bundle.decrypted run_id=%s bundle_id=%s changes=%s",
                    run_id,
                    bundle_id,
                    len(bundle.get("changes", [])),
                )
                applied_count = 0
                for change in bundle.get("changes", []):
                    applied_ok, conflicted = await self._apply_change(change)
                    if applied_ok:
                        applied_count += 1
                    if conflicted:
                        conflicts += 1
                applied.add(bundle_id)
                bundles_pulled += 1
                logger.info(
                    "sync.pull.bundle.applied run_id=%s bundle_id=%s applied=%s conflicts_total=%s",
                    run_id,
                    bundle_id,
                    applied_count,
                    conflicts,
                )

            await self._set_state("applied_bundles", _dumps(sorted(applied)))
            await self._set_state("last_pull_at", _now())
            await self._set_state("last_error", "")
            await self.db.commit()
            message = f"Pulled {bundles_pulled} bundle(s)."
            if conflicts:
                message += f" {conflicts} conflict(s) need review."
            result = SyncResult("pull", "ok", message, bundles_pulled=bundles_pulled, conflicts=conflicts)
            await self._finish_run(run_id, result)
            logger.info(
                "sync.pull.ok run_id=%s bundles_pulled=%s conflicts=%s applied_bundles=%s",
                run_id,
                bundles_pulled,
                conflicts,
                len(applied),
            )
            return result
        except Exception as exc:
            logger.exception("sync.pull.error run_id=%s", run_id)
            result = SyncResult("pull", "error", str(exc))
            await self._set_state("last_error", f"Pull failed: {exc}")
            await self._finish_run(run_id, result)
            return result

    async def run(self) -> SyncResult:
        logger.info("sync.run.start device=%s", self.config.device_name)
        if await self._clear_locked():
            logger.info("sync.run.locked")
            return SyncResult("run", "locked", "Clear/restore is in progress; sync skipped.")
        pulled = await self.pull()
        if pulled.status != "ok":
            logger.warning("sync.run.pull_failed message=%s", pulled.message)
            return pulled
        pushed = await self.push()
        if pushed.status != "ok":
            logger.warning("sync.run.push_failed message=%s", pushed.message)
            return pushed
        result = SyncResult(
            "run",
            "ok",
            f"{pulled.message} {pushed.message}".strip(),
            bundles_pulled=pulled.bundles_pulled,
            changes_pushed=pushed.changes_pushed,
            conflicts=pulled.conflicts,
        )
        logger.info(
            "sync.run.ok bundles_pulled=%s changes_pushed=%s conflicts=%s",
            result.bundles_pulled,
            result.changes_pushed,
            result.conflicts,
        )
        return result

    async def restore_tables(self, table_names: set[str] | list[str] | tuple[str, ...]) -> SyncResult:
        """Rehydrate selected tables from all remote sync state.

        This is used by local-only clear flows. It intentionally replays remote
        bootstrap and bundles for the selected tables without changing normal
        applied-bundle markers, so a scoped clear does not disturb sync state for
        unrelated app areas.
        """
        requested = set(table_names)
        unknown = sorted(requested - set(SYNC_TABLE_BY_NAME))
        if unknown:
            return SyncResult("restore", "error", f"Unknown sync table(s): {', '.join(unknown)}.")

        run_id = await self._start_run("restore")
        logger.info("sync.restore.start run_id=%s device=%s tables=%s", run_id, self.config.device_name, sorted(requested))
        try:
            await self.register_device()
            manifest = await self._load_manifest()
            if not manifest.get("bootstrap_key") and not manifest.get("bundles"):
                result = SyncResult("restore", "ok", "No remote sync state found.")
                await self._finish_run(run_id, result)
                return result

            bundles_pulled = 0
            conflicts = 0
            restored_changes = 0

            await self.db.execute("SAVEPOINT sync_restore_tables")
            if manifest.get("bootstrap_key"):
                logger.info("sync.restore.bootstrap.fetch run_id=%s key=%s", run_id, manifest["bootstrap_key"])
                payload = await self.store.get_bytes(manifest["bootstrap_key"])
                if payload:
                    snapshot = decrypt_json(payload, self.config.encryption_passphrase)
                    for table in SYNC_TABLES:
                        if table.name not in requested:
                            continue
                        for row in snapshot.get("tables", {}).get(table.name, []):
                            row = _normalize_workspace_row(table, row)
                            if not row or table.pk not in row:
                                continue
                            change = {
                                "table": table.name,
                                "record_id": str(row[table.pk]),
                                "op": "UPDATE",
                                "base_revision": 0,
                                "revision": row.get("sync_revision", 1),
                                "origin_device": row.get("sync_origin_device") or snapshot.get("device", ""),
                                "row": row,
                            }
                            applied_ok, conflicted = await self._apply_change(change)
                            if applied_ok:
                                restored_changes += 1
                            if conflicted:
                                conflicts += 1

            for entry in sorted(manifest.get("bundles", []), key=lambda item: item.get("created_at", "")):
                payload = await self.store.get_bytes(entry["key"])
                if payload is None:
                    logger.warning("sync.restore.bundle.missing run_id=%s bundle_id=%s key=%s", run_id, entry.get("id"), entry.get("key"))
                    continue
                bundle = decrypt_json(payload, self.config.encryption_passphrase)
                bundle_applied = 0
                for change in bundle.get("changes", []):
                    if change.get("table") not in requested:
                        continue
                    applied_ok, conflicted = await self._apply_change(change)
                    if applied_ok:
                        restored_changes += 1
                        bundle_applied += 1
                    if conflicted:
                        conflicts += 1
                if bundle_applied:
                    bundles_pulled += 1

            await self._set_state("last_pull_at", _now())
            await self._set_state("last_error", "")
            await self.db.execute("RELEASE SAVEPOINT sync_restore_tables")
            await self.db.commit()
            message = f"Restored {restored_changes} remote change(s) from {bundles_pulled} bundle(s)."
            if conflicts:
                message += f" {conflicts} conflict(s) need review."
            result = SyncResult(
                "restore",
                "ok",
                message,
                bundles_pulled=bundles_pulled,
                changes_pushed=0,
                conflicts=conflicts,
            )
            await self._finish_run(run_id, result)
            logger.info(
                "sync.restore.ok run_id=%s changes=%s bundles=%s conflicts=%s",
                run_id,
                restored_changes,
                bundles_pulled,
                conflicts,
            )
            return result
        except Exception as exc:
            logger.exception("sync.restore.error run_id=%s", run_id)
            try:
                await self.db.execute("ROLLBACK TO SAVEPOINT sync_restore_tables")
                await self.db.execute("RELEASE SAVEPOINT sync_restore_tables")
            except Exception:
                pass
            result = SyncResult("restore", "error", str(exc))
            await self._set_state("last_error", f"Restore failed: {exc}")
            await self._finish_run(run_id, result)
            return result

    async def open_conflicts(self) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT id, table_name, record_id, reason, created_at "
            "FROM sync_conflicts WHERE status = 'open' ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "table_name": r[1], "record_id": r[2], "reason": r[3], "created_at": r[4]}
            for r in rows
        ]

    async def resolve_conflict(self, conflict_id: str, resolution: str) -> SyncResult:
        logger.info("sync.conflict.resolve.start id=%s resolution=%s", conflict_id, resolution)
        cursor = await self.db.execute(
            "SELECT table_name, record_id, local_row, remote_row, remote_change "
            "FROM sync_conflicts WHERE id = ? AND status = 'open'",
            (conflict_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            logger.warning("sync.conflict.resolve.missing id=%s", conflict_id)
            return SyncResult("resolve", "error", "Conflict not found.")

        table_name, record_id, local_raw, remote_raw, remote_change_raw = row
        table = SYNC_TABLE_BY_NAME[table_name]
        local_row = json.loads(local_raw) if local_raw else None
        remote_change = json.loads(remote_change_raw)

        if resolution == "theirs":
            await self._apply_with_suppression(remote_change)
        elif resolution == "mine":
            if local_row:
                local_row["sync_revision"] = int(local_row.get("sync_revision") or 0) + 1
                local_row["updated_at"] = _now()
                local_row["sync_origin_device"] = self.config.device_name
                await self.db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
                try:
                    await self._upsert_row(table, local_row)
                finally:
                    await self.db.execute("UPDATE sync_runtime SET value = '0' WHERE key = 'suppress'")
                await self._queue_manual_change(table, str(local_row[table.pk]), "UPDATE", local_row)
        elif resolution == "both":
            if not table.duplicable or local_row is None:
                return SyncResult("resolve", "error", "Keep both is not available for this record.")
            await self._duplicate_row(table, local_row)
        else:
            return SyncResult("resolve", "error", "Unknown resolution.")

        await self.db.execute(
            "UPDATE sync_conflicts SET status = 'resolved', resolution = ?, "
            "resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (resolution, conflict_id),
        )
        await self.db.commit()
        logger.info("sync.conflict.resolve.ok id=%s resolution=%s table=%s record_id=%s", conflict_id, resolution, table_name, record_id)
        return SyncResult("resolve", "ok", "Conflict resolved.")

    async def _load_manifest(self) -> dict:
        manifest = await self.store.get_json(MANIFEST_KEY)
        if manifest is None:
            logger.info("sync.manifest.missing key=%s", MANIFEST_KEY)
            return {"version": 1, "bootstrap_key": "", "bundles": [], "updated_at": ""}
        logger.info(
            "sync.manifest.loaded key=%s bootstrap=%s bundles=%s updated_at=%s",
            MANIFEST_KEY,
            bool(manifest.get("bootstrap_key")),
            len(manifest.get("bundles", [])),
            manifest.get("updated_at", ""),
        )
        return manifest

    async def _upload_bootstrap(self, manifest: dict) -> None:
        snapshot = {
            "version": 1,
            "device": self.config.device_name,
            "created_at": _now(),
            "tables": {},
        }
        for table in SYNC_TABLES:
            snapshot["tables"][table.name] = await self._all_rows(table)
        table_counts = {name: len(rows) for name, rows in snapshot["tables"].items()}
        logger.info("sync.bootstrap.upload.start device=%s table_counts=%s", self.config.device_name, table_counts)
        await self.store.put_bytes(
            BOOTSTRAP_KEY,
            encrypt_json(snapshot, self.config.encryption_passphrase),
            "application/octet-stream",
        )
        manifest["bootstrap_key"] = BOOTSTRAP_KEY
        manifest["created_by"] = self.config.device_name
        manifest["updated_at"] = snapshot["created_at"]
        await self.store.put_json(MANIFEST_KEY, manifest)
        logger.info("sync.bootstrap.upload.ok key=%s table_counts=%s", BOOTSTRAP_KEY, table_counts)

    async def _apply_snapshot(self, snapshot: dict) -> int:
        conflicts = 0
        for table in SYNC_TABLES:
            for row in snapshot.get("tables", {}).get(table.name, []):
                row = _normalize_workspace_row(table, row)
                if not row or table.pk not in row:
                    continue
                change = {
                    "table": table.name,
                    "record_id": str(row[table.pk]),
                    "op": "UPDATE",
                    "base_revision": 0,
                    "revision": row.get("sync_revision", 1),
                    "origin_device": row.get("sync_origin_device") or snapshot.get("device", ""),
                    "row": row,
                }
                _, conflicted = await self._apply_change(change)
                if conflicted:
                    conflicts += 1
        logger.info("sync.snapshot.apply.done conflicts=%s", conflicts)
        return conflicts

    async def _pending_changes(self) -> tuple[list[dict], int]:
        cursor = await self.db.execute(
            "SELECT id, table_name, record_id, op, base_revision, local_revision, origin_device "
            "FROM sync_changes WHERE sent_at IS NULL ORDER BY id"
        )
        rows = await cursor.fetchall()
        if not rows:
            logger.info("sync.pending.none")
            return [], 0

        latest: dict[tuple[str, str], tuple] = {}
        max_id = 0
        for row in rows:
            max_id = max(max_id, row[0])
            latest[(row[1], row[2])] = row

        changes = []
        for (_, _), row in latest.items():
            _, table_name, record_id, op, base_revision, local_revision, origin_device = row
            table = SYNC_TABLE_BY_NAME[table_name]
            current = await self._row_by_id(table, record_id)
            effective_op = op if current is not None else "DELETE"
            changes.append({
                "table": table_name,
                "record_id": record_id,
                "op": effective_op,
                "base_revision": base_revision,
                "revision": local_revision if current is None else current.get("sync_revision", local_revision),
                "origin_device": origin_device,
                "row": current,
            })
        by_table: dict[str, int] = {}
        for change in changes:
            by_table[change["table"]] = by_table.get(change["table"], 0) + 1
        logger.info("sync.pending.compacted raw=%s effective=%s by_table=%s", len(rows), len(changes), by_table)
        return changes, max_id

    async def _drop_prebootstrap_stale_deletes(self) -> None:
        """Discard local wipe noise before this device has ever synced.

        Clearing data after sync triggers exist creates a delete entry for every
        old row. Before the first pull/push, those rows do not represent remote
        state yet, so showing them as pending work is confusing.
        """
        if await self._get_state("last_push_at", "") or await self._get_state("last_pull_at", ""):
            return
        cursor = await self.db.execute(
            "SELECT DISTINCT table_name, record_id FROM sync_changes WHERE sent_at IS NULL"
        )
        stale: list[tuple[str, str]] = []
        for table_name, record_id in await cursor.fetchall():
            table = SYNC_TABLE_BY_NAME.get(table_name)
            if table is None:
                continue
            if await self._row_by_id(table, record_id) is None:
                stale.append((table_name, record_id))
        for table_name, record_id in stale:
            await self.db.execute(
                "DELETE FROM sync_changes WHERE sent_at IS NULL AND table_name = ? AND record_id = ?",
                (table_name, record_id),
            )
        if stale:
            await self.db.commit()
            logger.info("sync.pending.pruned_stale count=%s", len(stale))

    async def _apply_change(self, change: dict) -> tuple[bool, bool]:
        table = SYNC_TABLE_BY_NAME[change["table"]]
        if change.get("row") is not None:
            change = {**change, "row": _normalize_workspace_row(table, change.get("row"))}
            if change["row"] is None and change["op"] != "DELETE":
                logger.info(
                    "sync.change.apply.skip_incompatible table=%s record_id=%s op=%s",
                    table.name,
                    change.get("record_id"),
                    change.get("op"),
                )
                return True, False
            if change["row"] and change["record_id"] not in {change["row"].get(table.pk), str(change["row"].get(table.pk))}:
                change["record_id"] = str(change["row"].get(table.pk))
        record_id = str(change["record_id"])
        local = await self._row_by_id(table, record_id)
        remote = change.get("row")

        if local is None:
            if not await self._apply_or_skip_invalid(change):
                return True, False
            logger.info("sync.change.apply.ok table=%s record_id=%s op=%s reason=no_local_row", table.name, record_id, change["op"])
            return True, False

        if change["op"] == "DELETE":
            if int(local.get("sync_revision") or 0) <= int(change.get("base_revision") or 0):
                if not await self._apply_or_skip_invalid(change):
                    return True, False
                logger.info("sync.change.apply.ok table=%s record_id=%s op=DELETE", table.name, record_id)
                return True, False
            await self._queue_conflict(table, record_id, local, remote, change, "Local row changed after remote delete.")
            return False, True

        if _hash_row(local) == _hash_row(remote):
            logger.info("sync.change.apply.skip_identical table=%s record_id=%s", table.name, record_id)
            return True, False

        local_rev = int(local.get("sync_revision") or 0)
        base_rev = int(change.get("base_revision") or 0)
        remote_rev = int(change.get("revision") or 0)
        if local_rev <= base_rev or (
            local.get("sync_origin_device") == change.get("origin_device")
            and local_rev < remote_rev
        ):
            if not await self._apply_or_skip_invalid(change):
                return True, False
            logger.info(
                "sync.change.apply.ok table=%s record_id=%s op=%s local_rev=%s base_rev=%s remote_rev=%s",
                table.name,
                record_id,
                change["op"],
                local_rev,
                base_rev,
                remote_rev,
            )
            return True, False

        await self._queue_conflict(table, record_id, local, remote, change, "Both devices changed this row.")
        return False, True

    async def _apply_or_skip_invalid(self, change: dict) -> bool:
        """Apply a remote change, or skip it if it cannot satisfy local schema.

        Sync payloads can outlive schema changes. A single legacy row with a
        missing NOT NULL field, invalid CHECK value, or broken FK should not
        poison the entire pull. Returning False means "treat this remote change
        as consumed but not applied locally."
        """
        try:
            await self._apply_with_suppression(change)
            return True
        except sqlite3.IntegrityError as exc:
            logger.warning(
                "sync.change.apply.skip_constraint table=%s record_id=%s op=%s error=%s",
                change.get("table"),
                change.get("record_id"),
                change.get("op"),
                exc,
            )
            return False

    async def _apply_with_suppression(self, change: dict) -> None:
        table = SYNC_TABLE_BY_NAME[change["table"]]
        previous_suppress = await self._get_runtime("suppress", "0")
        await self.db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
        try:
            if change["op"] == "DELETE":
                logger.info("sync.change.db.delete table=%s record_id=%s", table.name, change["record_id"])
                await self.db.execute(f"DELETE FROM {table.name} WHERE {table.pk} = ?", (change["record_id"],))
            else:
                logger.info("sync.change.db.upsert table=%s record_id=%s", table.name, change["record_id"])
                await self._upsert_row(table, change["row"])
        finally:
            await self.db.execute("UPDATE sync_runtime SET value = ? WHERE key = 'suppress'", (previous_suppress,))

    async def _upsert_row(self, table: SyncTable, row: dict) -> None:
        columns = await self._table_columns(table.name)
        usable = [col for col in columns if col in row]
        placeholders = ", ".join("?" for _ in usable)
        quoted = ", ".join(usable)
        updates = ", ".join(
            f"{col} = excluded.{col}" for col in usable if col != table.pk
        )
        sql = (
            f"INSERT INTO {table.name} ({quoted}) VALUES ({placeholders}) "
            f"ON CONFLICT({table.pk}) DO UPDATE SET {updates}"
        )
        await self.db.execute(sql, tuple(row[col] for col in usable))

    async def _duplicate_row(self, table: SyncTable, row: dict) -> None:
        duplicate = dict(row)
        duplicate[table.pk] = uuid.uuid4().hex[:8]
        if table.name == "quests":
            duplicate["title"] = f"{duplicate.get('title', 'Untitled')} (copy)"
            duplicate["created_at"] = _now()
        duplicate["updated_at"] = _now()
        duplicate["sync_revision"] = 1
        duplicate["sync_origin_device"] = self.config.device_name
        duplicate["deleted_at"] = None
        await self._queue_manual_change(table, str(duplicate[table.pk]), "INSERT", duplicate)
        await self.db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
        try:
            await self._upsert_row(table, duplicate)
        finally:
            await self.db.execute("UPDATE sync_runtime SET value = '0' WHERE key = 'suppress'")

    async def _queue_manual_change(self, table: SyncTable, record_id: str, op: str, row: dict | None) -> None:
        await self.db.execute(
            "INSERT INTO sync_changes (table_name, record_id, op, base_revision, local_revision, origin_device, row_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                table.name,
                record_id,
                op,
                int((row or {}).get("sync_revision") or 0),
                int((row or {}).get("sync_revision") or 0) + 1,
                self.config.device_name,
                _dumps(row) if row else None,
            ),
        )
        logger.info("sync.change.manual_queued table=%s record_id=%s op=%s", table.name, record_id, op)

    async def _queue_conflict(
        self,
        table: SyncTable,
        record_id: str,
        local: dict | None,
        remote: dict | None,
        change: dict,
        reason: str,
    ) -> None:
        conflict_id = hashlib.sha256(
            f"{table.name}:{record_id}:{_dumps(change)}".encode("utf-8")
        ).hexdigest()[:16]
        await self.db.execute(
            "INSERT OR IGNORE INTO sync_conflicts "
            "(id, table_name, record_id, local_row, remote_row, remote_change, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conflict_id,
                table.name,
                record_id,
                _dumps(local) if local else None,
                _dumps(remote) if remote else None,
                _dumps(change),
                reason,
            ),
        )
        logger.warning(
            "sync.conflict.queued id=%s table=%s record_id=%s reason=%s local_rev=%s remote_rev=%s",
            conflict_id,
            table.name,
            record_id,
            reason,
            (local or {}).get("sync_revision"),
            (remote or {}).get("sync_revision"),
        )

    async def _all_rows(self, table: SyncTable) -> list[dict]:
        cursor = await self.db.execute(f"SELECT * FROM {table.name} ORDER BY {table.pk}")
        rows = await cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]

    async def _row_by_id(self, table: SyncTable, record_id: str) -> dict | None:
        cursor = await self.db.execute(f"SELECT * FROM {table.name} WHERE {table.pk} = ?", (record_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))

    async def _table_columns(self, table_name: str) -> list[str]:
        cursor = await self.db.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        return [row[1] for row in rows]

    async def _get_state(self, key: str, default: str = "") -> str:
        cursor = await self.db.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default

    async def _set_state(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (key, value),
        )

    async def _get_runtime(self, key: str, default: str = "") -> str:
        cursor = await self.db.execute("SELECT value FROM sync_runtime WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default

    async def _clear_locked(self) -> bool:
        return await self._get_runtime("clear_lock", "0") == "1"

    async def _scalar(self, sql: str) -> Any:
        cursor = await self.db.execute(sql)
        row = await cursor.fetchone()
        return row[0] if row else None

    async def _start_run(self, action: str) -> int:
        cursor = await self.db.execute(
            "INSERT INTO sync_runs (action, status) VALUES (?, 'running')",
            (action,),
        )
        await self.db.commit()
        logger.info("sync.run_record.start id=%s action=%s", cursor.lastrowid, action)
        return cursor.lastrowid

    async def _finish_run(self, run_id: int, result: SyncResult) -> None:
        await self.db.execute(
            "UPDATE sync_runs SET status = ?, message = ?, bundles_pulled = ?, "
            "changes_pushed = ?, conflicts = ?, finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE id = ?",
            (
                result.status,
                result.message,
                result.bundles_pulled,
                result.changes_pushed,
                result.conflicts,
                run_id,
            ),
        )
        await self.db.commit()
        logger.info(
            "sync.run_record.finish id=%s action=%s status=%s pulled=%s pushed=%s conflicts=%s message=%s",
            run_id,
            result.action,
            result.status,
            result.bundles_pulled,
            result.changes_pushed,
            result.conflicts,
            result.message,
        )
