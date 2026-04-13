# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# First-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install textual rich fastapi uvicorn[standard] jinja2 aiosqlite sse-starlette httpx python-multipart

# Run TUI
python3 -m tui

# Run Web app
uvicorn web.app:app --reload

# Run with Docker
docker compose up --build

# Reset all data (creates backups first)
./clear_data.sh
```

Requires Python 3.10+.

### Testing

```bash
pip install pytest pytest-asyncio httpx aiosqlite

# Run all tests
pytest

# Run a single test file
pytest tests/test_web_routes.py

# Run a specific test
pytest tests/test_web_routes.py::test_add_quest -v
```

Tests use a temp SQLite DB via the `db` and `client` fixtures in `tests/conftest.py`. The `client` fixture yields an `httpx.AsyncClient` wired to the FastAPI app.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `QUESTLOG_DB` | `./questlog.db` | SQLite database path |

## Architecture

QuestLog has two frontends (TUI and Web) that share a common core layer.

```
core/           ← shared business logic + storage
  config.py     ← all tuneable values (timezone, pomo durations, quest state machine)
  storage/
    protocols.py    ← QuestRepo / PomoRepo / TrophyPRRepo Protocol interfaces
    json_backend.py ← JSON file storage (used by TUI)
    sqlite_backend.py ← async SQLite storage (used by Web)
  pomo_engine.py    ← timer state machine (charge → timer → deed → break_choice)
  pomo_queries.py   ← read-only analytics (keep new pomo analytics here)
  metrics.py        ← quest/pomo metric computations
  trophy_defs.py    ← trophy definitions
  trophy_compute.py ← trophy evaluation logic
  utils.py          ← format_duration, fantasy_date, date helpers

tui/            ← Textual TUI app (reads/writes JSON files)
  main.py       ← QuestLogApp: owns state, bindings, action handlers
  quest_panel.py, chronicle_panel.py, trophy_panel.py, pomo_panel.py
  modals.py, renderers.py, styles.tcss

web/            ← FastAPI + HTMX + Alpine.js web app (uses SQLite via aiosqlite)
  app.py        ← FastAPI app, lifespan, template setup, router registration
  db.py         ← SQLite connection (get_db) and migration runner
  deps.py       ← FastAPI dependency injection for repos
  quests/       ← quest board routes + templates
  pomos/        ← pomo flow routes + SSE timer + templates
  chronicle/    ← pomo history panel
  trophies/     ← trophy display
  dashboard/    ← dashboard modal
  shared/templates/ ← base.html layout, shared components
  static/       ← CSS (tokens.css, reset.css, style.css), JS (htmx, Alpine), fonts
```

### Storage Pattern

Both frontends use the same `Protocol` interfaces defined in `core/storage/protocols.py` (`QuestRepo`, `PomoRepo`, `TrophyPRRepo`). The TUI uses `json_backend.py` (sync, file-based), the web uses `sqlite_backend.py` (async, aiosqlite). Web dependencies are injected via `web/deps.py`.

### Database & Migrations

SQLite with WAL mode and foreign keys enabled. Schema lives in `migrations/001_initial.sql`. The migration runner in `web/db.py` auto-applies `migrations/*.sql` files in sorted order on startup, tracked by the `_migrations` table.

### Web Stack

FastAPI + Jinja2 templates + HTMX for interactivity + Alpine.js for client-side state. SSE for live pomo timer updates (`web/pomos/sse.py`). Each feature module has its own `routes.py` and `templates/` directory. Templates are discovered from all module template directories via `FileSystemLoader`.

### Quest Status Machine

```
log → active → done
log → blocked → active → done
any status → delete
```

Valid transitions defined in `core/config.py` as `VALID_SOURCES`.

### Pomodoro Flow

Modes cycle: `charge → timer → deed → break_choice → charge`. The pomo engine (`core/pomo_engine.py`) manages timer state. Segment types stored as `"work"` / `"short_break"` / `"long_break"`. `"extended_break"` is UI-only, stored as `short_break` + `break_size: "extended"`. Forge types: `hollow` (subpar) and `berserker` (over-extended).

### Timezone

All timestamps stored as UTC ISO strings. Display conversion uses `USER_TZ` in `core/config.py` (default: `Asia/Kolkata`).

### Feature Specs

`features/` contains product specs and PRDs. Consult these before implementing new pomodoro or gamification features — they document intentional design decisions around the charge/deed loop and War Room UX.
