# QuestLog Web — Product Spec & Low-Level Design

**Author:** Product + Engineering + UI  
**Status:** Ready for Implementation  
**Version:** 1.0  
**Date:** April 9, 2026

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Requirements](#2-requirements)
3. [Architecture](#3-architecture)
4. [Database Schema](#4-database-schema)
5. [Project Structure](#5-project-structure)
6. [Route Map & API](#6-route-map--api)
7. [Timer Architecture](#7-timer-architecture)
8. [UI Design System](#8-ui-design-system)
9. [Layout & Responsive](#9-layout--responsive)
10. [Component Specs](#10-component-specs)
11. [Animation & Motion](#11-animation--motion)
12. [Typography](#12-typography)
13. [Data Migration](#13-data-migration)
14. [Extensibility](#14-extensibility)
15. [Implementation Phases](#15-implementation-phases)
16. [Risks & Mitigations](#16-risks--mitigations)
17. [Dependencies](#17-dependencies)

---

## 1. Product Overview

QuestLog Web is a **single-user, self-hosted web app** that brings the existing QuestLog TUI to the browser. It preserves the core philosophy — every pomodoro has a declared Charge (intention) and a recorded Deed (outcome) — while gaining the visual richness, satisfying animations, and extensibility that a web interface provides.

### Core Insight (unchanged from TUI)

> Every productivity tool captures activity. None capture intention. QuestLog closes that loop.

### What Changes from TUI to Web

| Aspect | TUI | Web |
|--------|-----|-----|
| Data store | Flat JSON files | SQLite database |
| Rendering | Textual/Rich terminal widgets | Server-rendered HTML + HTMX |
| Interactivity | Key bindings | Click/keyboard + HTMX partial swaps |
| Timer | In-process Python timer | Server-authoritative + client display |
| Animations | None (terminal limitation) | Spring physics, celebrations, staggered reveals |
| Extensibility | Add Python modules | Add route/template directories (module pattern) |
| Deployment | `python3 main.py` | `docker compose up` or bare `uvicorn` |

### What Does NOT Change

- The Charge/Deed accountability loop
- Quest status machine (log -> active -> done, with blocked)
- Pomodoro segment model (work/short_break/long_break, forge types)
- Trophy system (7 trophies, tiered, with personal records)
- Single-user, personal-ledger philosophy
- RPG flavor text and terminology

---

## 2. Requirements

### Functional

| ID | Requirement |
|----|-------------|
| F1 | Quest CRUD with kanban board (log, active, blocked, done) |
| F2 | Quest state transitions with validation (same rules as TUI) |
| F3 | Frog flag toggle on quests |
| F4 | Pomodoro sessions attached to active quests |
| F5 | Charge gate before every work segment (hard gate, no skip) |
| F6 | Deed gate after every completed work segment (hard gate, break held hostage) |
| F7 | Forge type tagging (hollow, berserker) at deed gate |
| F8 | Break choice gate (short/extended/long/skip/end) after deed |
| F9 | Live countdown timer with progress bar |
| F10 | Interruption flow with reason capture |
| F11 | Early completion (Swiftblade) |
| F12 | Daily receipt view (charge/deed pairs) |
| F13 | Chronicle heatmap (pomo activity by day) |
| F14 | Chronicle daily timeline (today's segments) |
| F15 | Trophy panel with 7 trophies, tiers, and personal records |
| F16 | Dashboard metrics (quest velocity, cycle time, pomo stats) |
| F17 | Stats bar with live session info |
| F18 | Celebration animations on quest completion and pomo milestones |
| F19 | Break reminder nudges (5-min interval) |

### Non-Functional

| ID | Requirement |
|----|-------------|
| NF1 | Single user — no auth required |
| NF2 | Zero-cost infrastructure (SQLite, self-hosted) |
| NF3 | No JavaScript build step — all JS served as static files |
| NF4 | Total JS payload < 60KB |
| NF5 | Total CSS payload < 25KB |
| NF6 | Works offline (local network) |
| NF7 | Deployable via single Docker container |
| NF8 | Earthy, comfy, soulful aesthetic — not a generic SaaS dashboard |
| NF9 | Responsive: usable on mobile (>= 320px) |

---

## 3. Architecture

### 3.1 Stack

| Layer | Technology | Size/Weight |
|-------|------------|-------------|
| Backend | **FastAPI** (Python 3.11+) | — |
| Templating | **Jinja2** (server-rendered HTML) | — |
| Dynamic UI | **HTMX** | 14KB |
| Client state | **Alpine.js** | 15KB |
| Animations | **Motion** (motion.dev) | 18KB |
| Toasts | **Sonner** | 5KB |
| Database | **SQLite** (WAL mode) | — |
| DB access | **aiosqlite** (async, raw SQL) | — |
| SSE | **sse-starlette** | — |
| CSS tokens | **Open Props** (cherry-picked) | ~3KB |
| Icons | **Lucide** (inline SVG) | per-icon |
| Fonts | Inter, Crimson Pro, JetBrains Mono (self-hosted woff2) | ~80KB |

**Total JS: ~52KB. Total CSS: ~20KB. No build step. No node_modules.**

### 3.2 Architectural Principles

1. **HTML is the API.** Endpoints return HTML fragments, not JSON. The browser is a thin rendering client.
2. **One process, one file.** Single Python process, single SQLite file. No Redis, Celery, or message queue.
3. **Progressive enhancement.** Core app works without JS. HTMX adds dynamic swaps. Alpine.js adds the timer. Motion adds polish. Each layer is optional for degraded function.
4. **Module = directory.** Each feature (quests, pomos, trophies) is a self-contained directory with routes, queries, and templates. Adding a feature means adding a directory.
5. **Server-authoritative time.** The pomo timer's source of truth is the server. The client countdown is cosmetic. SSE pushes authoritative events.

### 3.3 Request Flow

```
Browser                    FastAPI                    SQLite
   │                          │                          │
   │  click [Done]            │                          │
   │ ─── HTMX PATCH ───────> │                          │
   │                          │ ── UPDATE quest ───────> │
   │                          │ <── ok ─────────────────│
   │                          │                          │
   │                          │  render quest_card.html  │
   │ <── HTML fragment ────── │  (Jinja2)                │
   │                          │                          │
   │  htmx:afterSwap fires   │                          │
   │  Alpine calls            │                          │
   │  celebrateDone(el)       │                          │
   │  Motion animates         │                          │
```

### 3.4 Why NOT These Alternatives

| Alternative | Rejected because |
|-------------|-----------------|
| React / Next.js | Build step, node ecosystem, hydration complexity. Overkill for single user. |
| Django | Heavier than needed. Admin panel wasted on single-user tool. |
| Supabase / PlanetScale | External dependency. Should work offline and locally. |
| HTMX alone (no Alpine) | Pomo countdown needs client-side `setInterval`. |
| Turso (hosted SQLite) | Adds latency and vendor lock. Local SQLite is faster. |
| Tailwind CSS | Utility classes fight against an intentional custom aesthetic. Needs build step for purge. |
| Pico CSS | Too opinionated, fights customization for the earthy palette. |
| Raw CSS (no tokens) | Reinventing easing curves, shadow scales, and fluid type that Open Props provides for free. |

---

## 4. Database Schema

### 4.1 Tables

```sql
-- ── Quests ───────────────────────────────────────────────────────
CREATE TABLE quests (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'log'
                      CHECK (status IN ('log','active','blocked','done')),
    frog         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at   TEXT,
    completed_at TEXT
);

CREATE INDEX idx_quests_status ON quests(status);


-- ── Pomo Sessions ────────────────────────────────────────────────
CREATE TABLE pomo_sessions (
    id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    quest_id             TEXT NOT NULL REFERENCES quests(id),
    quest_title          TEXT NOT NULL,
    started_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    ended_at             TEXT,
    actual_pomos         INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running','completed','stopped')),
    streak_peak          INTEGER NOT NULL DEFAULT 0,
    total_interruptions  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_sessions_quest ON pomo_sessions(quest_id);
CREATE INDEX idx_sessions_started ON pomo_sessions(started_at);


-- ── Pomo Segments ────────────────────────────────────────────────
CREATE TABLE pomo_segments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES pomo_sessions(id),
    type                 TEXT NOT NULL CHECK (type IN ('work','short_break','long_break')),
    lap                  INTEGER NOT NULL,
    cycle                INTEGER NOT NULL DEFAULT 0,
    completed            INTEGER NOT NULL DEFAULT 0,
    interruptions        INTEGER NOT NULL DEFAULT 0,
    started_at           TEXT NOT NULL,
    ended_at             TEXT NOT NULL,
    charge               TEXT,
    deed                 TEXT,
    break_size           TEXT,
    interruption_reason  TEXT,
    early_completion     INTEGER NOT NULL DEFAULT 0,
    forge_type           TEXT CHECK (forge_type IS NULL
                                    OR forge_type IN ('hollow','berserker'))
);

CREATE INDEX idx_segments_session ON pomo_segments(session_id);
CREATE INDEX idx_segments_started ON pomo_segments(started_at);
CREATE INDEX idx_segments_type    ON pomo_segments(type, completed);


-- ── Trophy Records (Personal Records) ────────────────────────────
CREATE TABLE trophy_records (
    trophy_id  TEXT PRIMARY KEY,
    best       TEXT NOT NULL,
    date       TEXT NOT NULL,
    detail     TEXT
);


-- ── Migration Tracking ───────────────────────────────────────────
CREATE TABLE _migrations (
    id         INTEGER PRIMARY KEY,
    filename   TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
```

### 4.2 Quest State Machine

```
log --> active --> done
log --> blocked --> active --> done
any status --> delete (hard delete from DB)
```

Enforced in Python via `VALID_SOURCES`:

```python
VALID_SOURCES = {
    "start":  {"log", "blocked"},
    "block":  {"log", "active"},
    "done":   {"active", "blocked"},
    "delete": {"log", "active", "blocked", "done"},
}
```

### 4.3 Segment Types

| Stored `type` | `break_size` | UI label |
|---------------|-------------|----------|
| `work` | — | Work |
| `short_break` | NULL | Short Break |
| `short_break` | `"extended"` | Extended Break |
| `long_break` | — | Long Break |

### 4.4 Migration Strategy

A `migrations/` directory with numbered SQL files (`001_initial.sql`, `002_add_habits.sql`, etc.). A `migrate()` function in `db.py` runs unapplied migrations in order and records them in `_migrations`. No Alembic.

---

## 5. Project Structure

```
questlog-web/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, lifespan, middleware, route registration
│   ├── db.py                    # SQLite connection pool, migrate(), get_db()
│   ├── config.py                # USER_TZ, POMO_CONFIG, VALID_SOURCES, DB_PATH
│   │
│   ├── quests/
│   │   ├── __init__.py
│   │   ├── routes.py            # Quest CRUD endpoints
│   │   ├── queries.py           # SQL: load, add, update, delete, toggle_frog
│   │   └── templates/
│   │       ├── board.html       # Full quest board (4 columns)
│   │       ├── column.html      # Single status column
│   │       └── card.html        # Single quest card
│   │
│   ├── pomos/
│   │   ├── __init__.py
│   │   ├── routes.py            # Session lifecycle + SSE tick
│   │   ├── queries.py           # Segments, receipt, counts, lap history
│   │   ├── state.py             # In-memory timer state (single-user)
│   │   └── templates/
│   │       ├── panel.html       # Full pomo panel (overlay)
│   │       ├── charge.html      # Charge gate
│   │       ├── timer.html       # Countdown display
│   │       ├── deed.html        # Deed gate
│   │       ├── break_choice.html
│   │       ├── interrupt.html   # Interruption reason form
│   │       └── receipt.html     # Daily receipt
│   │
│   ├── trophies/
│   │   ├── __init__.py
│   │   ├── routes.py            # GET /trophies
│   │   ├── compute.py           # Trophy computation logic
│   │   └── templates/
│   │       ├── panel.html       # Trophy list
│   │       └── card.html        # Single trophy card
│   │
│   ├── chronicle/
│   │   ├── __init__.py
│   │   ├── routes.py            # GET /chronicle
│   │   ├── queries.py           # Heatmap data, timeline, metrics
│   │   └── templates/
│   │       ├── panel.html       # Chronicle sidebar section
│   │       ├── heatmap.html     # Activity heatmap grid
│   │       └── timeline.html    # Today's session timeline
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── routes.py            # GET /dashboard
│   │   ├── queries.py           # Quest metrics, pomo metrics
│   │   └── templates/
│   │       └── modal.html       # Metrics overlay
│   │
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── utils.py             # format_duration, fantasy_date, timezone helpers
│   │   └── templates/
│   │       ├── base.html        # Full page shell (<html>, <head>, nav, layout)
│   │       ├── stats_bar.html   # Bottom stats bar
│   │       └── components/
│   │           ├── progress_bar.html
│   │           ├── badge.html
│   │           ├── stat_row.html
│   │           ├── confirm_modal.html
│   │           └── toast.html
│   │
│   └── static/
│       ├── reset.css            # Josh Comeau's modern CSS reset (~60 lines)
│       ├── tokens.css           # Open Props imports + earthy palette (~80 lines)
│       ├── style.css            # Component styles (~400 lines)
│       ├── htmx.min.js          # 14KB
│       ├── alpine.min.js        # 15KB
│       ├── motion.min.js        # 18KB
│       ├── sonner.min.js        # 5KB
│       ├── animations.js        # Celebration/transition helpers (~150 lines)
│       └── fonts/
│           ├── inter-var.woff2
│           ├── crimson-pro-var.woff2
│           └── jetbrains-mono-var.woff2
│
├── migrations/
│   └── 001_initial.sql
│
├── scripts/
│   └── migrate_json.py          # One-time JSON → SQLite migration
│
├── questlog.db                  # SQLite file (gitignored)
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## 6. Route Map & API

All endpoints return **HTML fragments** unless noted. HTMX swaps them into the DOM.

### Quest Routes (`/quests`)

| Method | Path | Returns | Trigger |
|--------|------|---------|---------|
| GET | `/` | Full page: board + chronicle + trophies + stats | Page load |
| GET | `/quests` | Quest board HTML (all 4 columns) | HTMX refresh |
| POST | `/quests` | New quest card, OOB swap into log column | HTMX form submit |
| PATCH | `/quests/{id}/status` | Updated card + OOB swaps for source/target columns | HTMX click |
| PATCH | `/quests/{id}/frog` | Updated card | HTMX click |
| DELETE | `/quests/{id}` | Empty (removes card from DOM) | HTMX confirm |

### Pomo Routes (`/pomos`)

| Method | Path | Returns | Trigger |
|--------|------|---------|---------|
| POST | `/pomos/start` | Charge gate HTML (full-screen overlay) | HTMX click on quest |
| POST | `/pomos/charge` | Timer HTML (starts countdown) | HTMX form submit |
| POST | `/pomos/deed` | Break choice HTML | HTMX form submit |
| POST | `/pomos/break` | Timer HTML (break countdown) | HTMX click |
| POST | `/pomos/interrupt` | Charge gate HTML (after recording interruption) | HTMX form submit |
| POST | `/pomos/complete-early` | Deed gate HTML | HTMX click |
| POST | `/pomos/stop` | Empty (closes overlay, refreshes board) | HTMX click |
| GET | `/pomos/tick` | **SSE stream** (remaining secs, segment events) | Alpine.js EventSource |

### Other Routes

| Method | Path | Returns | Trigger |
|--------|------|---------|---------|
| GET | `/receipt` | Receipt HTML | HTMX swap |
| GET | `/chronicle` | Chronicle panel HTML | HTMX swap |
| GET | `/trophies` | Trophy panel HTML | HTMX swap |
| GET | `/dashboard` | Dashboard metrics modal HTML | HTMX swap |
| GET | `/stats` | Stats bar HTML | HTMX poll (every 60s, or after mutations) |

---

## 7. Timer Architecture

The pomo timer uses **server-authoritative time** with **client-side countdown display**.

### Flow

1. `POST /pomos/charge` records the charge, sets server-side state:
   ```python
   # app/pomos/state.py — in-memory, single-user
   timer_state = {
       "session_id": "a1b2c3d4",
       "seg_type": "work",
       "seg_start": datetime.now(UTC),
       "seg_duration": 1500,  # 25 min
   }
   ```

2. Response HTML includes Alpine.js data attributes:
   ```html
   <div x-data="pomodoroTimer(1500, '2026-04-09T10:00:00Z')" x-init="start()">
   ```

3. Alpine.js runs a local `setInterval(1000)` for the visual countdown. This is **cosmetic only**.

4. SSE endpoint (`GET /pomos/tick`) checks server time. When `now >= seg_start + seg_duration`:
   - Pushes `event: segment-complete` with deed gate HTML
   - Client receives via `EventSource`, HTMX swaps in the deed gate

5. If the browser tab is backgrounded and the JS timer drifts, the SSE event corrects it on reconnect.

### Why SSE, Not WebSocket

- Unidirectional (server → client) is all we need
- Built-in reconnection
- Works through proxies without upgrade negotiation
- `sse-starlette` is a one-liner in FastAPI

### In-Memory State Justification

Single user, single process. No need for Redis or DB-backed timer state. If the server restarts mid-pomo, the session is recoverable from the DB (last segment's `started_at` + configured duration).

---

## 8. UI Design System

### 8.1 Design Direction: "Tavern Workbench"

A well-lit craftsman's desk in a warm tavern. Parchment warmth, wood-grain depth, ink-dark text, accent colors from nature. **Not** dark mode by default. **Not** SaaS gray.

Three sources of soul:
1. **Texture** — subtle SVG noise overlay on card surfaces
2. **Typography with character** — serif for display, clean sans for body
3. **Motion that breathes** — spring physics, earned celebrations

### 8.2 Color Palette

```css
:root {
  /* ── Surfaces ──────────────────────────────────────── */
  --surface-0: #faf6f0;       /* parchment — page background */
  --surface-1: #f3ede4;       /* warm cream — card background */
  --surface-2: #ebe3d7;       /* light tan — hover, active card */
  --surface-3: #ddd3c3;       /* deeper tan — borders, dividers */

  /* ── Ink ────────────────────────────────────────────── */
  --ink-0: #2c2418;           /* near-black walnut — primary text */
  --ink-1: #5c4f3c;           /* warm brown — secondary text */
  --ink-2: #8a7d6b;           /* muted — tertiary, timestamps */

  /* ── Accents ────────────────────────────────────────── */
  --sage: #7a9e7e;            /* active, success, done */
  --sage-dim: #b5ccb7;        /* sage at 50% — light backgrounds */
  --copper: #c07040;          /* warm action — start quest, CTA */
  --copper-dim: #d9a888;
  --hearth: #d4943a;          /* gold/amber — completion, celebration */
  --hearth-glow: #f5d78e;     /* celebration pulse color */
  --ember: #b5493a;           /* blocked, delete, interruption */
  --ember-dim: #d49e96;
  --slate: #6b7f8a;           /* neutral info, chronicle */
}
```

### 8.3 Semantic Color Mapping

| UI Concept | Color |
|------------|-------|
| Quest card: log | `--surface-1` border `--surface-3` |
| Quest card: active | Left border `--copper`, subtle `--copper-dim` bg tint |
| Quest card: blocked | Left border `--ember`, subtle `--ember-dim` bg tint |
| Quest card: done | Left border `--sage`, subtle `--sage-dim` bg tint |
| Frog badge | `--sage` background |
| Pomo timer: work | `--copper` progress bar |
| Pomo timer: break | `--sage` progress bar |
| Celebration flash | `--hearth-glow` |
| Trophy: gold | `--hearth` |
| Trophy: silver | `--surface-3` |
| Trophy: bronze | `--copper-dim` |
| Trophy: locked | `--ink-2` at 30% opacity |
| Heatmap: empty | `--surface-3` |
| Heatmap: light | `--sage-dim` |
| Heatmap: medium | `--sage` |
| Heatmap: heavy | `#3d6b41` (deep forest) |

### 8.4 Open Props Usage

Cherry-picked imports (not the full library):

```css
@import "open-props/easings";      /* --ease-in-*, --ease-out-*, --ease-spring-* */
@import "open-props/shadows";      /* --shadow-1 through --shadow-6 */
@import "open-props/sizes";        /* --size-1 through --size-15, --size-fluid-* */
@import "open-props/animations";   /* --animation-fade-in, --animation-scale-up */
```

These give us battle-tested easing curves, shadow elevation scale, and fluid spacing — without any classes or runtime.

### 8.5 Icons: Lucide

Inline SVG, not an icon font. Used for **UI controls only** (action buttons, nav). RPG flavor text (trophy names, headliners) keeps emoji.

| Control | Lucide icon |
|---------|-------------|
| Start quest | `play` |
| Block quest | `shield-ban` |
| Done quest | `check-circle` |
| Delete quest | `trash-2` |
| Frog toggle | `frog` (or keep emoji) |
| Pomo start | `flame` |
| Interrupt | `alert-triangle` |
| Receipt | `clipboard-list` |
| Dashboard | `bar-chart-3` |
| Refresh | `refresh-cw` |
| Settings | `settings` |

---

## 9. Layout & Responsive

### 9.1 Desktop (>= 1024px): Weighted Two-Column

```
┌──────────────────────────────────────────────────────────┐
│  HEADER: ✧ STARFORGE ✧ + fantasy date + quick actions    │
├─────────────────────────────────┬────────────────────────┤
│                                 │                        │
│   QUEST BOARD (65%)             │   SIDEBAR (35%)        │
│                                 │                        │
│   ┌── Log ──────────────────┐   │   ┌─ Chronicle ──────┐│
│   │ quest cards...          │   │   │ heatmap grid     ││
│   └─────────────────────────┘   │   └──────────────────┘│
│   ┌── In Battle ────────────┐   │   ┌─ Today ─────────┐│
│   │ quest cards...          │   │   │ timeline entries ││
│   └─────────────────────────┘   │   └──────────────────┘│
│   ┌── Blocked ──────────────┐   │   ┌─ Trophies ──────┐│
│   │ quest cards...          │   │   │ trophy cards     ││
│   └─────────────────────────┘   │   └──────────────────┘│
│   ┌── Done ─────────────────┐   │                        │
│   │ quest cards...          │   │                        │
│   └─────────────────────────┘   │                        │
│                                 │                        │
├─────────────────────────────────┴────────────────────────┤
│  STATS BAR: totals + live pomo status + receipt shortcut  │
└──────────────────────────────────────────────────────────┘
```

### 9.2 Tablet (768px–1023px): Stacked

Board full-width. Sidebar collapses to a horizontal strip below the board (heatmap + trophy summary). Full details in a slide-out drawer.

### 9.3 Mobile (< 768px): Single Column + Tabs

Board full-width. Chronicle and Trophies become tabs below. Pomo panel is always full-screen.

### 9.4 Pomo Panel: Full-Screen Overlay

When a pomo is active, the panel **takes over the entire viewport**. This is not a modal in a corner. It is an immersive focus screen.

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│           ⚔  Auth refactor  ⚔                            │
│        ⏯ Resumed · Lap 3 · Streak fire x 2              │
│                                                          │
│                  24 : 37                                  │
│           ████████████░░░░░░░░                            │
│                  62%                                      │
│                                                          │
│   ┌─ Your Charge ──────────────────────────────────────┐ │
│   │  "Squash the expiry bug in token middleware"        │ │
│   └────────────────────────────────────────────────────┘ │
│                                                          │
│   ┌─ Journey ──────────────────────────────────────────┐ │
│   │  filled filled filled half empty empty empty empty  │ │
│   └────────────────────────────────────────────────────┘ │
│                                                          │
│        [i] interrupt    [e] complete early                │
│        [x] abandon session                               │
│                                                          │
├────────────────────────────┬─────────────────────────────┤
│  TODAYS RECEIPT            │                             │
│  ────────────────────      │                             │
│  09:52  Auth Refactor      │                             │
│  Charge: squash expiry bug │                             │
│  Deed: bug squashed        │                             │
└────────────────────────────┴─────────────────────────────┘
```

---

## 10. Component Specs

### 10.1 Quest Card

```html
<article class="quest-card" data-status="active" data-id="a1b2c3d4">
  <div class="quest-card__header">
    <span class="quest-card__frog" x-show="frog">frog</span>
    <h3 class="quest-card__title">Auth refactor</h3>
    <button class="quest-card__menu">...</button>
  </div>
  <div class="quest-card__meta">
    <span>elapsed 2h 15m</span>
    <span>2 pomo today</span>
  </div>
  <div class="quest-card__actions">
    <!-- contextual by status -->
  </div>
</article>
```

**States:**
- Default: `--surface-1` bg, `--shadow-2`
- Hover: lifts to `--shadow-4`, border tints to status color
- Active (selected): `--surface-2` bg
- Dragging (future): `--shadow-5`, slight rotation

**Action buttons by status:**

| Status | Available actions |
|--------|-------------------|
| log | Start, Block, Delete, Frog, Pomo (disabled) |
| active | Block, Done, Delete, Frog, Pomo |
| blocked | Start (unblock), Delete, Frog |
| done | Delete |

### 10.2 Charge Gate

```html
<div class="pomo-gate charge-gate">
  <h2 class="gate__prompt">What will you have forged when this pomo ends?</h2>
  <p class="gate__hint">(name the one thing — a fix, a decision, a draft)</p>
  <form hx-post="/pomos/charge" hx-target="#pomo-panel" hx-swap="innerHTML">
    <input type="text" name="charge" required minlength="3" maxlength="120"
           autofocus placeholder="..." class="gate__input">
    <button type="submit" class="btn btn--copper" disabled>Begin Forging</button>
  </form>
</div>
```

- Button disabled until input has >= 3 characters (Alpine.js `x-bind:disabled`)
- Submit transitions to timer with a contraction animation

### 10.3 Deed Gate

```html
<div class="pomo-gate deed-gate">
  <h2 class="gate__prompt">Time's up, warrior. What did you claim?</h2>
  <p class="gate__hint">(a bug slain, a path cleared, a truth discovered)</p>
  <form hx-post="/pomos/deed" hx-target="#pomo-panel" hx-swap="innerHTML">
    <input type="text" name="deed" required minlength="3"
           autofocus class="gate__input">
    <div class="deed__forge-options">
      <button type="submit" name="forge_type" value="" class="btn btn--copper">Submit</button>
      <button type="submit" name="forge_type" value="hollow" class="btn btn--ghost">
        [h] Hollow
      </button>
      <button type="submit" name="forge_type" value="berserker" class="btn btn--ghost">
        [b] Berserker
      </button>
    </div>
  </form>
</div>
```

### 10.4 Break Choice Gate

```html
<div class="pomo-gate break-gate">
  <h2 class="gate__prompt">Your forge cools. Choose your rest.</h2>
  <div class="break-gate__options">
    <button hx-post="/pomos/break" hx-vals='{"choice":"short"}'
            class="btn btn--sage">Short (5m)</button>
    <button hx-post="/pomos/break" hx-vals='{"choice":"extended"}'
            class="btn btn--sage">Extended (10m)</button>
    <button hx-post="/pomos/break" hx-vals='{"choice":"long"}'
            class="btn btn--sage">Long (30m)</button>
    <button hx-post="/pomos/break" hx-vals='{"choice":"skip"}'
            class="btn btn--ghost">Skip Break</button>
    <button hx-post="/pomos/stop"
            class="btn btn--ghost">End Session</button>
  </div>
</div>
```

### 10.5 Timer Display

```html
<div class="timer" x-data="pomodoroTimer()" x-init="start()">
  <div class="timer__countdown" x-text="display">24:37</div>
  <div class="timer__bar">
    <div class="timer__bar-fill" :style="`width: ${percent}%`"></div>
  </div>
  <div class="timer__percent" x-text="`${Math.round(percent)}%`">62%</div>
</div>
```

Alpine.js component:

```javascript
function pomodoroTimer(totalSecs, startedAtISO) {
  return {
    remaining: totalSecs,
    total: totalSecs,
    display: '',
    percent: 100,
    interval: null,
    start() {
      const started = new Date(startedAtISO).getTime()
      this.interval = setInterval(() => {
        const elapsed = (Date.now() - started) / 1000
        this.remaining = Math.max(0, this.total - elapsed)
        this.percent = (this.remaining / this.total) * 100
        const m = Math.floor(this.remaining / 60)
        const s = Math.floor(this.remaining % 60)
        this.display = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
      }, 1000)
    },
    destroy() { clearInterval(this.interval) }
  }
}
```

### 10.6 Heatmap

```html
<div class="heatmap">
  <div class="heatmap__labels">
    <span>M</span><span>T</span><span>W</span><span>T</span>
    <span>F</span><span>S</span><span>S</span>
  </div>
  <div class="heatmap__grid">
    {% for cell in cells %}
    <div class="heatmap__cell heatmap__cell--{{ cell.level }}"
         title="{{ cell.date }}: {{ cell.count }} pomos"
         style="animation-delay: {{ loop.index * 20 }}ms">
    </div>
    {% endfor %}
  </div>
</div>
```

Levels: `empty` (0), `light` (1-2), `medium` (3-5), `heavy` (6+)

Cells are rounded squares (`border-radius: 3px`), 16x16px with 3px gap.

### 10.7 Trophy Card

```html
<article class="trophy-card trophy-card--{{ trophy.tier }}">
  <div class="trophy-card__header">
    <span class="trophy-card__badge">{{ tier_icon }}</span>
    <h4 class="trophy-card__name">{{ trophy.name }}</h4>
  </div>
  <p class="trophy-card__desc">{{ trophy.desc }}</p>
  <div class="trophy-card__progress">
    <div class="trophy-card__bar">
      <div class="trophy-card__bar-fill"
           style="width: {{ (trophy.progress / trophy.target * 100)|int }}%"></div>
    </div>
    <span class="trophy-card__label">{{ trophy.progress_label }}</span>
  </div>
  <div class="trophy-card__pr">PR: {{ trophy.pr }}</div>
</article>
```

---

## 11. Animation & Motion

All animations use **Motion** (motion.dev) for spring physics and DOM animation, triggered by Alpine.js or HTMX lifecycle events.

### 11.1 Animation Catalog

| Moment | Animation | Duration | Easing |
|--------|-----------|----------|--------|
| **Quest -> Done** | Gold ring pulse from card center; 12-20 particles burst (hearth/copper/sage); card floats to Done column | 800ms total | `--ease-spring-2` |
| **Quest -> Active** | Card slides right, left border fades to copper, subtle glow | 300ms | `--ease-out-3` |
| **Quest -> Blocked** | Card border pulses ember, slight shake (2px) | 400ms | `--ease-squish-2` |
| **Quest deleted** | Card scales down to 0.95, rotates 2deg, fades out | 400ms | `--ease-squish-2` |
| **Frog toggle on** | Frog badge bounces in (scale 0 -> 1.2 -> 1.0) | 300ms | `--ease-spring-3` |
| **Pomo complete (deed submitted)** | Screen edges flash hearth-glow; streak counter punches up | 500ms | `--ease-spring-2` |
| **Berserker forge** | Brief lightning flash effect on screen edges | 300ms | sharp ease |
| **Trophy tier earned** | Badge scales 0 -> 1.15 -> 1.0; shimmer sweep across card | 500ms | `--ease-spring-3` |
| **Heatmap load** | Cells fill in with 20ms stagger, left-to-right, top-to-bottom | ~1200ms total | `--ease-out-3` |
| **Charge -> Timer** | Input contracts into charge box; timer numbers fade in from below | 400ms | `--ease-spring-2` |
| **Timer -> Deed** | Screen edges briefly flash hearth-glow; timer fades; deed prompt fades in | 500ms | `--ease-out-3` |
| **Break -> Charge** | Full-screen gentle fade (opacity 0 -> 1, like waking up) | 600ms | `--ease-out-3` |
| **Toast enter** | Slides in from bottom-right, spring ease (Sonner default) | 300ms | spring |
| **Card hover** | Lifts from shadow-2 to shadow-4 | 150ms | `--ease-out-2` |
| **Receipt entry append** | New entry fades in + slides down from top of list | 300ms | `--ease-out-3` |

### 11.2 Celebration Particles (Done Quest)

```javascript
// animations.js
function celebrateDone(cardEl) {
  // Phase 1: card pulse
  animate(cardEl, {
    scale: [1, 1.06, 1],
    boxShadow: ['0 0 0 rgba(212,148,58,0)', '0 0 30px rgba(212,148,58,0.6)', '0 0 0 rgba(212,148,58,0)']
  }, { duration: 0.4, easing: 'ease-out' })

  // Phase 2: particles
  const rect = cardEl.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const colors = ['#d4943a', '#f5d78e', '#c07040', '#7a9e7e']

  for (let i = 0; i < 16; i++) {
    const dot = document.createElement('div')
    dot.className = 'particle'
    dot.style.cssText = `
      position:fixed; left:${cx}px; top:${cy}px;
      width:${4 + Math.random()*4}px; height:${4 + Math.random()*4}px;
      border-radius:${Math.random() > 0.5 ? '50%' : '2px'};
      background:${colors[i % colors.length]};
      pointer-events:none; z-index:9999;
    `
    document.body.appendChild(dot)

    const angle = (Math.PI * 2 * i) / 16 + (Math.random() - 0.5) * 0.5
    const dist = 60 + Math.random() * 80
    const tx = Math.cos(angle) * dist
    const ty = Math.sin(angle) * dist - 30  // bias upward

    animate(dot, {
      x: [0, tx], y: [0, ty],
      opacity: [1, 0], scale: [1, 0.3]
    }, { duration: 0.6 + Math.random() * 0.3, easing: 'ease-out' })
      .finished.then(() => dot.remove())
  }
}
```

### 11.3 HTMX Integration

Animations hook into HTMX's lifecycle events:

```javascript
// Listen for HTMX swaps and animate based on data attributes
document.body.addEventListener('htmx:afterSwap', (e) => {
  const trigger = e.detail.requestConfig?.headers?.['X-Animation']
  if (trigger === 'quest-done') celebrateDone(e.detail.elt)
  if (trigger === 'quest-delete') animateOut(e.detail.elt)
  // etc.
})

// Stagger new elements on swap
document.body.addEventListener('htmx:afterSettle', (e) => {
  e.detail.elt.querySelectorAll('[data-animate-in]').forEach((el, i) => {
    animate(el, { opacity: [0, 1], y: [10, 0] },
      { delay: i * 0.03, duration: 0.3, easing: spring() })
  })
})
```

The server sets `X-Animation` response headers to signal which animation to play. The client reads these headers and dispatches.

---

## 12. Typography

### 12.1 Font Stack

| Role | Font | Fallback |
|------|------|----------|
| Display / headings | Crimson Pro | Georgia, serif |
| Body / UI | Inter | system-ui, sans-serif |
| Timer / monospace | JetBrains Mono | monospace |

All self-hosted as variable woff2 files. No Google Fonts CDN dependency.

### 12.2 Type Scale

| Use | Font | Size | Weight |
|-----|------|------|--------|
| Page title ("STARFORGE") | Crimson Pro | `--size-fluid-4` (~2rem) | 600, letter-spacing 0.3em |
| Section headers (LOG, IN BATTLE) | Crimson Pro | `--size-fluid-2` (~1.25rem) | 600 |
| Quest card title | Inter | `--size-fluid-1` (~1.1rem) | 500 |
| Body / secondary text | Inter | `--size-1` (1rem) | 400 |
| Timestamps, metadata | Inter | `--size-0` (0.875rem) | 400, color `--ink-2` |
| Timer countdown | JetBrains Mono | `--size-fluid-5` (~3rem) | 700 |
| Gate prompts ("What will you...") | Crimson Pro | `--size-fluid-3` (~1.5rem) | 400 italic |
| Charge/Deed text in receipt | Inter | `--size-1` (1rem) | 400 |
| Stats bar | Inter | `--size-0` (0.875rem) | 400 |
| Trophy card name | Inter | `--size-fluid-1` (~1.1rem) | 600 |

---

## 13. Data Migration

### 13.1 JSON to SQLite Migration Script

`scripts/migrate_json.py` reads the three existing JSON files and inserts into SQLite:

| Source | Target |
|--------|--------|
| `quests.json` | `quests` table |
| `pomodoros.json` | `pomo_sessions` + `pomo_segments` tables |
| `trophies.json` | `trophy_records` table |

**Mapping notes:**

- Quest `id` (8-char hex) maps directly to `quests.id`
- Pomo session fields map 1:1
- Segments are extracted from `session.segments[]` array and inserted as individual rows in `pomo_segments` with a FK to the session
- Legacy `intent`/`retro` keys map to `charge`/`deed`
- Boolean fields (`completed`, `frog`, `early_completion`) convert from Python bool to SQLite integer (0/1)
- `break_size: "extended"` is preserved as-is

**The JSON files remain as backups.** The migration is idempotent (checks for existing data before inserting).

### 13.2 Running the Migration

```bash
# From questlog-web/
python scripts/migrate_json.py --json-dir ../questlog/ --db ./questlog.db
```

---

## 14. Extensibility

Each future feature follows the module pattern: new directory under `app/`, new tables in a migration, new route registration in `main.py`.

### 14.1 Planned Future Modules

| Feature | New Tables | Directory | Integration Point |
|---------|-----------|-----------|-------------------|
| **Recurring tasks** | `recurring_rules` (cron expr, quest template, last_triggered) | `app/recurring/` | On page load: check rules, auto-create quests from templates |
| **Habit dashboard** | `habits`, `habit_entries` | `app/habits/` | New sidebar section or tab. Daily check-in UI. |
| **Tiny experiments** | `experiments`, `experiment_logs` | `app/experiments/` | New tab. Time-boxed A/B self-experiments with journaling. |
| **LLM standup** | None (reads `pomo_segments`) | `app/standup/` | Button on receipt page. Calls LLM API with `get_today_receipt()` data. |
| **Weekly review** | `weekly_reviews` | `app/reviews/` | Aggregates quest + pomo + trophy data into a weekly summary. |

### 14.2 Adding a New Module (Checklist)

1. Create `app/{module}/` with `__init__.py`, `routes.py`, `queries.py`, `templates/`
2. Add migration file: `migrations/NNN_{module}.sql`
3. Register router in `app/main.py`: `app.include_router(module.routes.router)`
4. Add sidebar/tab entry in `shared/templates/base.html`
5. Done. No changes to existing modules required.

---

## 15. Implementation Phases

### Phase 1: Foundation

**Goal:** Deployable app with quest board working.

- [ ] FastAPI scaffold (`main.py`, lifespan)
- [ ] SQLite setup (`db.py`, `migrate()`, WAL mode)
- [ ] `config.py` — timezone, pomo durations, valid sources
- [ ] `migrations/001_initial.sql`
- [ ] `shared/templates/base.html` — page shell with CSS/JS imports
- [ ] `static/reset.css` + `static/tokens.css` + `static/style.css` (foundation)
- [ ] Self-host fonts (Inter, Crimson Pro, JetBrains Mono woff2)
- [ ] Vendor static JS (htmx, alpine, motion, sonner)
- [ ] Quest CRUD: routes, queries, templates
- [ ] Quest board UI with 4 status columns
- [ ] HTMX transitions for quest state changes
- [ ] Stats bar (static version, no live pomo)
- [ ] Card hover/action animations

**Deliverable:** A working quest board in the browser with earthy styling.

### Phase 2: Pomodoro Engine

**Goal:** Full charge/deed/timer loop working.

- [ ] `pomos/state.py` — in-memory timer state
- [ ] `pomos/queries.py` — session CRUD, segment CRUD
- [ ] Charge gate (form + validation)
- [ ] Timer display (Alpine.js countdown)
- [ ] SSE endpoint (`/pomos/tick`)
- [ ] Deed gate (form + forge type buttons)
- [ ] Break choice gate
- [ ] Interruption flow
- [ ] Early completion (Swiftblade)
- [ ] Session stop/end
- [ ] Receipt view
- [ ] Pomo panel full-screen overlay
- [ ] Pomo mode transitions (charge -> timer -> deed -> break)
- [ ] Break nudge timer
- [ ] Stats bar live updates during pomo

**Deliverable:** Complete pomo loop identical to TUI behavior.

### Phase 3: Chronicle & Trophies

**Goal:** Full feature parity with TUI.

- [ ] Chronicle heatmap (queries + template + stagger animation)
- [ ] Today's timeline
- [ ] Trophy computation (port from `trophy_store.py`)
- [ ] Trophy panel (cards + tier display)
- [ ] Dashboard metrics modal (port `compute_metrics` + `compute_pomo_metrics`)
- [ ] Trophy tier-earned animation
- [ ] Heatmap cell hover tooltips

**Deliverable:** All three panels working — full TUI feature parity.

### Phase 4: Polish & Migration

**Goal:** Production-ready, data migrated.

- [ ] `scripts/migrate_json.py`
- [ ] Celebration animations (quest done particles, pomo forge flash)
- [ ] Sonner toast integration for all notifications
- [ ] Responsive breakpoints (tablet, mobile)
- [ ] Keyboard shortcuts (matching TUI where sensible)
- [ ] Dockerfile + docker-compose.yml
- [ ] Final CSS polish pass

**Deliverable:** Deployable, data-migrated, polished app.

### Phase 5: Extensions (future, post-launch)

- [ ] Recurring tasks module
- [ ] Habit dashboard module
- [ ] Tiny experiments module
- [ ] LLM standup generation
- [ ] Weekly review

---

## 16. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **HTMX + pomo state machine complexity** | Medium | The charge -> timer -> deed -> break cycle has 5+ states. Use Alpine.js `x-data` for panel state, HTMX for server round-trips at each gate. SSE for timer events. Keep state machine logic on server, not client. |
| **Timer drift in backgrounded tabs** | Low | Server-authoritative time. SSE push corrects on reconnect. Client countdown is cosmetic. |
| **SQLite write contention** | None | Single user = zero contention. WAL mode for safety. |
| **Animation jank on low-end devices** | Low | All animations use compositor-friendly properties (transform, opacity). Motion auto-falls-back to CSS transitions. Particles are < 20 DOM elements, removed after animation. |
| **Scope creep from future modules** | Medium | Module pattern isolates features. Ship Phase 1-4 before starting Phase 5. Each extension is independent. |
| **Self-hosting friction** | Low | Single Docker container. No external services. `docker compose up` is the entire deploy. |
| **Open Props CDN dependency** | Low | Vendor the CSS file into `static/`. It's just custom properties — no runtime. |

---

## 17. Dependencies

### 17.1 Python

```toml
[project]
name = "questlog-web"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "aiosqlite>=0.20",
    "sse-starlette>=2.0",
    "python-multipart>=0.0.9",
]
```

**6 Python dependencies.** No ORM, no task queue, no cache layer.

### 17.2 Frontend (Static Files, No Build Step)

| Library | Version | Size (min+gzip) | Purpose |
|---------|---------|-----------------|---------|
| HTMX | 2.x | 14KB | Dynamic partial page updates |
| Alpine.js | 3.x | 15KB | Client-side reactivity (timer, forms) |
| Motion | 11.x | 18KB | Spring physics, DOM animations |
| Sonner | 1.x | 5KB | Toast notifications |
| Open Props | latest | ~3KB (cherry-picked) | CSS design tokens |
| Lucide | latest | per-icon (~300B each) | SVG icons |

**Total JS: ~52KB. Total CSS: ~20KB. Fonts: ~80KB.**

### 17.3 Deployment

```yaml
# docker-compose.yml
services:
  questlog:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data  # persists questlog.db
    environment:
      - QUESTLOG_DB=/app/data/questlog.db
      - QUESTLOG_TZ=Asia/Kolkata
```

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app/ app/
COPY migrations/ migrations/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

*End of spec. This document is the single source of truth for QuestLog Web implementation.*
