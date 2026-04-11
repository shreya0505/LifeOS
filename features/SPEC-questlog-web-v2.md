# QuestLog Web v2 — Shared-Core Revision

**Author:** Principal Engineering  
**Status:** Ready for Review  
**Version:** 2.0  
**Date:** April 9, 2026  
**Supersedes:** SPEC-questlog-web.md v1.0

---

## 0. Why This Revision Exists

The v1 spec designed the web app as a **ground-up rewrite** — separate project, separate
data layer, separate business logic. This wastes ~800 lines of battle-tested Python that
already implements:

- Trophy computation (7 trophies, tiered, with PRs) — 300 lines
- Pomo analytical queries (receipt, timeline, heatmap, berserker stats) — 157 lines
- Productivity metrics (velocity, cycle time, pickup speed, etc.) — 200 lines
- Config (POMO_CONFIG, VALID_SOURCES, USER_TZ) — 29 lines
- Utility helpers (timezone, formatting, duration) — 100 lines
- Pomo state machine (charge → timer → deed → break → charge) — ~250 lines

The v1 approach would rewrite all of this as SQL queries and new Python modules, creating
two divergent implementations that must be kept in sync forever. That is an unmaintainable
architecture for a single developer.

**This revision restructures the project so TUI and web share a single `core/` package.**
The northstar (features, UX, design system, animations) remains identical to v1. Only the
internal architecture changes.

---

## 1. What Changes from v1

| Aspect | v1 Spec | v2 Revision |
|--------|---------|-------------|
| Project structure | Separate `questlog-web/` repo | Monorepo: `questlog/` with `core/`, `tui/`, `web/` |
| Business logic | Rewritten in SQL queries per module | Shared `core/` package, imported by both |
| Storage | SQLite only, new query modules | Storage protocol with JSON + SQLite backends |
| Pomo state machine | Reimplemented in `pomos/state.py` | Shared `PomoEngine` class in `core/` |
| Trophy computation | Reimplemented in `trophies/compute.py` | Existing `trophy_compute.py` moved to `core/` |
| Metrics | Reimplemented in `dashboard/queries.py` | Existing `compute_metrics` / `compute_pomo_metrics` in `core/` |
| Config | Duplicated in `app/config.py` | Single `core/config.py` |
| Data migration | JSON → SQLite one-time script | Same, but JSON backend remains functional for TUI |

**What does NOT change from v1:**
- Everything in sections 1, 2 (requirements), 6 (routes), 7 (timer architecture),
  8 (design system), 9 (layout), 10 (component specs), 11 (animations),
  12 (typography), 14 (extensibility), 16 (risks), 17 (dependencies)
- The northstar UX, aesthetics, and feature set are identical

---

## 2. Reuse Audit — Module-by-Module

### 2.1 Fully Reusable (move to `core/`, zero changes)

| Current File | Core Location | Lines | Notes |
|-------------|--------------|-------|-------|
| `config.py` | `core/config.py` | 29 | POMO_CONFIG, VALID_SOURCES, USER_TZ — pure data |
| `utils.py` (helpers) | `core/utils.py` | ~110 | `today_local`, `to_local_date`, `fantasy_date`, `format_duration`, `fmt_compact`, `segment_duration`, `classify_delta`, `delta_arrow`, `fmt_delta_*` — pure functions |
| `utils.py` (metrics) | `core/metrics.py` | ~120 | `compute_metrics(quests)` and `compute_pomo_metrics(sessions)` — already accept data as parameters |

### 2.2 Reusable After Parameter Injection (surgical refactor)

| Current File | Core Location | Lines | Refactor Needed |
|-------------|--------------|-------|-----------------|
| `pomo_queries.py` | `core/pomo_queries.py` | 157 | Each function calls `load_pomos()` internally. Add `sessions: list[dict]` parameter, remove internal load. TUI call sites pass `load_pomos()`. Web call sites pass SQL results. |
| `trophy_store.py` (computation) | `core/trophy_compute.py` | ~300 | `compute_trophies()` calls `load_pomos()` and `load_quests()`. Refactor to `compute_trophies(sessions, quests, prs)` → returns results + updated PRs. Caller handles persistence. |

