"""FastAPI application — QuestLog Web."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

from web.db import get_db, migrate

_WEB_DIR = Path(__file__).parent
_TEMPLATE_DIRS = [
    str(_WEB_DIR / "shared" / "templates"),
    str(_WEB_DIR / "quests" / "templates"),
    str(_WEB_DIR / "pomos" / "templates"),
    str(_WEB_DIR / "chronicle" / "templates"),
    str(_WEB_DIR / "trophies" / "templates"),
    str(_WEB_DIR / "dashboard" / "templates"),
    str(_WEB_DIR / "challenge" / "templates"),
    str(_WEB_DIR / "artifact_keys" / "templates"),
    str(_WEB_DIR / "sync" / "templates"),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open DB, run migrations
    db = await get_db()
    await migrate(db)
    app.state.db = db
    try:
        from core.sync.config import load_sync_config
        sync_config = load_sync_config()
        app.state.sync_config = sync_config
        app.state.sync_config_error = ""
        if sync_config.enabled:
            await db.execute(
                "INSERT INTO sync_state (key, value) VALUES ('device_name', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
                (sync_config.device_name,),
            )
            await db.execute(
                "INSERT INTO sync_devices (name) VALUES (?) "
                "ON CONFLICT(name) DO UPDATE SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
                (sync_config.device_name,),
            )
            await db.commit()
            if sync_config.auto_enabled and sync_config.interval_seconds > 0:
                app.state.sync_task = asyncio.create_task(_sync_loop(app))
    except Exception:
        app.state.sync_config = None
        app.state.sync_config_error = "Sync configuration is invalid."
    yield
    sync_task = getattr(app.state, "sync_task", None)
    if sync_task is not None:
        sync_task.cancel()
    # Shutdown: close DB + engine
    from web.pomos.engine import shutdown_engine
    shutdown_engine()
    await db.close()


async def _sync_loop(app: FastAPI) -> None:
    """Best-effort periodic sync while the web app is running."""
    from core.sync.service import SyncService
    from core.sync.store import build_store

    while True:
        config = getattr(app.state, "sync_config", None)
        interval = config.interval_seconds if config else 0
        await asyncio.sleep(max(interval, 5))
        try:
            await SyncService(app.state.db, config, build_store(config)).run()
        except asyncio.CancelledError:
            raise
        except Exception:
            try:
                await app.state.db.execute(
                    "INSERT INTO sync_state (key, value) VALUES ('last_error', 'Periodic sync failed.') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                )
                await app.state.db.commit()
            except Exception:
                pass


app = FastAPI(title="QuestLog", lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory=str(_WEB_DIR / "static")), name="static")

# Jinja2 templates — FileSystemLoader searches dirs in order
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIRS),
    autoescape=True,
)
templates = Jinja2Templates(env=_jinja_env)


def _sync_ui_poll_seconds() -> int:
    try:
        from core.sync.config import load_sync_config
        return load_sync_config().ui_poll_seconds
    except Exception:
        return 60


_jinja_env.globals["sync_ui_poll_seconds"] = _sync_ui_poll_seconds

# Register routers
from web.quests.routes import router as quest_router  # noqa: E402
from web.pomos.routes import router as pomo_router  # noqa: E402
from web.pomos.sse import router as sse_router  # noqa: E402
from web.chronicle.routes import router as chronicle_router  # noqa: E402
from web.trophies.routes import router as trophy_router  # noqa: E402
from web.dashboard.routes import router as dashboard_router  # noqa: E402
from web.challenge.routes import router as challenge_router  # noqa: E402
from web.artifact_keys.routes import router as artifact_keys_router  # noqa: E402
from web.sync.routes import router as sync_router  # noqa: E402

app.include_router(quest_router)
app.include_router(pomo_router)
app.include_router(sse_router)
app.include_router(chronicle_router)
app.include_router(trophy_router)
app.include_router(dashboard_router)
app.include_router(challenge_router)
app.include_router(artifact_keys_router)
app.include_router(sync_router)

# Test mode — dev-only, gated by TEST_MODE env var
from core import clock  # noqa: E402
if clock.is_test_mode():
    from web.test_mode.routes import router as test_mode_router  # noqa: E402
    app.include_router(test_mode_router)

_jinja_env.globals["test_mode_enabled"] = clock.is_test_mode

from core.utils import is_url as _is_url  # noqa: E402
_jinja_env.globals["is_url"] = _is_url


@app.get("/health")
async def health_check():
    """Liveness + readiness probe."""
    try:
        db = app.state.db
        await db.execute("SELECT 1")
        return JSONResponse({"status": "ok"})
    except Exception:
        return JSONResponse({"status": "error", "detail": "db unreachable"}, status_code=503)
