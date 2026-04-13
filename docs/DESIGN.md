# QuestLog — Design Document

> Captures visual identity, code style, UI feel, and architectural philosophy.
> Reference this before adding UI, styling, or language to either frontend.

---

## 1. Identity & Philosophy

QuestLog is a **productivity companion with an RPG soul**. Every interaction — from naming a task to completing a timer — is wrapped in the language of an adventurer's journal. The goal is to make doing hard work feel like an act of consequence.

**Core tensions held deliberately:**
- Serious enough to be a real work tool. Playful enough to make work feel like a quest.
- Data-rich analytics. UI that never overwhelms.
- Two completely distinct visual identities (TUI vs Web) — same metaphors, different worlds.

---

## 2. RPG Language & Naming

All user-facing language uses the RPG lexicon. This is not decoration — it's the product identity.

| Plain Term | QuestLog Term |
|---|---|
| Task / To-do | Quest |
| Intent before work | Charge |
| Outcome after work | Deed |
| Complete a pomodoro | Forge |
| Barely worked pomo | Hollow (`💀`) |
| Deep flow pomo | Berserker (`⚡`) |
| Dreaded task | Frog (`🐸`) |
| Complete dreaded task | Eat the frog |
| Early pomo completion | Swiftblade |
| Break | Respite |
| Active work session | The Fray |
| Stop session | Abandon |
| Trophy display | Hall of Valor |
| Stats panel | Adventure's Chronicle |
| You | Warrior / Adventurer |

**Rule:** New UI copy must use these terms. Never mix plain and RPG language in the same surface.

---

## 3. TUI Visual Identity — "Starforge"

The TUI lives in darkness. It's the terminal war room: focused, urgent, neon-lit.

### Color Palette

| Role | Hex | Usage |
|---|---|---|
| Background | `#0e0e1a` | Screen, panel bg |
| Surface | `#1a1a2e` | Modals, footer, stats bar |
| Primary accent | `#bf40ff` | Active borders, titles, CTAs |
| Text primary | `#e0e0ff` | All body text |
| Muted border | `#333355` | Inactive panel borders |
| Border title | `#8888cc` | Inactive panel labels |

### Layout

Three-column layout: **Roster (1fr) | Chronicle (1.5fr) | Hall of Valor (1.5fr)**

- Panels use `round` borders (Textual CSS)
- Active panel: `#bf40ff` border + title
- Inactive: `#333355` border, `#8888cc` title
- Header docked top (height: 2), footer docked bottom
- Stats bar docked bottom above footer

### Pomo Panel (War Room)

Overlays the full screen. Centered content. Distinct zones:
- **Charge gate** — purple header, input centered
- **Work timer** — block clock display (monospace segments), health bar, momentum bar
- **Deed gate** — victory flash, forge type selector
- **Break choice** — minimal options display

### Style Rules (TUI)

- Use Rich markup for color/bold: `[bold #bf40ff]text[/]`
- `border: round` everywhere — no square borders
- All interactive zones: centered text + content-align
- Avoid dense walls of text — use spacing and blank lines

---

## 4. Web Visual Identity — "The Modern Chronicle"

The web UI is daylight to the TUI's darkness. It's a **warm parchment journal** — the ledger where an adventurer records their deeds.

### Color System (Design Tokens)

Defined in `web/static/tokens.css`. All values via CSS custom properties.

#### Surfaces (Mocha Parchment)
| Token | Value | Role |
|---|---|---|
| `--surface` | `#F3EDE3` | Base layer — warm oat parchment |
| `--surface-container-low` | `#E8DED0` | Section containers |
| `--surface-container-lowest` | `#FBF8F3` | Elevated cards, inputs |
| `--surface-container-high` | `#DFD2C1` | Nested detail groups |
| `--surface-dim` | `#D6C9B8` | Empty/disabled |

#### On-Surface (Ink)
| Token | Value | Role |
|---|---|---|
| `--on-surface` | `#1c1c18` | Primary text — never pure black |
| `--on-surface-variant` | `#44483e` | Secondary text |
| `--on-surface-muted` | `#74796c` | Timestamps, metadata |
| `--outline-variant` | `#c2c8c0` | Ghost borders |

#### Semantic Colors
| Token | Value | Role |
|---|---|---|
| `--primary` | `#163422` | CTAs, primary action bg (deep forest green) |
| `--primary-container` | `#2d4b37` | Hover state, gradient end |
| `--secondary` | `#95482b` | Accent, high-priority (terracotta) |
| `--secondary-container` | `#fc9a77` | Warm chip/tag bg |
| `--tertiary` | `#7a9e7e` | Done, active, break states (sage) |
| `--error` | `#b5493a` | Blocked, destructive (ember red) |
| `--hearth` | `#d4943a` | Trophy, completion (gold/amber) |
| `--hearth-glow` | `#f5d78e` | Celebration pulse |

### Typography

Three typefaces. Each has a role. Do not swap them.

| Font | Role | Token |
|---|---|---|
| **Newsreader** (serif) | Headers, ritual moments (charge gate, deed gate titles) | `--font-display` |
| **Manrope** (sans) | Body, labels, all UI copy | `--font-body` |
| **JetBrains Mono NF** | Timers, counts, data values | `--font-mono` |

**Type scale:** `--text-xs` (11px) through `--text-4xl` (56px). Body default: `--text-base` (14px).

**Rules:**
- Newsreader weights: 400–700 only. No italic. No 800+.
- Manrope minimum weight: 500 (Medium). No thin/regular 400.
- JetBrains Mono weight 600 for timers.

### Spacing & Radii

