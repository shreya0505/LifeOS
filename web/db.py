"""SQLite database connection and migration management."""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
_DEFAULT_DB = Path(__file__).parent.parent / "questlog.db"

DB_PATH = Path(os.environ.get("QUESTLOG_DB", str(_DEFAULT_DB)))


async def get_db() -> aiosqlite.Connection:
    """Open a connection with WAL mode and FK enforcement."""
    db = await aiosqlite.connect(str(DB_PATH))
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def migrate(db: aiosqlite.Connection) -> None:
    """Run unapplied SQL migrations in order."""
    # Ensure _migrations table exists (bootstrap)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS _migrations ("
        "  id INTEGER PRIMARY KEY,"
        "  filename TEXT NOT NULL UNIQUE,"
        "  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))"
        ")"
    )
    await db.commit()

    # Find applied migrations
    cursor = await db.execute("SELECT filename FROM _migrations")
    applied = {row[0] for row in await cursor.fetchall()}

    # Run unapplied migrations in sorted order
    if not _MIGRATIONS_DIR.exists():
        return

    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.name in applied:
            continue
        sql = sql_file.read_text()
        await db.executescript(sql)
        await db.execute(
            "INSERT INTO _migrations (filename) VALUES (?)",
            (sql_file.name,),
        )
        await db.commit()
