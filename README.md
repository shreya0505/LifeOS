# LifeOS (QuestLog)

**A productivity companion featuring an active quest board and pomodoro timer with RPG theming and trophy gamification.**

Two interfaces. One shared core:
1. **TUI** — keyboard-driven terminal app, JSON file storage
2. **Web** — browser dashboard, SQLite + HTMX + Alpine.js

---

## Operations Guide

### 1. Set Up And Run The Project

#### Run With Docker

```bash
# Create local env file. This file is gitignored.
cp .env.example .env  # if present, otherwise create .env manually

# Start the web app.
docker compose up --build -d

# → http://localhost:8000
```

Minimum `.env` for Docker:

```env
QUESTLOG_DB=/app/data/web/questlog.db
```

Stop Docker:

```bash
docker compose down
```

Restart after config or code changes:

```bash
docker compose up --build -d
# → http://localhost:8000
```

#### Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" jinja2 aiosqlite sse-starlette httpx python-multipart boto3 cryptography

# Optional: choose a local SQLite DB path.
export QUESTLOG_DB=./data/web/questlog.db

uvicorn web.app:app --reload
# → http://127.0.0.1:8000
```

#### Run The TUI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install textual rich
python3 -m tui
```

TUI data uses JSON storage and is not part of the R2 SQLite sync.

#### Run Tests

```bash
.venv/bin/pytest -q
```

### 2. Set Up Sync

LifeOS Web sync uses encrypted objects in Cloudflare R2. Use the same R2 location and passphrase on every laptop, but a different device name on each laptop.

Add this to `.env` for Docker, or export the same variables before running locally:

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

Sync setting details:

- `SYNC_ENABLED=true` turns on the R2 sync UI and sync routes. Use `false` for a purely local SQLite app.
- `SYNC_PROVIDER=r2` selects Cloudflare R2 through its S3-compatible API.
- `SYNC_DEVICE_NAME` identifies the current laptop in sync metadata. Keep it unique per device.
- `R2_BUCKET`, `R2_PREFIX`, and `R2_ENDPOINT` choose where encrypted sync objects live.
- `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` are the R2 credentials used by the app.
- `SYNC_ENCRYPTION_PASSPHRASE` encrypts and decrypts bootstrap and bundle payloads. Every device in the same sync set must use the same passphrase.
- `SYNC_AUTO_ENABLED=true` lets the app run sync periodically in the background. With `false`, syncing is manual from the UI.
- `SYNC_INTERVAL_SECONDS` controls the background sync interval when auto sync is enabled.
- `SYNC_UI_POLL_SECONDS` controls how often the sync status chip refreshes in the browser.
- `SYNC_HIDE_PROMPTS=true` hides the visible sync prompt/chip affordance when you want a quieter UI.

Operational notes:

- `.env` is ignored by git. Do not commit R2 keys or the sync passphrase.
- Use the same `R2_BUCKET`, `R2_PREFIX`, and `SYNC_ENCRYPTION_PASSPHRASE` on every laptop.
- Use a different `SYNC_DEVICE_NAME` per laptop.
- With `SYNC_AUTO_ENABLED=false`, R2 requests happen only when you press Pull, Push, or Sync now.
- With `SYNC_AUTO_ENABLED=true`, the app can pull and push periodically in the background.

Bootstrap behavior:

- The first device that pushes to an empty R2 prefix uploads an encrypted `bootstrap.json.enc` snapshot containing the current rows from every sync-enabled table.
- A device applies bootstrap only once, tracked locally by `sync_state.applied_bootstrap = 1`.
- After bootstrap, normal sync happens through encrypted change bundles. Push uploads local inserts, updates, and deletes; pull applies remote bundles from other devices.
- The clear-data scripts below are local-only with remote restore when sync is enabled. They suppress sync triggers, wipe the selected local tables, and rehydrate those tables from remote sync state.
- Clear-data scripts do not push remote deletes. They are safe to use when you want to repair or repopulate a local device from sync.
- If unsynced local changes exist in the selected scope, the script warns you. Sync first to preserve those edits, or explicitly confirm discard.
- To intentionally make the cloud empty for a scope, the app needs a separate destructive sync-reset/delete-everywhere mode. A normal local clear is not that mode.

### 3. Set Up An Existing Project On A New Laptop With Sync

```bash
# Clone the repo.
git clone <repo-url> LifeOS
cd LifeOS

# Create .env from a trusted source. Do not invent a new passphrase.
cp .env.example .env  # if present, otherwise create .env manually

# Set a unique device name for this laptop.
# Keep R2_BUCKET, R2_PREFIX, R2_ENDPOINT, and SYNC_ENCRYPTION_PASSPHRASE
# exactly the same as the existing synced devices.

docker compose up --build -d
# → http://localhost:8000
```

Then open the app and run **Pull** or **Sync now** before adding new data. On a fresh laptop this applies the remote bootstrap once, then applies later change bundles.

Recommended new-laptop order:

1. Configure `.env` with the existing R2 sync settings.
2. Use a new `SYNC_DEVICE_NAME`.
3. Start the app.
4. Pull remote data before creating or clearing anything locally.
5. After the first successful pull, use the app normally.

On a fresh laptop, prefer **Pull** or **Sync now** before any clear/reset command. Clear is only needed if the local DB is already stale or inconsistent.

### 4. Clear Or Reset Data Safely

There are two different operations:

- **Clear** means local-only cleanup. For synced Web data, clear removes local rows for the chosen scope and then restores them from R2 sync. It does not delete remote data.
- **Reset** means start fresh locally. Use reset only when you intentionally want an empty local database or JSON store. If sync is enabled, disable sync or use a new R2 prefix before resetting, otherwise remote data can come back.

Recommended rule: if you use Docker, run the Docker commands. If you run the app locally, run the host commands. Host scripts do not touch the Docker volume.

#### A. Clear Web Data Safely

Use clear when the local SQLite DB is stale, incomplete, or inconsistent and you want it rebuilt from sync.

Before clearing synced Web data:

1. Press **Sync now** in the app if you want to preserve recent local edits.
2. Stop using the app during the clear.
3. Choose the smallest scope that fixes the issue.
4. Answer `no` to discarding unsynced changes unless you deliberately want to lose local-only edits.

Scopes:

| Scope | Deletes locally | Restores from sync when enabled |
|---|---|---|
| `questlog` | Quests, artifact keys, pomos, trophies | Yes |
| `challenge` | Hard 90 challenge data and linked Tiny Experiments | Yes |
| `tiny_experiments` | Tiny Experiment protocols and daily signals only | Yes |
| `saga` | Saga emotion log entries | Yes |
| `all` | All Web app data | Yes |

The `challenge` scope includes Tiny Experiments because those rows are linked to challenge rows. The `tiny_experiments` scope is safe when you only want to remove experiment protocols/signals while keeping the parent Hard 90 challenge.

#### Clear Local Host Web Data

These commands affect files on the host machine, not the Docker volume.

```bash
# Clear local host Web QuestLog SQLite data: quests, artifacts, pomos, trophies.
./scripts/clear_sql_data.sh

# Clear local host Hard 90 challenge data, including linked Tiny Experiments.
./scripts/clear_challenge_data.sh
```

The host clear scripts create timestamped DB backups in `data/backups/` before clearing. They keep schema and migrations intact. When sync is enabled, they restore the cleared scope from R2 and do not queue remote deletes.

#### Clear Docker Web Data

When running through Docker, clear the SQLite database inside the Docker volume. This is the usual path for the deployed app:

```bash
# Choose which Docker web app data to clear.
scripts/clear_docker_data.sh

# Clear QuestLog data only.
LIFEOS_CLEAR_SCOPE=questlog scripts/clear_docker_data.sh

# Clear only Hard 90 challenge data, including Tiny Experiments.
LIFEOS_CLEAR_SCOPE=challenge scripts/clear_docker_data.sh

# Clear only Tiny Experiments protocols and daily signals.
LIFEOS_CLEAR_SCOPE=tiny_experiments scripts/clear_docker_data.sh

# Clear Saga data only.
LIFEOS_CLEAR_SCOPE=saga scripts/clear_docker_data.sh

# Clear all Docker web data.
LIFEOS_CLEAR_SCOPE=all scripts/clear_docker_data.sh
```

The Docker clear script keeps schema, migrations, and sync settings. It suppresses sync triggers during the wipe, clears local pending sync journal entries for the selected tables, restores from sync when enabled, checks linked data integrity, and does not queue remote deletes.

After clearing Docker data, refresh the browser. If the UI still shows cached state, restart the service:

```bash
docker compose restart questlog
```

Docker clear config knobs:

```bash
# Compose service name. Defaults to questlog.
LIFEOS_SERVICE=questlog scripts/clear_docker_data.sh

# SQLite path inside the container. Defaults to /app/data/web/questlog.db.
LIFEOS_DB=/app/data/web/questlog.db scripts/clear_docker_data.sh

# Scope: questlog, challenge, tiny_experiments, saga, or all. When omitted, the script asks.
LIFEOS_CLEAR_SCOPE=saga scripts/clear_docker_data.sh
```

Local clear and Docker clear are separate. If the app is running in Docker, use `scripts/clear_docker_data.sh`; host scripts will not touch the Docker volume.

#### B. Reset Data Safely

Use reset when you intentionally want a fresh local start.

TUI reset:

```bash
# Reset TUI JSON data: quests, pomodoros, trophies.
./scripts/clear_data.sh
```

The TUI uses JSON files under `data/tui/` and is not part of R2 SQLite sync. The script backs up JSON files to `data/backups/`, writes empty JSON stores, and optionally deletes old JSON backups.

Local Web reset without remote restore:

```bash
# Disable sync for this shell so clear remains local-only.
SYNC_ENABLED=false QUESTLOG_DB=./data/web/questlog.db python3 -m core.maintenance.clear_data --db ./data/web/questlog.db --scope all --discard-unsynced
```

Docker Web reset without remote restore:

```bash
# Temporarily disable sync in .env, then recreate the container.
docker compose up --build -d
LIFEOS_CLEAR_SCOPE=all scripts/clear_docker_data.sh
```

For a truly blank Docker volume, stop and delete the volume:

```bash
docker compose down -v
docker compose up --build -d
```

Only use `docker compose down -v` when you are sure the Docker volume contains no data you need. It deletes the container volume, not the R2 remote sync objects.

Remote reset/delete-everywhere is not currently implemented. Do not use the normal clear scripts expecting cloud data to be deleted; they are designed to avoid that.

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

## Tech Stack

- **Core:** Python 3.10+
- **TUI:** Textual, Rich
- **Web:** FastAPI, Jinja2, HTMX, Alpine.js, SSE, aiosqlite
- **Docker:** Docker Compose

---

*May your quests be many and your focus unbreakable.*