### 2.3 Extractable from `main.py` (new shared class)

| Logic Block | Core Location | Lines | What It Does |
|------------|--------------|-------|--------------|
| Pomo state machine | `core/pomo_engine.py` | ~250 | `PomoEngine` class owning: segment lifecycle, charge/deed/break gates, streak/momentum tracking, interruption handling, break nudge scheduling. Emits events; UI layer subscribes. |

### 2.4 Not Reusable (presentation-specific)

| File | Reason | Stays In |
|------|--------|----------|
| `quest_panel.py` | Textual widgets | `tui/` |
| `chronicle_panel.py` | Textual widgets | `tui/` |
| `trophy_panel.py` | Textual widgets | `tui/` |
| `pomo_panel.py` | Textual widgets | `tui/` |
| `modals.py` | Textual modals | `tui/` |
| `renderers.py` | Rich markup, pixel art digits | `tui/` |
| `styles.tcss` | Textual CSS | `tui/` |

---

## 3. Revised Project Structure

```
questlog/
├── core/                          # Shared business logic (NEW package)
│   ├── __init__.py
│   ├── config.py                  # ← from root config.py (unchanged)
│   ├── utils.py                   # ← from root utils.py (helpers only)
│   ├── metrics.py                 # ← extracted from utils.py (compute_metrics, compute_pomo_metrics)
│   ├── pomo_queries.py            # ← from root (refactored: accepts sessions param)
│   ├── trophy_compute.py          # ← from trophy_store.py (computation only, accepts data params)
│   ├── trophy_defs.py             # ← TROPHY_DEFS list extracted (used by both compute + display)
│   ├── pomo_engine.py             # ← NEW: extracted state machine from main.py
│   └── storage/
│       ├── __init__.py
│       ├── protocols.py           # QuestRepo, PomoRepo, TrophyPRRepo protocols
│       ├── json_backend.py        # ← from quest_store.py + pomo_store.py + trophy PR I/O
│       └── sqlite_backend.py      # NEW: same protocols, SQLite implementation
│
├── tui/                           # TUI app (existing files, updated imports)
│   ├── __init__.py
│   ├── main.py                    # ← from root (uses core.PomoEngine + core.storage.json_backend)
│   ├── quest_panel.py             # ← from root
│   ├── chronicle_panel.py         # ← from root
│   ├── trophy_panel.py            # ← from root
│   ├── pomo_panel.py              # ← from root
│   ├── modals.py                  # ← from root
│   ├── renderers.py               # ← from root
│   └── styles.tcss                # ← from root
│
├── web/                           # Web app (NEW, per v1 spec sections 6-12)
│   ├── __init__.py
│   ├── app.py                     # FastAPI app, lifespan, middleware
│   ├── db.py                      # SQLite connection, migrate(), get_db()
│   ├── deps.py                    # FastAPI dependencies (get repos, get engine)
│   │
│   ├── quests/
│   │   ├── __init__.py
│   │   ├── routes.py              # Quest CRUD — calls core.storage.sqlite_backend
│   │   └── templates/
│   │       ├── board.html
│   │       ├── column.html
│   │       └── card.html
│   │
│   ├── pomos/
│   │   ├── __init__.py
│   │   ├── routes.py              # Pomo routes — delegates to core.PomoEngine
│   │   ├── sse.py                 # SSE tick endpoint
│   │   └── templates/
│   │       ├── panel.html
│   │       ├── charge.html
│   │       ├── timer.html
│   │       ├── deed.html
│   │       ├── break_choice.html
│   │       ├── interrupt.html
│   │       └── receipt.html
│   │
│   ├── trophies/
│   │   ├── __init__.py
│   │   ├── routes.py              # Calls core.trophy_compute (no rewrite!)
│   │   └── templates/
│   │       ├── panel.html
│   │       └── card.html
│   │
│   ├── chronicle/
│   │   ├── __init__.py
│   │   ├── routes.py              # Calls core.pomo_queries (no rewrite!)
│   │   └── templates/
│   │       ├── panel.html
│   │       ├── heatmap.html
│   │       └── timeline.html
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── routes.py              # Calls core.metrics (no rewrite!)
│   │   └── templates/
│   │       └── modal.html
│   │
│   ├── shared/
│   │   └── templates/
│   │       ├── base.html
│   │       ├── stats_bar.html
│   │       └── components/
│   │           ├── progress_bar.html
│   │           ├── badge.html
│   │           ├── stat_row.html
│   │           ├── confirm_modal.html
│   │           └── toast.html
│   │
│   └── static/                    # Per v1 spec section 17.2
│       ├── reset.css
│       ├── tokens.css
│       ├── style.css
│       ├── htmx.min.js
│       ├── alpine.min.js
│       ├── motion.min.js
│       ├── sonner.min.js
│       ├── animations.js
│       └── fonts/
│
├── migrations/
│   └── 001_initial.sql            # Per v1 spec section 4.1
│
├── scripts/
│   └── migrate_json.py            # JSON → SQLite (per v1 spec section 13)
│
├── features/                      # Specs (unchanged)
│   ├── SPEC-questlog-web.md
│   └── SPEC-questlog-web-v2.md
│
├── pyproject.toml                 # Single package with optional deps: [tui], [web]
├── Dockerfile
├── docker-compose.yml
└── CLAUDE.md
```