```
--space-xs: 0.25rem    --radius-sm:   0.125rem  (heatmap cells)
--space-sm: 0.5rem     --radius-md:   0.375rem  (buttons)
--space-md: 1rem       --radius-lg:   0.5rem    (inputs)
--space-lg: 1.5rem     --radius-xl:   0.75rem   (cards)
--space-xl: 2rem       --radius-full: 9999px    (pills, chips)
```

### Shadows (Warm Tinted Ambient)

```
--shadow-ambient    — base cards
--shadow-lifted     — interactive elements
--shadow-floating   — dropdowns, tooltips
--shadow-overlay    — modals
--shadow-input-focus — focused inputs (green glow ring)
```

Never use plain `box-shadow: 0 2px 4px rgba(0,0,0,0.5)` — always use tokens.

### Motion & Easing

```
--ease-natural:     cubic-bezier(0.4, 0, 0.2, 1)   — default transitions
--ease-decelerate:  cubic-bezier(0, 0, 0.2, 1)      — entering elements
--ease-accelerate:  cubic-bezier(0.4, 0, 1, 1)      — exiting elements
--ease-spring:      cubic-bezier(0.5, 1.25, 0.75, 1.25) — playful interactions
```

### Glassmorphism

```
--glass-bg:     rgba(255, 255, 255, 0.65)
--glass-blur:   20px
--glass-border: rgba(120, 100, 80, 0.12)
```

Use sparingly — overlapping modals, tooltip panels.

---

## 5. Architecture

### Dual Frontend, Shared Core

```
core/               ← ALL business logic lives here
  config.py         ← tuneables: timezone, pomo durations, state machine
  storage/
    protocols.py    ← QuestRepo / PomoRepo / TrophyPRRepo Protocol interfaces
    json_backend.py ← sync JSON file storage (TUI)
    sqlite_backend.py ← async aiosqlite storage (Web)
  pomo_engine.py    ← timer state machine
  pomo_queries.py   ← read-only analytics
  metrics.py        ← quest/pomo metric computations
  trophy_defs.py    ← trophy definitions
  trophy_compute.py ← trophy evaluation logic
  utils.py          ← format_duration, fantasy_date, date helpers

tui/                ← Textual TUI app
web/                ← FastAPI + HTMX + Alpine.js
```

**Rule:** Zero business logic in `tui/` or `web/`. Both are pure presentation layers. Analytics and computations belong in `core/`.

### Storage Pattern

Both frontends implement the same `Protocol` interfaces (`core/storage/protocols.py`). Adding a new storage backend = implement the Protocol, wire into deps. No other changes needed.

### Web Stack Detail

- **FastAPI** — routing, lifespan, DI
- **Jinja2** — server-rendered templates, discovered from all module `templates/` dirs via `FileSystemLoader`
- **HTMX** — partial page updates (quest status changes, pomo flow)
- **Alpine.js** — client-side state (timer display, toggle state)
- **SSE** — live pomo timer updates via `web/pomos/sse.py`
- **aiosqlite** — async SQLite with WAL mode

### Module Structure (Web)

Each feature is a self-contained module:
```
web/quests/    routes.py + templates/
web/pomos/     routes.py + templates/ + sse.py
web/chronicle/ routes.py + templates/
web/trophies/  routes.py + templates/
web/dashboard/ routes.py + templates/
```

### Pomodoro State Machine

```
charge → timer → deed → break_choice → charge (next lap)
```

Stored types: `work` / `short_break` / `long_break`
`extended_break` is UI-only → stored as `short_break` + `break_size: "extended"`

Forge types: `hollow` (💀) and `berserker` (⚡). Hollow segments do not increment `actual_pomos`.

### Quest State Machine

```
log → active → done
log → blocked → active → done
any → delete
```

Valid transitions defined in `core/config.py` as `VALID_SOURCES`.

---

## 6. Code Style

### Python

- Python 3.10+ — use `match`, `|` union types, `from __future__ import annotations`
- No type: ignore suppression without comment
- Repository classes take `Path` or `aiosqlite.Connection` — no globals inside repo classes
- All timestamps: UTC ISO strings on storage. Convert to `USER_TZ` on display only.
- `core/config.py` for all tuneables — no magic numbers in feature code

### Templates (Jinja2 + HTMX)

- HTMX attributes: `hx-get`, `hx-post`, `hx-swap`, `hx-target`
- Alpine.js for client-only state: `x-data`, `x-show`, `x-bind`
- Use `x-teleport` for portal patterns (tooltips, overlays out of DOM flow)
- Partial templates returned for HTMX swaps — never full page on HTMX requests

### CSS

- CSS custom properties only — no hardcoded color hex in `style.css`
- Tokens defined in `tokens.css`, applied in `style.css`
- Class naming: BEM-adjacent, hyphenated, feature-prefixed (`.quest-card`, `.pomo-timer`)

---

## 7. Data & Timezone

- All storage: UTC ISO 8601 strings
- Display conversion: `USER_TZ = ZoneInfo("Asia/Kolkata")` in `core/config.py`
- Change timezone: edit `USER_TZ` only — never convert timestamps before storage

---

## 8. Do Not

- Add business logic to `tui/` or `web/` — belongs in `core/`
- Use plain hex colors in web CSS — use `tokens.css` vars
- Mix RPG and plain language in user-facing copy
- Add Newsreader at weight 800+ or italic
- Add Manrope at weight 400 (Regular) — minimum 500
- Use `box-shadow` without design tokens in web
- Hardcode `questlog.db` path in new code — always via `QUESTLOG_DB` env var
- Store converted (local) timestamps — UTC only
