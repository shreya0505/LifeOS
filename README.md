# LifeOS (QuestLog)

**A productivity companion featuring an active quest board and pomodoro timer with RPG theming and trophy gamification.**

Two interfaces. One shared core:
1. **TUI** — keyboard-driven terminal app, JSON file storage
2. **Web** — browser dashboard, SQLite + HTMX + Alpine.js

---

## Quick Start

```bash
# TUI
python3 -m venv .venv && source .venv/bin/activate
pip install textual rich
python3 -m tui

# Web (local)
pip install fastapi "uvicorn[standard]" jinja2 aiosqlite sse-starlette httpx
uvicorn web.app:app --reload
# → http://127.0.0.1:8000

# Web (Docker)
docker compose up --build
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

# Reset Web data (SQLite, keeps schema)
./scripts/clear_sql_data.sh
```

Both scripts create timestamped backups in `data/backups/` before clearing.

---

## Tech Stack

- **Core:** Python 3.10+
- **TUI:** Textual, Rich
- **Web:** FastAPI, Jinja2, HTMX, Alpine.js, SSE, aiosqlite
- **Docker:** Docker Compose

---

*May your quests be many and your focus unbreakable.*