---

## 4. Storage Protocol Design

### 4.1 Protocols

```python
# core/storage/protocols.py
from typing import Protocol


class QuestRepo(Protocol):
    def load_all(self) -> list[dict]: ...
    def add(self, title: str) -> dict: ...
    def update_status(self, quest_id: str, status: str) -> dict | None: ...
    def delete(self, quest_id: str) -> dict | None: ...
    def toggle_frog(self, quest_id: str) -> dict | None: ...


class PomoRepo(Protocol):
    def load_all(self) -> list[dict]: ...
    def start_session(self, quest_id: str, quest_title: str) -> dict: ...
    def get_session(self, session_id: str) -> dict | None: ...
    def add_segment(self, session_id: str, **kwargs) -> dict | None: ...
    def update_segment_deed(self, session_id: str, lap: int,
                            deed: str, forge_type: str | None = None) -> None: ...
    def end_session(self, session_id: str) -> dict | None: ...


class TrophyPRRepo(Protocol):
    def load_prs(self) -> dict: ...
    def save_prs(self, prs: dict) -> None: ...
```

### 4.2 JSON Backend (wraps existing code)

```python
# core/storage/json_backend.py
# Wraps the existing quest_store.py / pomo_store.py / trophy_store.py I/O functions.
# No logic changes — just implements the Protocol interface.

class JsonQuestRepo:
    """Implements QuestRepo backed by quests.json."""
    def __init__(self, path: Path): ...
    # Methods delegate to existing load/save/add/update/delete/toggle_frog logic

class JsonPomoRepo:
    """Implements PomoRepo backed by pomodoros.json."""
    def __init__(self, path: Path): ...

class JsonTrophyPRRepo:
    """Implements TrophyPRRepo backed by trophies.json."""
    def __init__(self, path: Path): ...
```

### 4.3 SQLite Backend (new)

```python
# core/storage/sqlite_backend.py
# Implements the same protocols using aiosqlite.
# Schema per v1 spec section 4.1.
# Returns the same dict shapes as the JSON backend.

class SqliteQuestRepo:
    def __init__(self, db: aiosqlite.Connection): ...

class SqlitePomoRepo:
    def __init__(self, db: aiosqlite.Connection): ...
    # Key: load_all() returns list[dict] with nested segments,
    # matching the JSON structure so core query functions work unchanged.

class SqliteTrophyPRRepo:
    def __init__(self, db: aiosqlite.Connection): ...
```

