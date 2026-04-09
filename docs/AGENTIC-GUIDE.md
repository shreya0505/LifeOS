# QuestLog — Agentic Development Guide

Best practices, architecture context, and conventions for AI agents working on this codebase.

---

## Running the App

```bash
# TUI
python3 -m venv .venv && source .venv/bin/activate
pip install textual rich
python -m tui.main

# Web
pip install fastapi uvicorn[standard] jinja2 aiosqlite sse-starlette python-multipart
uvicorn web.app:app --reload --port 8000

# Reset all data
./clear_data.sh
```

Requires Python 3.10+.

---

## Project Structure (Monorepo)

```
questlog/
├── core/              # Shared business logic — NEVER put UI here
│   ├── config.py      # POMO_CONFIG, VALID_SOURCES, USER_TZ
│   ├── utils.py       # Timezone helpers, format_duration, fantasy_date
│   ├── metrics.py     # compute_metrics(quests), compute_pomo_metrics(sessions)
│   ├── pomo_queries.py    # Read-only analytics over session data
│   ├── pomo_engine.py     # PomoEngine state machine (charge→work→deed→break)
│   ├── trophy_compute.py  # Trophy computation (7 trophies, tiered, PRs)
│   ├── trophy_defs.py     # TROPHY_DEFS constant list
│   └── storage/
│       ├── protocols.py       # QuestRepo, PomoRepo, TrophyPRRepo protocols
│       ├── json_backend.py    # JSON file implementations (TUI uses this)
│       ├── sqlite_backend.py  # Async SQLite implementations (web uses this)
│       └── sync_sqlite_backend.py
│
├── tui/               # Terminal UI (Textual/Rich)
│   ├── main.py        # QuestLogApp — owns all TUI state and bindings
│   ├── quest_panel.py, chronicle_panel.py, trophy_panel.py, pomo_panel.py
│   ├── modals.py      # Push-screen dialogs
│   ├── renderers.py   # Rich markup, pixel-art clock, health bar
│   └── styles.tcss    # Textual CSS
│
├── web/               # Web UI (FastAPI + HTMX + Alpine.js)
│   ├── app.py         # FastAPI app, lifespan, middleware, route registration
│   ├── db.py          # SQLite connection, migrate(), get_db()
│   ├── deps.py        # FastAPI dependencies
│   ├── quests/        # Quest CRUD routes + templates
│   ├── pomos/         # Pomo lifecycle routes + SSE + templates
│   ├── chronicle/     # Chronicle/heatmap routes + templates
│   ├── trophies/      # Trophy routes + templates
│   ├── dashboard/     # Dashboard metrics routes + templates
│   ├── shared/templates/   # base.html, stats_bar, components
│   └── static/        # CSS, JS (htmx, alpine, motion), fonts
│
├── migrations/        # Numbered SQL files (001_initial.sql, etc.)
├── tests/             # pytest tests
├── features/          # Product specs and PRDs (read-only reference)
└── docs/              # Documentation
```

---

## Architecture Rules

### Shared Core Pattern

All business logic lives in `core/`. Both TUI and web import from it. **Never duplicate computation.**

```python
# CORRECT — web route calling shared core logic
from core.pomo_queries import get_today_receipt
sessions = await pomo_repo.load_all()
receipt = get_today_receipt(sessions)

# WRONG — reimplementing query logic in web/
def get_today_receipt_sql(db):
    rows = db.execute("SELECT ...")  # Don't do this
```

### Storage Protocol

`core/storage/protocols.py` defines `QuestRepo`, `PomoRepo`, `TrophyPRRepo` protocols.
- TUI uses `JsonQuestRepo`, `JsonPomoRepo` (flat JSON files)
- Web uses `SqliteQuestRepo`, `SqlitePomoRepo` (async SQLite)
- Both backends return identical dict shapes

**Critical contract:** `load_all()` on pomo repos returns sessions with nested `segments` lists, matching JSON structure. Core query functions work against either backend.

### Core Function Signatures

All `core/pomo_queries.py` functions accept `sessions: list[dict]` as first parameter. They never load data themselves. Caller provides data from the appropriate backend.

All `core/trophy_compute.py` functions accept `(sessions, quests, prs)` and return `(result, updated_prs)`. Caller handles persistence.

---

## Data Layer

### JSON files (TUI)

| File | Purpose |
|------|---------|
| `quests.json` | Quest records (id, title, status, timestamps, frog flag) |
| `pomodoros.json` | Pomo sessions with nested segment arrays |
| `trophies.json` | Personal records (best-ever per trophy) |

### SQLite (Web)

| Table | Purpose |
|-------|---------|
| `quests` | Quest records |
| `pomo_sessions` | Pomo session records |
| `pomo_segments` | Individual work/break segments (FK to sessions) |
| `trophy_records` | Personal records |
| `_migrations` | Migration tracking |

### Timezone Convention

