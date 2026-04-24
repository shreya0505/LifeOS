# LifeOS (QuestLog)

**A productivity companion featuring an active quest board and pomodoro timer with RPG theming and trophy gamification.**

Two interfaces. One shared core:
1. **TUI** — keyboard-driven terminal app, JSON file storage
2. **Web** — browser dashboard, SQLite + HTMX + Alpine.js

---

## Quick Start

### Web with Docker

```bash
# 1. Create local env file. This file is gitignored.
cp .env.example .env  # if present, otherwise create .env manually

# 2. Start the web app.
docker compose up --build

# → http://localhost:8000
```

Minimum `.env` for Docker:

```env
QUESTLOG_DB=/app/data/web/questlog.db
```

Optional R2 sync config:

```env
SYNC_ENABLED=true
SYNC_PROVIDER=r2
SYNC_DEVICE_NAME=personal-laptop

R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=life-os-sync-prod
R2_PREFIX=lifeos/prod
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com

SYNC_ENCRYPTION_PASSPHRASE=...
SYNC_AUTO_ENABLED=false
SYNC_INTERVAL_SECONDS=3600
SYNC_UI_POLL_SECONDS=300
SYNC_HIDE_PROMPTS=false
```

Notes:

- `.env` is ignored by git. Do not commit R2 keys or the sync passphrase.
- Use the same `R2_BUCKET`, `R2_PREFIX`, and `SYNC_ENCRYPTION_PASSPHRASE` on every laptop.
- Use a different `SYNC_DEVICE_NAME` per laptop.
- With `SYNC_AUTO_ENABLED=false`, R2 requests happen only when you press Pull, Push, or Sync now.

### Local Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" jinja2 aiosqlite sse-starlette httpx python-multipart boto3 cryptography
uvicorn web.app:app --reload
# → http://127.0.0.1:8000
```

### TUI

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install textual rich
python3 -m tui
```

TUI data uses JSON storage and is not part of the R2 SQLite sync.

### Tests

```bash
.venv/bin/pytest -q
```

### Stop Docker

```bash
docker compose down
```

Restart after config or code changes:

```bash
docker compose up --build -d
# → http://localhost:8000
```

---

## Features

- **Quest Board** — RPG-themed task manager. Mark dreaded tasks as Frogs (`🐸`).
- **Pomodoro Timer** — Charge (intent) → Work → Deed (outcome) loop. Tracks Hollow (`💀`) and Berserker (`⚡`) forges.
- **Trophy System** — Hall of Valor with daily trophies (Bronze/Silver/Gold tiers) and personal records.
- **Analytics** — Adventure's Chronicle: daily/weekly stats, heatmaps, interruption analysis.

---

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/GUIDE.md`](docs/GUIDE.md) | Full setup and usage guide (TUI, Web, Docker) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Visual identity, code style, architecture reference |
| [`docs/INSTRUCTIONS.md`](docs/INSTRUCTIONS.md) | In-depth RPG mechanics, keybindings, workflow tips |

---

## Project Structure

```
core/          ← shared business logic + storage backends
tui/           ← Textual TUI app
web/           ← FastAPI + HTMX + Alpine.js web app
migrations/    ← SQL schema (auto-applied on startup)
tests/         ← pytest suite
scripts/       ← data reset scripts
docs/          ← design docs, user guide, specs
data/backups/  ← timestamped data backups
```

---

## Maintenance

```bash
# Reset TUI data (JSON stores)
./scripts/clear_data.sh

# Reset local host Web data (SQLite, keeps schema)
./scripts/clear_sql_data.sh
```

The host reset scripts create timestamped backups in `data/backups/` before clearing.

### Clear Docker Data

When running through Docker, clear the SQLite database inside the Docker volume:

```bash
# Clear all Docker web data: quests, pomos, trophies, and Hard 90.
scripts/clear_docker_data.sh

# Clear only Hard 90 challenge data.
LIFEOS_CLEAR_SCOPE=challenge scripts/clear_docker_data.sh
```

The Docker clear script keeps schema, migrations, and sync settings. It suppresses sync triggers during the wipe and clears local pending sync journal entries for the wiped tables.

After clearing Docker data, refresh the browser. If the UI still shows cached state, restart the service:

```bash
docker compose restart questlog
```

Config knobs:

```bash
# Compose service name. Defaults to questlog.
LIFEOS_SERVICE=questlog scripts/clear_docker_data.sh

# SQLite path inside the container. Defaults to /app/data/web/questlog.db.
LIFEOS_DB=/app/data/web/questlog.db scripts/clear_docker_data.sh

# Scope: all or challenge. Defaults to all.
LIFEOS_CLEAR_SCOPE=all scripts/clear_docker_data.sh
```

---

## Tech Stack

- **Core:** Python 3.10+
- **TUI:** Textual, Rich
- **Web:** FastAPI, Jinja2, HTMX, Alpine.js, SSE, aiosqlite
- **Docker:** Docker Compose

---

*May your quests be many and your focus unbreakable.*