**Critical contract:** `SqlitePomoRepo.load_all()` must return sessions with nested
`segments` lists (joining `pomo_sessions` + `pomo_segments`), matching the JSON structure.
This allows `core/pomo_queries.py` and `core/trophy_compute.py` to work identically
against either backend.

### 4.4 Why Not an ORM

Same reasoning as v1: single-user, 3 entities, no relations complex enough to warrant
SQLAlchemy overhead. Raw `aiosqlite` with the Protocol pattern gives us type-safe
interfaces without the abstraction weight.

---

## 5. PomoEngine — Shared State Machine

### 5.1 What Gets Extracted from `main.py`

The following methods move from `QuestLogApp` into `core/pomo_engine.py`:

```python
class PomoEngine:
    """Pomo session state machine — shared between TUI and web.

    Manages the lifecycle: charge → work → deed → break_choice → charge.
    Emits events via callbacks. Does NOT own UI or timers.
    """

    def __init__(self, pomo_repo: PomoRepo, config: dict = POMO_CONFIG):
        # Session state
        self.session: dict | None = None
        self.seg_type: str = "work"
        self.seg_start: datetime | None = None
        self.seg_interruptions: int = 0
        self.lap: int = 0
        self.lap_history: dict = {}
        self.is_resume: bool = False
        self.charge: str = ""
        self.deed_lap: int = -1
        self.last_early: bool = False
        # War Room state
        self.streak: int = 0
        self.streak_peak: int = 0
        self.momentum: int = 0
        self.total_interruptions: int = 0
        self.session_focus_secs: float = 0.0

    # ── Lifecycle ──────────────────────────────────────────────────────
    def start_session(self, quest_id: str, quest_title: str,
                      prior_pomos: int = 0, lap_history: dict = None) -> dict:
        """Start a new pomo session. Returns the session dict."""

    def start_segment(self, seg_type: str) -> SegmentStarted:
        """Begin a work or break segment. Returns event with timing info."""

    def tick(self) -> float:
        """Returns remaining seconds. Caller owns the interval."""

    def end_segment(self, completed: bool, interruption_reason: str = "",
                    break_size: str | None = None,
                    early_completion: bool = False) -> SegmentEnded:
        """End current segment. Returns event indicating next gate."""

    def submit_charge(self, charge: str) -> None:
        """Record charge text. Caller should then call start_segment('work')."""

    def submit_deed(self, deed: str,
                    forge_type: str | None = None) -> DeedSubmitted:
        """Record deed + forge type. Returns event with notification info."""

    def choose_break(self, choice: str) -> BreakChosen:
        """Handle break choice. Returns event: start break, skip, or end."""

    def interrupt(self, reason: str) -> Interrupted:
        """Record interruption, advance lap. Returns event."""

    def complete_early(self) -> SegmentEnded:
        """Swiftblade — complete current work pomo early."""

    def stop_session(self) -> SessionStopped:
        """End the session. Returns summary."""

    # ── Query helpers ──────────────────────────────────────────────────
    def seg_duration(self) -> int:
        """Duration in seconds for current segment type."""

    def remaining(self) -> float:
        """Seconds remaining in current segment."""
```

### 5.2 Event Types (simple dataclasses)

```python
@dataclass
class SegmentStarted:
    seg_type: str
    duration: int
    lap: int
    started_at: str

@dataclass
class SegmentEnded:
    next_gate: str          # "deed" | "charge" | "break_choice" | "summary"
    completed: bool
    seg_type: str

@dataclass
class DeedSubmitted:
    forge_type: str | None
    actual_pomos: int
    streak: int
    notification: str       # Pre-formatted message

@dataclass
class BreakChosen:
    action: str             # "start_break" | "skip_to_charge" | "end_session"
    seg_type: str | None    # Set if action == "start_break"

@dataclass
class Interrupted:
    new_lap: int
    total_interruptions: int

@dataclass
class SessionStopped:
    quest_title: str
    actual_pomos: int
```

### 5.3 How TUI Uses PomoEngine

