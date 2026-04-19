# Hard 90 Challenge — Design Doc

Serious-toned behavioral tracking sitelet inside Life OS. Parallel to Quest Tracker. Do-or-die philosophy: system evaluates user under pressure, no motivational fluff.

Route root: `/challenge`.

## Core Premise

- 90 consecutive days. One era per run.
- User defines static task set at setup. Tasks immutable after (typo edits only).
- Each day, user rates every tracked task on a 5-state scale.
- Rolling-window streak logic can reset the era to day 0.
- 26 named levels (13 weekly main + 13 mid-week) track progress.
- Era ends → archived to history with prose narrative → new era auto-starts with same tasks.

## Data Model

### Buckets
| Bucket | Role | Reset tracked? |
|---|---|---|
| `anchor` | Non-negotiable. Daily. Core to survival. | Yes |
| `improver` | Growth. Discipline. Elevation. | Yes |
| `enricher` | Optional. Engagement without penalty. | No (metric-only) |

### States (5-tier)
Order = worst → best. `STATE_RANK` gives monotonic int for drift detection.

| State | Icon | Label |
|---|---|---|
| `NOT_DONE` | ✗ | Not Done |
| `STARTED` | ⋯ | Started |
| `PARTIAL` | – | Partial |
| `COMPLETED_UNSATISFACTORY` | ✓− | Completed (unsatisfactory) |
| `COMPLETED_SATISFACTORY` | ✓ | Completed |

`PARTIAL` breaks soft streak. `STARTED` does not.

### Tables
- `challenges` — era-scoped. `midweek_adjective` persisted per-era (stable display across week within era). `peak_level` tracked for archive summary.
- `challenge_tasks` — static after setup. UNIQUE(challenge_id, name).
- `challenge_entries` — UNIQUE(task_id, log_date). One rating per task per day. `notes` free-text.
- `challenge_eras` — archived runs. `reset_cause ∈ {hard, soft, forfeit, completed}`. `summary_prose` stored at archive time.

## Reset Logic (per-task rolling window)

Applied to anchors + improvers only. Enrichers NEVER trigger reset.

- **Hard fail**: last 3 entries all `NOT_DONE` → reset.
- **Soft fail**: last 7 entries all ∈ `{NOT_DONE, STARTED}` → reset.
- Evaluated per-task, not globally. Any single task tripping window = reset.
- Backfill retroactively triggers reset (scan all contiguous windows).
- Reset → current era archived (with prose cause), new era created with same task structure, level→0, days→0, new era name picked.

## Levels (26 tiers)

13 main + 13 mid-week. Main tier names stable across eras (cross-era comparison). Mid-week tier names = random adjective (chosen per-era) + next main name.

- `week_num = days_elapsed // 7`, capped at 13.
- Day 0–2 of week → main tier for that week.
- Day 3–6 of week → mid-week tier (adjective + next main name).
- Main promotion: full-screen cinematic (ember burst + sigil + typed level name).
- Mid-week promotion: corner toast, auto-dismiss 3.5s.
- Day 90 → completion cinematic (ash rain).

Main names: `Initiate → Acolyte → Wanderer → Sentinel → Guardian → Vanguard → Champion → Warlord → Ascendant → Sovereign → Ironclad → Forgeborn → Legendborn → Godbound`.

Mid-week adjective pool: `Unshakeable, Relentless, Resolute, Steadfast, Unwavering, Unbending, Unyielding, Fierce, Dauntless, Indomitable, Valiant, Stalwart, Intrepid, Fearless, Audacious` — one chosen per era at setup.

## Eras

- 30-name pool. No dupes per user until all 30 used, then reuse random.
- Era name set at creation; not editable.
- Picker queries `challenge_eras` for used names rather than in-memory set.
- Archive prose generated at reset/complete/forfeit time via `metrics_engine.era_prose()`.

## UX Decisions

### Setup Wizard (`/challenge/setup`)
- Three stacked sections: Anchors, Improvers, Enrichers.
- Alpine `x-data` dynamic add/remove task rows.
- At least one anchor required; setup rejects empty.
- Starts same day (no countdown — decided for simplicity over Kolkata 00:00 gate).
- Warning: "Once sealed, tasks cannot be changed except for typos."

### Today (`/challenge/today`) — primary view
- Header: Level badge (red accent), Day N/90 counter, era name, progress bar.
- Task cards grouped by bucket. Icon-based 5-state radio picker with hover glow.
- Notes textarea per task, collapsed.
- HTMX inline entry: state change POSTs to `/today/entry/{task_id}`, server returns updated card.
- Seal bar: counter of tracked-rated, "Seal Day N" button (disabled until all tracked tasks rated).
- Seal submits → server checks reset → returns cinematic OR reloaded today page with seal toast.
- Forfeit ("Relinquish") two-step confirm: darker name than "Forfeit" per user's request.
- Unrated anchors/improvers from yesterday block today (amber warn banner). Enrichers skippable.

### Metrics (`/challenge/metrics`) — magazine layout
Editorial, not dashboard. Asymmetric grid, prose woven in, italic callouts. Deliberately NOT a cards-stack.

- Hero: eyebrow kicker + oversized title "Day N of 90" + deck paragraph.
- Grid A (1fr 1.4fr): circular conic-gradient survival gauge + italic quote (tone escalates by survival %) | per-task pressure bars (Hard X/3, Soft X/7).
- Divider: `━━ Pattern Analysis ━━`.
- Grid B (1fr 1.3fr 1fr): bucket posture state counts | drift/warning callout list with red left-border | enricher engagement big-number stat.
- Narrative block: full-width italic prose, tone shifts on survival index (holding / cracks / edge).

