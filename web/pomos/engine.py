"""Pomo engine singleton for the web app.

Single-user, single-process. The engine lives in-memory for the lifetime
of the server. It uses a sync SQLite connection (separate from the async
one used by analytics routes) because PomoEngine calls repo methods
synchronously.
"""

from __future__ import annotations

from core.pomo_engine import PomoEngine
from core.storage.sync_sqlite_backend import SyncSqlitePomoRepo
import web.db as db_mod

_engine: PomoEngine | None = None
_sync_repo: SyncSqlitePomoRepo | None = None


def get_engine() -> PomoEngine:
    """Get or create the singleton PomoEngine."""
    global _engine, _sync_repo
    if _engine is None:
        _sync_repo = SyncSqlitePomoRepo(str(db_mod.DB_PATH))
        _engine = PomoEngine(_sync_repo)
    return _engine


def shutdown_engine() -> None:
    """Close the sync repo connection on app shutdown."""
    global _engine, _sync_repo
    if _sync_repo is not None:
        _sync_repo.close()
        _sync_repo = None
    _engine = None