```python
# tui/main.py — QuestLogApp
class QuestLogApp(App):
    def on_mount(self):
        self._engine = PomoEngine(pomo_repo=JsonPomoRepo(POMOS_FILE))
        ...

    def _handle_charge_submit(self, charge: str):
        self._engine.submit_charge(charge)
        event = self._engine.start_segment("work")
        # Update UI: show timer with event.duration, event.lap
        self._pomo_timer_handle = self.set_interval(1.0, self._pomo_tick)

    def _pomo_tick(self):
        remaining = self._engine.remaining()
        if remaining <= 0:
            event = self._engine.end_segment(completed=True)
            # Route to next gate based on event.next_gate
        else:
            # Update timer display
```

### 5.4 How Web Uses PomoEngine

```python
# web/pomos/routes.py
@router.post("/pomos/charge")
async def charge(request: Request, charge: str = Form(...)):
    engine = get_pomo_engine()  # singleton, in-memory (single user)
    engine.submit_charge(charge)
    event = engine.start_segment("work")
    return templates.TemplateResponse("pomos/timer.html", {
        "request": request,
        "duration": event.duration,
        "lap": event.lap,
        "started_at": event.started_at,
        "session": engine.session,
    })
```

The web's SSE endpoint polls `engine.remaining()` and calls `engine.end_segment()` when
time expires — same logic, different timer mechanism.

---

## 6. Refactored `pomo_queries.py`

### Before (current)

```python
def get_today_receipt() -> list[dict]:
    today = today_local().isoformat()
    entries = []
    for s in load_pomos():       # ← hardcoded JSON load
        for seg in s["segments"]:
            ...
```

### After (core)

```python
def get_today_receipt(sessions: list[dict]) -> list[dict]:
    today = today_local().isoformat()
    entries = []
    for s in sessions:            # ← caller provides data
        for seg in s["segments"]:
            ...
```

**Every function in `pomo_queries.py` gets the same treatment:**

| Function | Current Signature | Refactored Signature |
|----------|------------------|---------------------|
| `get_today_receipt` | `() -> list[dict]` | `(sessions) -> list[dict]` |
| `get_quest_pomo_total` | `(quest_id) -> int` | `(sessions, quest_id) -> int` |
| `get_quest_lap_history` | `(quest_id) -> dict` | `(sessions, quest_id) -> dict` |
| `get_quest_segment_journey` | `(quest_id) -> list[dict]` | `(sessions, quest_id) -> list[dict]` |
| `get_today_timeline` | `() -> list[dict]` | `(sessions) -> list[dict]` |
| `get_all_pomo_counts_today` | `() -> dict` | `(sessions) -> dict` |
| `get_berserker_stats` | `() -> dict` | `(sessions) -> dict` |

TUI call sites change from:
```python
receipt = get_today_receipt()
```
to:
```python
receipt = get_today_receipt(self.pomo_repo.load_all())
```

One-line change per call site. Zero logic changes.

---

## 7. Refactored `trophy_compute.py`

### Before (current `trophy_store.py`)

```python
def compute_trophies() -> dict:
    sessions = load_pomos()     # ← hardcoded
    quests = load_quests()      # ← hardcoded
    prs = _load_prs()           # ← hardcoded JSON file
    ...
    if updated:
        _save_prs(prs)          # ← hardcoded JSON file
    ...
```

### After (core)

```python
def compute_trophies(sessions: list[dict], quests: list[dict],
                     prs: dict) -> tuple[dict, dict]:
    """Compute trophy states.

    Args:
        sessions: All pomo sessions (with nested segments)
        quests: All quests
        prs: Current personal records dict

    Returns:
        (result_dict, updated_prs) — caller persists updated_prs if changed
    """
    ...
    return {"trophies": trophies, "summary": summary, "best_day": best_day}, prs
```

Caller (TUI):
```python
sessions = pomo_repo.load_all()
quests = quest_repo.load_all()
prs = trophy_pr_repo.load_prs()
result, updated_prs = compute_trophies(sessions, quests, prs)
trophy_pr_repo.save_prs(updated_prs)
```