All timestamps stored as **UTC ISO strings**. Display conversion uses `USER_TZ` in `core/config.py` (default: `Asia/Kolkata`).

---

## Quest Status Machine

```
log → active → done
log → blocked → active → done
any status → delete
```

Enforced by `VALID_SOURCES` dict in `core/config.py`.

---

## Pomodoro Flow

The state machine cycles: `charge → timer → deed → break_choice → charge`

- **Charge Gate:** Hard gate, no skip. Timer does not start until non-empty charge submitted.
- **Deed Gate:** Hard gate. Break buttons hidden until deed submitted.
- **Forge Types:** `hollow` (barely worked), `berserker` (flow state), or normal (default).
- **Break Choices:** short (5m), extended (10m), long (30m, resets streak), skip, end session.

`PomoEngine` in `core/pomo_engine.py` owns this state machine. UI layers subscribe to events.

### Segment Types

| Stored `type` | `break_size` | Meaning |
|---------------|-------------|---------|
| `work` | — | Work segment |
| `short_break` | NULL | Short break |
| `short_break` | `"extended"` | Extended break (UI-only concept) |
| `long_break` | — | Long break |

### Config

```python
POMO_CONFIG = {
    "work_secs": 25 * 60,
    "short_break_secs": 5 * 60,
    "extended_break_secs": 10 * 60,
    "long_break_secs": 30 * 60,
}
```

---

## Trophy System

7 daily-resetting trophies, each with Bronze → Silver → Gold tiers:

| Trophy | Tracks |
|--------|--------|
| Frog Slayer | Completing dreaded (frog-flagged) tasks |
| Swamp Clearer | Volume of frogs completed |
| Forge Master | Total pomos completed |
| Untouchable | Clean pomos without interruptions |
| Quest Closer | Quests completed |
| Scribe | Pomos with deeds logged |
| Ironclad | Taking breaks after pomos |

Personal Records (PRs) track best-ever single-day performance.

---

## Web Stack

| Layer | Technology | Size |
|-------|------------|------|
| Backend | FastAPI | — |
| Templating | Jinja2 (server-rendered HTML) | — |
| Dynamic UI | HTMX | 14KB |
| Client state | Alpine.js | 15KB |
| Animations | Motion (motion.dev) | 18KB |
| Toasts | Sonner | 5KB |
| Database | SQLite (WAL mode) | — |
| SSE | sse-starlette | — |

**Total JS < 60KB. No build step. No node_modules.**

### Web Architecture Principles

1. **HTML is the API.** Endpoints return HTML fragments, not JSON.
2. **One process, one file.** Single Python process, single SQLite file.
3. **Server-authoritative time.** Pomo timer source of truth is the server. Client countdown is cosmetic. SSE pushes authoritative events.
4. **Module = directory.** Each feature is self-contained with routes, templates. Adding a feature = adding a directory.

### Route Convention

All endpoints return HTML fragments. HTMX swaps them into the DOM. Server sets `HX-Trigger` headers for toast notifications. `X-Animation` headers signal which celebration to play.

---

## Feature Specs Reference

Consult these before implementing related features:

| File | Scope |
|------|-------|
| `features/PRD.md` | Core product vision — Charge/Deed accountability loop |
| `features/SPEC-intentional-pomo.md` | Charge/Deed gates, receipt, pomo panel design |
| `features/SPEC-war-room-pomo.md` | Visual drama, break system, journey tracks, streaks |
| `features/SPEC-war-room-gap.md` | Implementation status tracker for War Room features |
| `features/SPEC-questlog-web.md` | Web app v1 spec (full design system, components, animations) |
| `features/SPEC-questlog-web-v2.md` | v2 revision (shared core architecture) |
| `features/web-imp-plan.md` | Phase-by-phase implementation plan |

---

## Conventions

### RPG Terminology

| Term | Means |
|------|-------|
| Quest | Task/project |
| Charge | Pre-work intention ("What will you forge?") |
| Deed | Post-work outcome ("What did you claim?") |
| Forge | A completed pomo |
| Hollow | Pomo where you barely worked (💀) |
| Berserker | Flow state pomo (⚡) |
| Frog | Dreaded task (🐸) |
| Swiftblade | Early completion |
| Hall of Valor | Trophy panel |

### Code Conventions

- Immutability preferred — create new objects, don't mutate
- Functions < 50 lines, files < 800 lines
- Validate at system boundaries
- No hardcoded secrets
- Error handling at every level

### CSS (Web)

- Earthy palette defined in `tokens.css` via CSS custom properties
- Component styles in `style.css`
- Fonts: Inter (body), Crimson Pro (display), JetBrains Mono (timer)
- Animate only compositor-friendly properties (transform, opacity)

### Adding a Web Module

1. Create `web/{module}/` with `__init__.py`, `routes.py`, `templates/`
2. Add migration: `migrations/NNN_{module}.sql`
3. Register router in `web/app.py`
4. Add nav entry in `shared/templates/base.html`
