# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# First-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install textual rich

# Run
python3 main.py

# Reset all data (creates backups first)
./clear_data.sh
```

Requires Python 3.10+.

## Architecture

QuestLog is a **Textual TUI app** with three persistent JSON files as its data store. There is no database.

### Data Layer

| File | Store module | Purpose |
|------|-------------|---------|
| `quests.json` | `quest_store.py` | Quest records (id, title, status, timestamps, frog flag) |
| `pomodoros.json` | `pomo_store.py` | Pomodoro sessions and their work/break segments |
| `trophies.json` | `trophy_store.py` | Personal records / achievements |

Each store module exposes plain functions (load, save, add, update) that read/write JSON directly. No ORM, no caching.

`pomo_queries.py` contains read-only analytical queries over `pomodoros.json` (today's receipt, counts, lap history). Keep all new pomodoro analytics here rather than in the store.

`utils.py` holds shared helpers: `USER_TZ` (change here to switch timezone), `format_duration`, `fantasy_date`, `compute_metrics`, `compute_pomo_metrics`, `today_local`, and `to_local_date`.

### UI Layer

`main.py` (`QuestLogApp`) owns all application state, bindings, and action handlers. The three panels — `RosterPanel`, `ChroniclePanel`, `TrophyPanel` — are composed as `Horizontal` children.

- `quest_panel.py` (`RosterPanel`) — four `StatusPane` widgets (log/active/blocked/done) in a lazygit-style vertical layout.
- `chronicle_panel.py` (`ChroniclePanel`) — scrollable pomo history with a green heatmap and per-day breakdowns.
- `trophy_panel.py` (`TrophyPanel`) — Hall of Valor showing personal records and achievements.

The **Pomodoro flow** is a multi-mode overlay screen (`PomodoroPanel`) pushed onto the screen stack. Its modes cycle: `charge → timer → deed → break_choice → charge`. App-level state (`_pomo_*` fields) drives the flow; `PomodoroPanel` is purely display/input. Pressing `Esc` on the pomo screen is intentionally disabled — the timer keeps running while the panel is hidden via `x` (Abandon).

`modals.py` contains push-screen dialogs: `AddQuestModal`, `ConfirmModal`, `DashboardModal`, `DailyReceiptModal`.

`renderers.py` holds Rich markup strings and RPG-flavored display helpers.

`styles.tcss` is the Textual CSS file for layout and theming.

### Quest Status Machine

```
log → active → done
log → blocked → active → done
any status → delete
```

Valid transitions are enforced by `VALID_SOURCES` dict in `main.py`. Key bindings: `s`=start, `b`=block, `u`=unblock (same binding as `b`, re-activates blocked quests), `d`=done, `x`=delete, `f`=toggle frog flag.

### Pomodoro Segment Types

Stored as `"work"` / `"short_break"` / `"long_break"` in JSON. `"extended_break"` is a UI-only concept stored as `short_break` + `break_size: "extended"`. Timer durations live in `POMO_CONFIG` in `pomo_store.py`.

During the deed gate, the user can optionally tag the pomo with a **forge type** before submitting: `h`=Hollow (completed but subpar), `b`=Berserker (intense/over-extended). These are stored on the segment for analytics.

### Timezone

All timestamps are stored as UTC ISO strings. Display conversion uses `USER_TZ` in `utils.py` (default: `Asia/Kolkata`). Change `USER_TZ` there to switch.

### Feature Specs

`features/` contains product specs and PRDs (e.g. `PRD.md`, `SPEC-war-room-pomo.md`). Consult these before implementing new pomodoro or gamification features — they document intentional design decisions around the charge/deed loop and War Room UX.
