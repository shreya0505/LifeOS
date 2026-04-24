"""FastAPI application — QuestLog Web."""

from __future__ import annotations

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
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open DB, run migrations
    db = await get_db()
    await migrate(db)
    app.state.db = db
    yield
    # Shutdown: close DB + engine
    from web.pomos.engine import shutdown_engine
    shutdown_engine()
    await db.close()


app = FastAPI(title="QuestLog", lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory=str(_WEB_DIR / "static")), name="static")

# Jinja2 templates — FileSystemLoader searches dirs in order
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIRS),
    autoescape=True,
)
templates = Jinja2Templates(env=_jinja_env)

# Register routers
from web.quests.routes import router as quest_router  # noqa: E402
from web.pomos.routes import router as pomo_router  # noqa: E402
from web.pomos.sse import router as sse_router  # noqa: E402
from web.chronicle.routes import router as chronicle_router  # noqa: E402
from web.trophies.routes import router as trophy_router  # noqa: E402
from web.dashboard.routes import router as dashboard_router  # noqa: E402
from web.challenge.routes import router as challenge_router  # noqa: E402
from web.artifact_keys.routes import router as artifact_keys_router  # noqa: E402

app.include_router(quest_router)
app.include_router(pomo_router)
app.include_router(sse_router)
app.include_router(chronicle_router)
app.include_router(trophy_router)
app.include_router(dashboard_router)
app.include_router(challenge_router)
app.include_router(artifact_keys_router)

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
