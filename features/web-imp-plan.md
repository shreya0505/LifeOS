● Implementation Plan: QuestLog Web (v2 Architecture)

  Requirements Restatement

  Build a single-user, self-hosted web app that brings QuestLog TUI to the browser, using a shared core/ package architecture. The web app must:

  - Deliver full TUI feature parity (quests, pomos, trophies, chronicle, dashboard)
  - Use the "Tavern Workbench" aesthetic with spring-physics animations
  - Stack: FastAPI + Jinja2 + HTMX + Alpine.js + Motion + SQLite
  - Share all business logic with the TUI via core/ — no duplicated computation
  - Total JS < 60KB, CSS < 25KB, no build step

  ---
  Phase 0: Core Extraction (Prerequisite)

  Goal: Restructure into monorepo. TUI works identically after.

  0.1 Create core/ package skeleton

  - core/__init__.py
  - core/config.py ← move from config.py (POMO_CONFIG, VALID_SOURCES, USER_TZ)
  - Verify: from core.config import POMO_CONFIG works

  0.2 Extract utilities

  - core/utils.py ← move helper functions from utils.py (today_local, to_local_date, fantasy_date, format_duration, fmt_compact, segment_duration, classify_delta, delta_arrow, fmt_delta_*, parse_dt,
  get_elapsed)
  - core/metrics.py ← extract compute_metrics() and compute_pomo_metrics() from utils.py (already parameterized — zero logic change)

  0.3 Refactor pomo_queries (parameter injection)

  - core/pomo_queries.py ← move from pomo_queries.py
  - Add sessions: list[dict] parameter to all 7 functions
  - Remove internal load_pomos() calls
  - Functions affected: get_today_receipt, get_quest_pomo_total, get_quest_lap_history, get_quest_segment_journey, get_today_timeline, get_all_pomo_counts_today, get_berserker_stats

  0.4 Extract trophy computation

  - core/trophy_defs.py ← extract TROPHY_DEFS list from trophy_store.py
  - core/trophy_compute.py ← extract compute_trophies() from trophy_store.py
  - Refactor signature: compute_trophies(sessions, quests, prs) -> (result, updated_prs)
  - Remove internal load_pomos(), load_quests(), _load_prs(), _save_prs() calls
  - Caller handles persistence

  0.5 Create storage protocols + JSON backend

  - core/storage/__init__.py
  - core/storage/protocols.py — QuestRepo, PomoRepo, TrophyPRRepo Protocol classes
  - core/storage/json_backend.py — JsonQuestRepo, JsonPomoRepo, JsonTrophyPRRepo
    - Wraps existing quest_store.py / pomo_store.py / trophy PR I/O logic
    - Implements the Protocol interfaces

  0.6 Extract PomoEngine

  - core/pomo_engine.py — extract state machine from main.py
  - Event dataclasses: SegmentStarted, SegmentEnded, DeedSubmitted, BreakChosen, Interrupted, SessionStopped
  - Methods: start_session, start_segment, tick/remaining, end_segment, submit_charge, submit_deed, choose_break, interrupt, complete_early, stop_session
  - Engine accepts PomoRepo via constructor, owns no UI or timers

  0.7 Restructure TUI into tui/ package

  - Move main.py → tui/main.py
  - Move quest_panel.py, chronicle_panel.py, trophy_panel.py, pomo_panel.py, modals.py, renderers.py, styles.tcss → tui/
  - Update all imports to use core.*
  - tui/main.py: instantiate PomoEngine(JsonPomoRepo(...)), delegate state transitions
  - Update call sites: get_today_receipt(repo.load_all()) etc.

  0.8 Verify TUI works identically

  - Run python -m tui.main — all features must work
  - Manual smoke test: add quest, start, pomo cycle, trophies, chronicle

  0.9 Unit tests for core/

  - Test pomo_queries functions with fixture data
  - Test trophy_compute with fixture data
  - Test PomoEngine state transitions (charge → work → deed → break → charge)
  - Test metrics.compute_metrics / compute_pomo_metrics with fixture data
  - Test storage protocol compliance for JSON backend

  Deliverable: Same app, cleaner architecture. ~200 lines moved, ~50 lines of Protocol glue, ~30 import updates. Zero logic changes.

  Complexity: Medium — mostly mechanical moves, but the PomoEngine extraction requires careful state management.

  Risk: TUI regression. Mitigation: Git commit per logical move, test after each.

  ---
  Phase 1: Web Foundation (Quest Board)

  Goal: Deployable web app with quest board working.

  1.1 FastAPI scaffold

  - web/__init__.py
  - web/app.py — FastAPI app, lifespan hook (run migrations on startup), Jinja2 template config, static file mount, CORS middleware
  - web/db.py — SQLite connection with WAL mode, migrate() function, get_db() dependency
  - web/deps.py — FastAPI dependencies: get_quest_repo(), get_pomo_repo(), etc.
  - pyproject.toml — single package with [project.optional-dependencies] for tui (textual, rich) and web (fastapi, uvicorn, jinja2, aiosqlite, sse-starlette)

  1.2 Database setup

  - migrations/001_initial.sql — all CREATE TABLE statements per v1 spec §4.1
  - core/storage/sqlite_backend.py — SqliteQuestRepo, SqlitePomoRepo, SqliteTrophyPRRepo
  - Critical: SqlitePomoRepo.load_all() must JOIN sessions + segments into nested dicts

  1.3 Frontend foundation

  - web/static/reset.css — Josh Comeau's modern reset
  - web/static/tokens.css — Open Props cherry-picks + earthy palette (v1 spec §8.2)
  - web/static/style.css — component styles foundation
  - Vendor static JS: htmx.min.js, alpine.min.js, motion.min.js, sonner.min.js
  - Self-host fonts: Inter, Crimson Pro, JetBrains Mono (woff2)
  - web/shared/templates/base.html — page shell with CSS/JS imports, nav, layout grid

  1.4 Quest CRUD

  - web/quests/routes.py — GET /, GET/POST/PATCH/DELETE /quests/*
  - web/quests/templates/board.html — 4-column kanban (log, active, blocked, done)
  - web/quests/templates/column.html — single status column
  - web/quests/templates/card.html — quest card with contextual actions
  - All routes use SqliteQuestRepo via core.storage.sqlite_backend
  - HTMX partial swaps for state transitions
  - Frog toggle

  1.5 Stats bar (static)

  - web/shared/templates/stats_bar.html — totals, no live pomo yet

  1.6 Card interactions

  - Hover lift animation (shadow-2 → shadow-4)
  - Status transition animations (Motion)
  - Confirm modal for delete

  Deliverable: Working quest board in browser with earthy styling, HTMX transitions.

  Complexity: Medium — mostly templates + one new SQLite backend.

  ---
  Phase 2: Pomodoro Engine (Web)

  Goal: Full charge/deed/timer loop working in browser.

  2.1 Pomo engine wiring

  - Instantiate PomoEngine(SqlitePomoRepo(...)) as app-level singleton (single user)
  - web/deps.py — get_pomo_engine() dependency

  2.2 Pomo routes

  - web/pomos/routes.py:
    - POST /pomos/start → initialize engine, return charge gate
    - POST /pomos/charge → engine.submit_charge(), engine.start_segment("work"), return timer
    - POST /pomos/deed → engine.submit_deed(), return break choice
    - POST /pomos/break → engine.choose_break(), return timer or charge or stop
    - POST /pomos/interrupt → engine.interrupt(), return charge gate
    - POST /pomos/complete-early → engine.complete_early(), return deed gate
    - POST /pomos/stop → engine.stop_session(), return empty + OOB board refresh

  2.3 SSE endpoint

  - web/pomos/sse.py — GET /pomos/tick
  - Polls engine.remaining() every second
  - Pushes event: tick with remaining seconds
  - Pushes event: segment-complete with deed gate HTML when timer expires
  - Uses sse-starlette

  2.4 Pomo templates

  - web/pomos/templates/panel.html — full-screen overlay container
  - web/pomos/templates/charge.html — charge gate form (v1 spec §10.2)
  - web/pomos/templates/timer.html — Alpine.js countdown + progress bar (v1 spec §10.5)
  - web/pomos/templates/deed.html — deed gate form + forge type buttons (v1 spec §10.3)
  - web/pomos/templates/break_choice.html — break options (v1 spec §10.4)
  - web/pomos/templates/interrupt.html — interruption reason form
  - web/pomos/templates/receipt.html — daily receipt (calls core.pomo_queries.get_today_receipt)

  2.5 Timer display

  - Alpine.js pomodoroTimer() component (v1 spec §10.5)
  - Client-side setInterval(1000) for cosmetic countdown
  - SSE EventSource for server-authoritative events
  - Gate transitions: charge → timer (contraction animation), timer → deed (hearth flash)

  2.6 Stats bar live updates

  - During active pomo: show quest title, segment type, timer, streak
  - HTMX poll or SSE-driven OOB swap

  2.7 Break nudge

  - Server-side 5-minute interval nudge via SSE when between segments

  Deliverable: Complete pomo loop in browser — identical behavior to TUI.

  Complexity: High — SSE + Alpine.js timer coordination, full state machine integration.

  Risk: HTMX + pomo state machine gate complexity. Mitigation: PomoEngine emits typed events, each route handler simply pattern-matches on the event type and returns the corresponding template.

  ---
  Phase 3: Chronicle & Trophies

  Goal: Full feature parity with TUI.

  3.1 Chronicle panel

  - web/chronicle/routes.py:
    - GET /chronicle — calls core.pomo_queries.get_today_timeline(sessions) and heatmap data
  - web/chronicle/templates/panel.html — sidebar section
  - web/chronicle/templates/heatmap.html — activity grid with stagger animation (v1 spec §10.6)
  - web/chronicle/templates/timeline.html — today's session segments
  - Heatmap cell hover tooltips

  3.2 Trophy panel

  - web/trophies/routes.py:
    - GET /trophies — calls core.trophy_compute.compute_trophies(sessions, quests, prs)
  - web/trophies/templates/panel.html — trophy list
  - web/trophies/templates/card.html — single trophy card with tier, progress bar, PR (v1 spec §10.7)
  - Trophy tier-earned animation

  3.3 Dashboard metrics

  - web/dashboard/routes.py:
    - GET /dashboard — calls core.metrics.compute_metrics(quests) + compute_pomo_metrics(sessions)
  - web/dashboard/templates/modal.html — metrics overlay with quest + pomo metrics
  - Delta arrows, color coding (good/bad/neutral)

  3.4 HTMX refresh wiring

  - After pomo deed/completion: OOB swap trophy panel, chronicle panel
  - After quest state change: OOB swap stats bar
  - 60-second stats bar poll

  Deliverable: All three panels working — full TUI feature parity.

  Complexity: Low-Medium — mostly templates wiring to existing core/ functions.

  ---
  Phase 4: Polish & Migration

  Goal: Production-ready, data migrated, deployable.

  4.1 Data migration

  - scripts/migrate_json.py — reads quests.json, pomodoros.json, trophies.json, inserts into SQLite
  - Handles legacy intent/retro → charge/deed mapping
  - Idempotent (checks for existing data)

  4.2 Celebration animations

  - web/static/animations.js — per v1 spec §11
  - Quest done: gold ring pulse + 16 particles burst
  - Pomo complete: screen edge hearth flash
  - Berserker forge: lightning flash
  - Trophy earned: badge scale + shimmer sweep
  - HTMX afterSwap / afterSettle hooks for trigger dispatch

  4.3 Toast integration

  - Sonner toast for all notifications (quest added, pomo complete, interruption, etc.)
  - Server sends HX-Trigger headers; Alpine.js dispatches to Sonner

  4.4 Responsive breakpoints

  - Desktop (≥1024px): weighted two-column per v1 spec §9.1
  - Tablet (768-1023px): stacked, sidebar becomes horizontal strip
  - Mobile (<768px): single column + tabs, pomo panel always full-screen

  4.5 Keyboard shortcuts

  - Match TUI where sensible: a add, s start, b block, d done, x delete, f frog, t pomo
  - Alpine.js @keydown.window handlers

  4.6 Deployment

  - Dockerfile — Python 3.12-slim, single container
  - docker-compose.yml — volume mount for questlog.db
  - Health check endpoint

  4.7 Final CSS polish pass

  - Verify earthy palette consistency
  - Noise texture overlay on card surfaces
  - All hover/focus/active states intentional
  - Cross-browser check (Chrome, Firefox, Safari)

  Deliverable: Deployable, data-migrated, polished app.

  Complexity: Medium — animation JS is the largest new code.

  ---
  Phase 5: Extensions (Post-Launch)

  - Recurring tasks module
  - Habit dashboard module
  - Tiny experiments module
  - LLM standup generation
  - Weekly review

  Each extension follows the module pattern: new directory under web/, new migration, new route registration. No changes to existing modules.

  ---
  Dependency Graph

  Phase 0 (core extraction)
      │
      ├──► Phase 1 (quest board) ──► Phase 2 (pomo engine) ──► Phase 3 (chronicle/trophies)
      │                                                              │
      │                                                              ▼
      │                                                        Phase 4 (polish)
      │                                                              │
      └── TUI continues working ◄────────────────────────────────────┘
                                                                     │
                                                                Phase 5 (extensions)

  Critical Risks

  ┌────────────────────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────┐
  │                  Risk                  │ Severity │                               Mitigation                                │
  ├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
  │ Phase 0 breaks TUI                     │ High     │ Git commit per move, smoke test after each. Revert-friendly.            │
  ├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
  │ Dict shape divergence (JSON vs SQLite) │ Medium   │ Unit test: both backends return identical shapes for same seed data.    │
  ├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
  │ PomoEngine extraction misses edge case │ Medium   │ Port all existing TUI pomo tests. Add state machine fuzz tests.         │
  ├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
  │ SSE + Alpine timer coordination        │ Medium   │ Server is authoritative. Client is cosmetic. SSE corrects on reconnect. │
  ├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
  │ Scope creep in animations              │ Low      │ Animations are Phase 4. Ship functional app first (Phases 1-3).         │
  └────────────────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────┘