Caller (Web):
```python
sessions = await sqlite_pomo_repo.load_all()
quests = await sqlite_quest_repo.load_all()
prs = await sqlite_trophy_pr_repo.load_prs()
result, updated_prs = compute_trophies(sessions, quests, prs)
await sqlite_trophy_pr_repo.save_prs(updated_prs)
```

Same computation, different I/O. `TROPHY_DEFS` moves to `core/trophy_defs.py` since both
TUI and web need the definition list for display.

---

## 8. Database Schema

**Unchanged from v1 spec section 4.** The SQLite schema is identical. The only difference
is that `SqlitePomoRepo.load_all()` must join `pomo_sessions` + `pomo_segments` and
return nested dicts matching the JSON shape:

```python
async def load_all(self) -> list[dict]:
    """Load all sessions with nested segments.

    Returns list matching JSON structure:
    [
        {
            "id": "abc123",
            "quest_id": "def456",
            "quest_title": "Auth refactor",
            "segments": [ { "type": "work", "lap": 0, ... }, ... ],
            ...
        }
    ]
    """
    sessions = await self.db.execute_fetchall("SELECT * FROM pomo_sessions")
    for session in sessions:
        segments = await self.db.execute_fetchall(
            "SELECT * FROM pomo_segments WHERE session_id = ? ORDER BY id",
            (session["id"],)
        )
        session["segments"] = [dict(s) for s in segments]
    return sessions
```

### Performance Note

For the web app, heavy analytical queries (heatmap, berserker stats) could benefit from
SQL-level aggregation rather than loading all sessions into Python. This is an **optional
optimization**, not a requirement:

```python
# core/pomo_queries.py — default implementation (works for both backends)
def get_all_pomo_counts_today(sessions: list[dict]) -> dict: ...

# web/chronicle/queries.py — optional SQL-optimized override
async def get_all_pomo_counts_today_sql(db: Connection) -> dict:
    """SQL-optimized version for large datasets."""
    rows = await db.execute_fetchall("""
        SELECT ps.quest_id, COUNT(*) as cnt
        FROM pomo_segments seg
        JOIN pomo_sessions ps ON seg.session_id = ps.id
        WHERE seg.type = 'work' AND seg.completed = 1
          AND seg.forge_type IS NOT 'hollow'
          AND date(seg.started_at) = date('now')
        GROUP BY ps.quest_id
    """)
    return {r["quest_id"]: r["cnt"] for r in rows}
```

The shared Python implementation is the **canonical, always-correct version**. SQL
overrides are performance shortcuts that must return identical results.

---

## 9. Web Routing & Templates

**Unchanged from v1 spec sections 6, 10.** The routes, template structure, and HTML
component specs remain identical. The only difference is that route handlers call
`core` functions instead of reimplemented query modules:

```python
# web/chronicle/routes.py
from core.pomo_queries import get_today_timeline, get_all_pomo_counts_today
from core.storage.sqlite_backend import SqlitePomoRepo

@router.get("/chronicle")
async def chronicle(request: Request, db=Depends(get_db)):
    repo = SqlitePomoRepo(db)
    sessions = await repo.load_all()
    timeline = get_today_timeline(sessions)
    counts = get_all_pomo_counts_today(sessions)
    ...
```

```python
# web/trophies/routes.py
from core.trophy_compute import compute_trophies

@router.get("/trophies")
async def trophies(request: Request, db=Depends(get_db)):
    sessions = await pomo_repo.load_all()
    quests = await quest_repo.load_all()
    prs = await trophy_pr_repo.load_prs()
    result, updated_prs = compute_trophies(sessions, quests, prs)
    await trophy_pr_repo.save_prs(updated_prs)
    ...
```

```python
# web/dashboard/routes.py
from core.metrics import compute_metrics, compute_pomo_metrics

@router.get("/dashboard")
async def dashboard(request: Request, db=Depends(get_db)):
    quests = await quest_repo.load_all()
    sessions = await pomo_repo.load_all()
    quest_metrics = compute_metrics(quests)          # already accepts params!
    pomo_metrics = compute_pomo_metrics(sessions)    # already accepts params!
    ...
```

