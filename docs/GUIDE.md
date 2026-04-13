# QuestLog — User Guide

> Complete guide for spinning up and using both the TUI and Web interfaces.

---

## Prerequisites

- **Python 3.10+** (for TUI or local Web)
- **Docker + Docker Compose** (for containerized Web only)

---

## Option A — Terminal UI (TUI)

The TUI is a keyboard-driven terminal app backed by local JSON files. No server required.

### Setup

```bash
cd LifeOS

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install textual rich
```

### Run

```bash
python3 -m tui
```

### Data

TUI stores all data in `data/tui/`:

| File | Contents |
|---|---|
| `data/tui/quests.json` | All quests and their state |
| `data/tui/pomodoros.json` | All pomo sessions and segments |
| `data/tui/trophies.json` | Personal records for trophies |

The `data/tui/` directory is created automatically on first run. Gitignored by default.

### Reset Data

```bash
./scripts/clear_data.sh
```

Prompts for confirmation, creates timestamped backups in `data/backups/`, then resets to empty state.

---

## Option B — Web Application (Local)

The Web UI is a FastAPI app with HTMX + Alpine.js, backed by SQLite. Runs in browser.

### Setup

```bash
cd LifeOS

python3 -m venv .venv
source .venv/bin/activate

pip install fastapi "uvicorn[standard]" jinja2 aiosqlite sse-starlette httpx
```

### Run

```bash
uvicorn web.app:app --reload
```

Open: `http://127.0.0.1:8000`

### Database

SQLite database at `data/web/questlog.db` by default. The directory is created automatically. Override path with env var:

```bash
QUESTLOG_DB=/custom/path/questlog.db uvicorn web.app:app --reload
```

Schema migrations run automatically on startup from `migrations/*.sql`.

### Reset Data

```bash
./scripts/clear_sql_data.sh
```

Backs up the DB to `data/backups/`, then deletes all rows (schema intact).

---

## Option C — Docker (Web App)

The Docker route runs the Web UI in a container with persistent data in a named volume. Recommended for running as a service.

### Run

```bash
docker compose up --build
```

Open: `http://localhost:8000`

First build downloads dependencies and copies app code. Subsequent starts are fast.

### Data Persistence

Data is stored in the `questlog-data` Docker volume at `/app/data/questlog.db` inside the container. The volume persists across container restarts and rebuilds.

```bash
# View volume
docker volume inspect lifeos_questlog-data

# Stop without deleting data
docker compose down

# Stop AND delete all data
docker compose down -v
```

### Environment Variables (Docker)

Defined in `docker-compose.yml`. Override by passing `-e` flags or adding a `.env` file:

| Variable | Default (Docker) | Purpose |
|---|---|---|
| `QUESTLOG_DB` | `/app/data/questlog.db` | SQLite database path inside container |

### Health Check

The container has a built-in health check hitting `http://localhost:8000/health` every 30s. Check container status:

```bash
docker compose ps
```

---

## Environment Variables Reference

| Variable | Default | Purpose |
|---|---|---|
| `QUESTLOG_DB` | `./questlog.db` | SQLite path (Web only). TUI uses JSON files. |

---

## Running Tests

```bash
pip install pytest pytest-asyncio httpx aiosqlite

# All tests
pytest

# Single file
pytest tests/test_web_routes.py

# Single test, verbose
pytest tests/test_web_routes.py::test_add_quest -v
```

Tests use an isolated in-memory SQLite DB via fixtures in `tests/conftest.py`. They never touch production data.

---

## TUI — Navigation & Keys

### Global

| Key | Action |
|---|---|
| `q` | Quit |
| `r` | Refresh all panels |
| `Esc` | Close modal / hide pomo panel |
| `o` | Open dashboard |
| `p` | Daily receipt |

### Quest Roster

| Key | Action |
|---|---|
| `↑` / `↓` | Move selection |
| `a` | Add new quest |
| `Enter` | Activate quest |
| `b` | Block quest |
| `u` | Unblock quest |
| `d` | Mark done |
| `x` | Delete quest |
| `f` | Toggle Frog flag (`🐸`) |
| `t` | Start pomodoro (on active quest) |

### Pomodoro — During Work

| Key | Action |
|---|---|
| `c` | Swift finish (complete early) |
| `i` | Interrupt (log reason, then resume) |
| `x` | Abandon session |
| `Esc` | Hide panel (timer keeps running) |

### Pomodoro — Deed Gate

| Key | Action |
|---|---|
| `h` | Toggle Hollow forge (`💀`) |
| `b` | Toggle Berserker forge (`⚡`) |
| `Enter` | Submit deed |

