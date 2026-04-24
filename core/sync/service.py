"""SQLite logical sync service."""

from __future__ import annotations

import hashlib
import json
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
        await self._set_state("device_name", self.config.device_name)
        await self.db.execute(
            "INSERT INTO sync_devices (name) VALUES (?) "
            "ON CONFLICT(name) DO UPDATE SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (self.config.device_name,),
        )
        await self.db.commit()

    async def status(self) -> dict:
        await self._drop_prebootstrap_stale_deletes()
        changes, _ = await self._pending_changes()
        pending = len(changes)
        conflicts = await self._scalar("SELECT COUNT(*) FROM sync_conflicts WHERE status = 'open'")
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
        try:
            await self.register_device()
            manifest = await self._load_manifest()
            if not manifest.get("bootstrap_key"):
                await self._upload_bootstrap(manifest)

            changes, max_change_id = await self._pending_changes()
            if not changes:
                await self._set_state("last_push_at", _now())
                result = SyncResult("push", "ok", "No local changes to push.")
                await self._finish_run(run_id, result)
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
            manifest.setdefault("bundles", []).append({
                "id": bundle_id,
                "key": key,
                "device": self.config.device_name,
                "created_at": now,
                "change_count": len(changes),
            })
            manifest["updated_at"] = now
            await self.store.put_json(MANIFEST_KEY, manifest)
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
            return result
        except Exception as exc:
            result = SyncResult("push", "error", str(exc))
            await self._set_state("last_error", "Push failed.")
            await self._finish_run(run_id, result)
            return result

    async def pull(self) -> SyncResult:
        run_id = await self._start_run("pull")
        try:
            await self.register_device()
            manifest = await self._load_manifest()
            if not manifest:
                result = SyncResult("pull", "ok", "No remote sync state found.")
                await self._finish_run(run_id, result)
                return result

            bundles_pulled = 0
            conflicts = 0
            if manifest.get("bootstrap_key") and await self._get_state("applied_bootstrap", "0") != "1":
                payload = await self.store.get_bytes(manifest["bootstrap_key"])
                if payload:
                    snapshot = decrypt_json(payload, self.config.encryption_passphrase)
                    conflicts += await self._apply_snapshot(snapshot)
                    await self._set_state("applied_bootstrap", "1")

            applied = set(json.loads(await self._get_state("applied_bundles", "[]") or "[]"))
            for entry in sorted(manifest.get("bundles", []), key=lambda item: item.get("created_at", "")):
                bundle_id = entry["id"]
                if bundle_id in applied:
                    continue
                if entry.get("device") == self.config.device_name:
                    applied.add(bundle_id)
                    continue
                payload = await self.store.get_bytes(entry["key"])
                if payload is None:
                    continue
                bundle = decrypt_json(payload, self.config.encryption_passphrase)
                for change in bundle.get("changes", []):
                    applied_ok, conflicted = await self._apply_change(change)
                    if conflicted:
                        conflicts += 1
                applied.add(bundle_id)
                bundles_pulled += 1

            await self._set_state("applied_bundles", _dumps(sorted(applied)))
            await self._set_state("last_pull_at", _now())
            await self._set_state("last_error", "")
            await self.db.commit()
            message = f"Pulled {bundles_pulled} bundle(s)."
            if conflicts:
                message += f" {conflicts} conflict(s) need review."
            result = SyncResult("pull", "ok", message, bundles_pulled=bundles_pulled, conflicts=conflicts)
            await self._finish_run(run_id, result)
            return result
        except Exception as exc:
            result = SyncResult("pull", "error", str(exc))
            await self._set_state("last_error", "Pull failed.")
            await self._finish_run(run_id, result)
            return result

    async def run(self) -> SyncResult:
        pulled = await self.pull()
        if pulled.status != "ok":
            return pulled
        pushed = await self.push()
        if pushed.status != "ok":
            return pushed
        return SyncResult(
            "run",
            "ok",
            f"{pulled.message} {pushed.message}".strip(),
            bundles_pulled=pulled.bundles_pulled,
            changes_pushed=pushed.changes_pushed,
            conflicts=pulled.conflicts,
        )

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
        cursor = await self.db.execute(
            "SELECT table_name, record_id, local_row, remote_row, remote_change "
            "FROM sync_conflicts WHERE id = ? AND status = 'open'",
            (conflict_id,),
        )
        row = await cursor.fetchone()
        if row is None:
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
        return SyncResult("resolve", "ok", "Conflict resolved.")

    async def _load_manifest(self) -> dict:
        manifest = await self.store.get_json(MANIFEST_KEY)
        if manifest is None:
            return {"version": 1, "bootstrap_key": "", "bundles": [], "updated_at": ""}
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
        await self.store.put_bytes(
            BOOTSTRAP_KEY,
            encrypt_json(snapshot, self.config.encryption_passphrase),
            "application/octet-stream",
        )
        manifest["bootstrap_key"] = BOOTSTRAP_KEY
        manifest["created_by"] = self.config.device_name
        manifest["updated_at"] = snapshot["created_at"]
        await self.store.put_json(MANIFEST_KEY, manifest)

    async def _apply_snapshot(self, snapshot: dict) -> int:
        conflicts = 0
        for table in SYNC_TABLES:
            for row in snapshot.get("tables", {}).get(table.name, []):
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
        return conflicts

    async def _pending_changes(self) -> tuple[list[dict], int]:
        cursor = await self.db.execute(
            "SELECT id, table_name, record_id, op, base_revision, local_revision, origin_device "
            "FROM sync_changes WHERE sent_at IS NULL ORDER BY id"
        )
        rows = await cursor.fetchall()
        if not rows:
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

    async def _apply_change(self, change: dict) -> tuple[bool, bool]:
        table = SYNC_TABLE_BY_NAME[change["table"]]
        record_id = str(change["record_id"])
        local = await self._row_by_id(table, record_id)
        remote = change.get("row")

        if local is None:
            await self._apply_with_suppression(change)
            return True, False

        if change["op"] == "DELETE":
            if int(local.get("sync_revision") or 0) <= int(change.get("base_revision") or 0):
                await self._apply_with_suppression(change)
                return True, False
            await self._queue_conflict(table, record_id, local, remote, change, "Local row changed after remote delete.")
            return False, True

        if _hash_row(local) == _hash_row(remote):
            return True, False

        local_rev = int(local.get("sync_revision") or 0)
        base_rev = int(change.get("base_revision") or 0)
        remote_rev = int(change.get("revision") or 0)
        if local_rev <= base_rev or (
            local.get("sync_origin_device") == change.get("origin_device")
            and local_rev < remote_rev
        ):
            await self._apply_with_suppression(change)
            return True, False

        await self._queue_conflict(table, record_id, local, remote, change, "Both devices changed this row.")
        return False, True

    async def _apply_with_suppression(self, change: dict) -> None:
        table = SYNC_TABLE_BY_NAME[change["table"]]
        await self.db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
        try:
            if change["op"] == "DELETE":
                await self.db.execute(f"DELETE FROM {table.name} WHERE {table.pk} = ?", (change["record_id"],))
            else:
                await self._upsert_row(table, change["row"])
        finally:
            await self.db.execute("UPDATE sync_runtime SET value = '0' WHERE key = 'suppress'")

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