---

## 10. Timer Architecture

**Unchanged from v1 spec section 7.** The web timer is server-authoritative with SSE.
The `PomoEngine` lives in-memory (single user, single process). The SSE endpoint polls
`engine.remaining()` and pushes events.

```python
# web/pomos/sse.py
from core.pomo_engine import PomoEngine

async def tick_stream(engine: PomoEngine):
    while engine.session and engine.seg_start:
        remaining = engine.remaining()
        if remaining <= 0:
            event = engine.end_segment(completed=True)
            yield {"event": "segment-complete", "data": event.next_gate}
            return
        yield {"event": "tick", "data": json.dumps({"remaining": remaining})}
        await asyncio.sleep(1)
```

---

## 11. UI Design System, Animations, Typography

**Unchanged from v1 spec sections 8, 9, 11, 12.** These are purely frontend concerns.
The "Tavern Workbench" aesthetic, earthy palette, spring physics, celebration particles,
font stack — all identical.

---

## 12. Implementation Phases (Revised)

### Phase 0: Core Extraction (prerequisite — TUI keeps working)

**Goal:** Restructure into monorepo. TUI works identically after this phase.

- [ ] Create `core/` package directory
- [ ] Move `config.py` → `core/config.py`
- [ ] Move helpers from `utils.py` → `core/utils.py`
- [ ] Extract metrics from `utils.py` → `core/metrics.py`
- [ ] Refactor `pomo_queries.py` → `core/pomo_queries.py` (add sessions param)
- [ ] Extract `TROPHY_DEFS` → `core/trophy_defs.py`
- [ ] Refactor `compute_trophies()` → `core/trophy_compute.py` (add data params)
- [ ] Create `core/storage/protocols.py`
- [ ] Create `core/storage/json_backend.py` (wrap existing store code)
- [ ] Extract `PomoEngine` from `main.py` → `core/pomo_engine.py`
- [ ] Move TUI files into `tui/`, update all imports
- [ ] Verify TUI runs identically: `python -m tui.main`
- [ ] Write unit tests for `core/` functions (they're now testable in isolation!)

**Deliverable:** Same app, cleaner architecture. All core logic is tested independently.

**Estimated diff:** ~200 lines moved, ~50 lines of new Protocol/backend glue, ~30 import
changes across TUI files. Zero logic changes.

### Phase 1: Web Foundation

**Goal:** Deployable app with quest board working.

Same as v1 Phase 1, but:
- `web/app.py` imports from `core.config`
- `web/quests/routes.py` uses `core.storage.sqlite_backend.SqliteQuestRepo`
- No need to rewrite quest CRUD logic — Protocol methods match existing signatures
- Create `core/storage/sqlite_backend.py`
- Create `web/db.py` (connection pool, migrate)
- `migrations/001_initial.sql` (unchanged from v1)
- All frontend assets (CSS, JS, fonts, templates) per v1 spec

**Deliverable:** Quest board in browser, backed by shared config and storage protocol.

### Phase 2: Pomodoro Engine (Web)

**Goal:** Full charge/deed/timer loop working in browser.

Same as v1 Phase 2, but:
- `web/pomos/routes.py` delegates to `core.pomo_engine.PomoEngine`
- SSE endpoint uses `engine.remaining()` and `engine.end_segment()`
- No reimplementation of state machine logic
- Templates are new (Jinja2), but the data they receive comes from shared engine

**Deliverable:** Complete pomo loop in browser — identical behavior to TUI.

### Phase 3: Chronicle & Trophies

**Goal:** Full feature parity with TUI.

Same as v1 Phase 3, but:
- Chronicle routes call `core.pomo_queries` functions
- Trophy routes call `core.trophy_compute.compute_trophies()`
- Dashboard routes call `core.metrics.compute_metrics()` / `compute_pomo_metrics()`
- No query logic rewrite — just wire routes to core functions

**Deliverable:** All panels working. Full TUI feature parity.

### Phase 4: Polish & Migration

**Identical to v1 Phase 4.** Migration script, celebrations, responsive, Docker.

### Phase 5: Extensions

**Identical to v1 Phase 5.** Recurring tasks, habits, experiments, etc.

---

## 13. Migration Path

### 13.1 JSON → SQLite Migration Script

**Unchanged from v1 spec section 13.** `scripts/migrate_json.py` reads the three JSON
files and inserts into SQLite.

### 13.2 Dual-Backend Coexistence

After Phase 0, the TUI continues using the JSON backend. The web app uses SQLite. Users
can choose:

- **TUI only:** JSON backend (no migration needed, status quo)
- **Web only:** SQLite backend (run migration once)
- **Both:** JSON for TUI, SQLite for web (run migration, then both are independent)
- **Future:** TUI could optionally switch to SQLite backend too (one config change)

The storage protocol makes this a configuration choice, not an architectural decision.

---

## 14. Lines of Code Impact

| What | v1 Approach | v2 Approach | Savings |
|------|------------|------------|---------|
| Trophy computation | Rewrite ~300 lines | Move, add 2 params | ~280 lines saved |
| Pomo queries | Rewrite ~157 lines | Move, add 1 param each | ~140 lines saved |
| Metrics | Rewrite ~120 lines | Move (already parameterized!) | ~120 lines saved |
| Pomo state machine | Rewrite ~250 lines | Extract to shared class | ~230 lines saved |
| Config | Duplicate ~29 lines | Shared import | ~29 lines saved |
| Utils | Rewrite ~110 lines | Move | ~100 lines saved |
| **Total** | **~966 lines rewritten** | **~70 lines of Protocol glue** | **~900 lines** |

Beyond line savings, the critical benefit is **single source of truth** — when trophy
tiers change or a new forge type is added, it's one change in `core/`, not two divergent
patches.

---

## 15. Risks & Mitigations (Revised)

All v1 risks remain valid. Additional risks from the refactor:

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Phase 0 breaks TUI** | Medium | Phase 0 is purely structural (move + rename). Run TUI integration test after every file move. Git commit per logical move. |
| **Async/sync mismatch** | Low | Core functions are sync (pure computation). SQLite backend uses `aiosqlite` (async). Web routes `await` the repo, then pass sync data to core functions. No conflict. |
| **Dict shape divergence between backends** | Medium | Unit test: both backends must return identical dict shapes for the same seed data. The SQLite `load_all()` join must produce the nested-segment structure. |
| **PomoEngine in-memory state + server restart** | Low | Same as v1 — session recoverable from DB. Add `PomoEngine.recover(session_id)` method that reconstructs state from the last stored segment. |

---

## 16. Appendix: Files Unchanged from v1

The following v1 spec sections apply verbatim to v2 and should be read alongside this
document:

- **Section 2** — Requirements (F1-F19, NF1-NF9)
- **Section 4.1** — Database Schema (all CREATE TABLE statements)
- **Section 4.2** — Quest State Machine
- **Section 4.3** — Segment Types
- **Section 6** — Route Map & API (all endpoints)
- **Section 7** — Timer Architecture (SSE, server-authoritative)
- **Section 8** — UI Design System (palette, tokens, icons)
- **Section 9** — Layout & Responsive (desktop/tablet/mobile)
- **Section 10** — Component Specs (quest card, gates, timer, heatmap, trophy card)
- **Section 11** — Animation & Motion (celebration particles, HTMX integration)
- **Section 12** — Typography (font stack, type scale)
- **Section 14** — Extensibility (module pattern, future modules)
- **Section 17** — Dependencies (Python packages, frontend static files, Docker)

---

*This document revises the internal architecture of QuestLog Web. The user-facing product
is identical to v1. The difference is engineering: shared code, single source of truth,
and a monorepo that scales to future frontends without duplicating business logic.*