### Pomodoro — Break Choice

| Key | Action |
|---|---|
| `1` | Short rest (5 min) |
| `2` | Camp fire (10 min) |
| `3` | Full rest (15 min) — resets streak |
| `4` | Press on — skip break |
| `e` | End quest session |

---

## TUI — Concepts

**Quest lifecycle:** `log → active → done` (or `log → blocked → active → done`)

**Pomodoro flow:** `charge → work timer → deed → break choice → charge (next lap)`

**Charge** = Your stated intent before the timer starts.  
**Deed** = What you actually accomplished, logged after the bell rings.  
**Forge** = A completed pomo.  
**Hollow** (`💀`) = Went through the motions. Does not count toward stats or trophies.  
**Berserker** (`⚡`) = Deep flow state, exceptional output. Counts as 1 pomo, flagged as exceptional.  
**Frog** (`🐸`) = A dreaded task. Completing frogs earns trophy progress.  
**Streak** = Consecutive pomos without a long break.  
**Momentum** = Consecutive pomos without an interruption.

---

## Web UI — Usage

### Quest Board

- **Add quest** — click `+ New Quest` or use the input at top
- **Activate** — click `Start` on a log quest
- **Block / Unblock** — status action buttons on each quest card
- **Mark done** — `Done` button
- **Toggle frog** — `🐸` button on quest card
- **Delete** — trash icon (confirms before deleting)

### Pomodoro Timer

1. Navigate to an active quest → click **Enter the Fray**
2. Enter your **Charge** — what you'll conquer
3. Timer runs for 25 min. Live updates via SSE (no polling).
4. After the bell: enter your **Deed**, optionally set forge type
5. Choose rest or press on

### Chronicle

Accessible via the Chronicle tab or sidebar. Shows:
- Today's pomo count and focus time
- Weekly heatmap
- Interruption breakdown
- Quest completion rate

### Hall of Valor

Trophy panel. Shows 7 daily trophies with Bronze/Silver/Gold tiers and personal records (★).

---

## Directory Structure

```
LifeOS/
├── core/               ← Shared business logic (storage, engine, metrics)
├── tui/                ← Textual TUI app
├── web/                ← FastAPI web app
│   ├── quests/         ← Quest board routes + templates
│   ├── pomos/          ← Pomo flow routes + SSE + templates
│   ├── chronicle/      ← Stats panel
│   ├── trophies/       ← Trophy panel
│   ├── dashboard/      ← Dashboard modal
│   ├── shared/         ← Base layout, shared components
│   └── static/         ← CSS tokens, JS, fonts
├── migrations/         ← SQL schema migrations (auto-applied)
├── tests/              ← pytest suite
├── scripts/            ← Operational scripts
│   ├── clear_data.sh   ← Reset TUI JSON stores
│   └── clear_sql_data.sh ← Reset SQLite data
├── data/
│   ├── tui/            ← TUI JSON stores (gitignored, auto-created)
│   │   ├── quests.json
│   │   ├── pomodoros.json
│   │   └── trophies.json
│   ├── web/            ← SQLite DB (gitignored, auto-created)
│   │   └── questlog.db
│   └── backups/        ← Timestamped backups (gitignored)
├── docs/               ← Design docs, specs, this guide
│   ├── DESIGN.md       ← Visual identity + architecture reference
│   ├── GUIDE.md        ← This file
│   ├── INSTRUCTIONS.md ← In-depth RPG mechanics and keybindings
│   └── specs/          ← Feature PRDs and specs
├── docker-compose.yml
└── Dockerfile
```

---

## Troubleshooting

**TUI: Timer not visible**  
Press `t` while an active quest is selected. Quest must be in Active state.

**TUI: Can't activate quest**  
Quest must be in `log` or `blocked` state — not already active or done.

**TUI: Lost work?**  
Use `i` (interrupt) not `x` (abandon). Interrupt logs reason and resumes; abandon ends the session.

**Web: DB not found error on startup**  
The `migrations/` dir must exist and contain `001_initial.sql`. Migrations run on startup automatically.

**Web: Port already in use**  
`lsof -i :8000` to find and kill the process, or run on a different port:
```bash
uvicorn web.app:app --reload --port 8001
```

**Docker: Want to reset all container data**  
```bash
docker compose down -v   # deletes the questlog-data volume
docker compose up --build
```

**Timezone showing wrong time**  
Edit `USER_TZ` in `core/config.py`. Default is `Asia/Kolkata`. Use any `zoneinfo` key (e.g. `America/New_York`).