### History (`/challenge/history`)
- Vertical scrollable timeline, newest first.
- Active era card at top (red border).
- Each archived era: name + cause chip (color-coded) + meta line (dates, duration, peak) + prose.
- Era breaks between cards: gradient red line + "— Era Ended: [name] —".

### Cinematics
Server returns full HTML page with effect. HTMX not used for these (full swap).

- **Reset**: red radial flash + fade-up core. "The era ends. [name] falls." Stats + new era reveal + "Witness the New Age" button.
- **Complete**: ash particle rain (JS generator). "The 90 stands. You did not break." → Archive button.
- **Promote (main)**: ember burst (radial particle explode) + slow-rotating sigil SVG + typed-out level name (CSS step typewriter).
- **Midweek**: fixed bottom-right toast, 340px, auto-dismiss 3.5s via `setTimeout → location.href`.
- **Forfeit**: "Relinquished" eyebrow, old era past-tense title, peak stats, "Begin Again" button.

## Visual Identity

Scoped under `.challenge-page` class — all CSS nested, prevents QuestLog leakage.

- Palette: `--ch-bg #0a0a0b`, `--ch-surface #131316`, `--ch-red #ef4444`, `--ch-red-hi #dc2626`, `--ch-red-deep #991b1b`, `--ch-red-glow rgba(239,68,68,0.25)`. Amber/green only for warn/success accents.
- Fonts: Inter sans + JetBrains Mono (mono used for numeric/eyebrow text for Linear.app feel).
- Linear.app-inspired: collapsible left sidebar (Life OS app nav), compact top strip, 6-column max content, tight 14px base.
- Mono numerics throughout: day counter, level labels, hbar labels, stat readouts.
- Red left-border = action/highlight. Dotted underlines for subtle dividers.

### Sidebar
Challenge-specific (Life OS app switcher). Alpine `sidebarOpen` state. Collapses to 54px icon rail. Mobile: position absolute + hamburger toggle. Links: Quest Tracker (`/`), Hard 90 (`/challenge`).

## Key Architectural Conventions

- **Template filenames prefixed `challenge_`** — Jinja FileSystemLoader searches flat across all registered dirs; prefix avoids collision (`base.html`, `setup.html` exist elsewhere).
- **Templates reference bare filename**: `_render(request, "challenge_today.html", ctx)`.
- **`_render` helper imports `templates` locally** inside function body — breaks circular import with `web.app`.
- **Repos live in `core/storage/`, engines in `core/challenge/`** — engines are framework-free pure fns, fully unit-testable.
- **All challenge CSS scoped under `.challenge-page`** — no leakage into QuestLog glassmorphic theme.
- **Day counter semantics**: `start_date = day 1` (inclusive). `_days_elapsed = (today - start).days + 1`.
- **Midweek adjective stored at era creation**, not recomputed. Ensures display stability through era even if config changes.
- **Era archive creates new challenge** with copied task set (new IDs). Old entries remain linked to old challenge_id.

## Out of Scope (v1)

- SSE live cinematics — HTMX full-page swap instead.
- Editing past days — locked per spec.
- Mid-run task changes (beyond typo).
- Weekday/weekend task split — explicitly scrapped.
- Custom era name input — pool-only.
- Authentication — single-user Life OS.
- Promotion sound effects.
- Level badge SVG assets — placeholder sigil for now.

## File Map

```
core/challenge/
  config.py           constants, levels, eras, adjectives
  reset_engine.py     check_hard, check_soft, check_reset, evaluate_backfill (pure)
  level_engine.py     compute_level, should_promote_main/midweek, is_complete (pure)
  metrics_engine.py   survival_index, per_task_health, bucket_posture, detect_drift, era_prose
  era_names.py        pick_era_name (async, queries repo), pick_midweek_adjective

core/storage/
  challenge_backend.py  SqliteChallengeRepo, SqliteChallengeTaskRepo, SqliteChallengeEntryRepo, SqliteChallengeEraRepo
  protocols.py          +4 Protocol classes

web/challenge/
  routes.py           index, setup (GET/POST), today, update_entry, seal_day, forfeit, metrics, history
  templates/          challenge_base, challenge_setup, challenge_today, challenge_task_card,
                      challenge_metrics, challenge_history,
                      challenge_cinematic_{reset,complete,promote,midweek,forfeit}

web/static/
  challenge.css       scoped under .challenge-page
  challenge.js        chEmberBurst, chAshRain (particle generators)

migrations/
  004_challenge.sql   4 tables + indexes
```

## Gotchas / Future Traps

- **Notes textarea blur** triggers HTMX POST that requires `state` field. If user types notes before selecting state → 422. Currently acceptable (user picks state first), but consider client-guard if it bites.
- **Reset during same day** → new challenge created, but today_str entries already written to old (reset) challenge. New challenge starts with empty entries. Intentional: the failed day belongs to the failed era.
- **Backfill reset** not yet wired into `seal_day` route — engine fn exists (`evaluate_backfill`) but route uses forward-only `check_hard`/`check_soft`. Add if backfill UI lands.
- **Days-elapsed** recomputed from `start_date` diff on every seal — not incremented. Means multiple seals same day are idempotent for day counter. Safe.
- **Peak level** updated via `UPDATE ... MAX(peak_level, ?)` to prevent regression on reset day.
- **Enrichers in `challenge_entries`** also get UNIQUE(task_id, log_date). They can be rated but never gate sealing.
