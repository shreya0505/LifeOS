# PRD: Intentional Pomodoro — Charge, Deed & Daily Receipt
**Author:** Senior Product Engineer  
**Status:** Ready for Implementation  
**Version:** 1.1

---

## 1. Problem Statement

A pomodoro timer solves *when* to focus. It does not solve *what* you focused on or *whether you did it*. Without that loop, sessions accumulate as raw counts — `🍅 × 12` — with no visibility into output. At the end of a day, a week, the work is invisible. You feel busy. You cannot prove it.

There are two naturally occurring pause points in **every** pomo cycle:

1. **Before the work segment starts** — scope is still open, the mind is primed  
2. **Right after the timer fires, before the break** — recall is freshest, the deed is fresh

We own both moments, **for every pomo in the run**. Everything else is unchanged.

---

## 2. Goals

- **G1.** Give every pomodoro a declared **Charge** (what you will do) before it starts.
- **G2.** Give every pomodoro a **Deed** (what actually happened) immediately after.
- **G3.** Surface a live, persistent daily log of Charge vs. Deed — always visible, regardless of screen.
- **G4.** Produce a human-readable daily receipt that is the LLM prompt payload in v0.2.
- **G5.** Make the pomodoro panel an immersive, feature-rich screen — not a modal overlay.

## 3. Non-Goals (v0.1)

- ❌ LLM summarisation or daily report generation
- ❌ Subtask checklists or task decomposition trees  
- ❌ Export, sync, or sharing of receipts  
- ❌ Editing past entries  
- ❌ Per-quest or cross-session subtask tracking  

---

## 4. User Stories

> **As a developer in deep-work mode**, I want to name one concrete target before each focus block so I have a micro-contract with myself — a Charge — that keeps scope tight and prevents Parkinson's Law from silently consuming the session.

> **As a developer coming out of focus**, I want a structured moment to chronicle my deed before I decompress into a break, so the effort is named while it's fresh — not reconstructed from memory an hour later.

> **As a developer reviewing my day**, I want a persistent log that shows what I charged toward vs. what I actually forged for each block, so I can see the gap between intention and execution and calibrate future runs.

---

## 5. Interaction Design

### 5.1 Session Start — Pomo Count Only

**Trigger:** User selects a quest and presses `[p]` to begin a pomodoro run.

**Behaviour:**
- `PomodoroStartModal` is shown with a single question:

  > **"How many 🍅 for this quest?"**

- A numeric `Input` (default: 1, min: 1, max: 8) is auto-focused.
- `[Ride Out]` button starts the session and immediately transitions to the **Charge Gate** (5.2).
- No intent/charge is collected here. That happens before *each* individual pomo.

---

### 5.2 Charge Gate — Pre-Pomo (Hard Constraint, runs before EVERY pomo)

**Trigger:** A work segment is about to begin — whether it is the first pomo or the fifth.

**Behaviour:**
- The pomo panel's **charge screen** is shown full-width with the prompt:

  > **"What will you have forged when this 🍅 ends?"**  
  > *(name the one thing — a fix, a decision, a draft)*

- A required `Input` field is auto-focused.
- The timer does **not** start until the field is submitted non-empty.
- There is no skip. An empty submission does nothing.
- On submit: charge text is stored against this lap's work segment, timer starts immediately.

**Rationale for hard gate:** A skippable prompt becomes invisible within 2 days. The friction *is* the feature. If you cannot name what you are forging, the pomo should not start.

---

### 5.3 Deed Gate — Post-Pomo (Hard Constraint, runs after EVERY pomo)

**Trigger:** Work segment timer reaches zero.

**Behaviour:**
- Bell fires. Timer stops.
- The pomo panel's **deed screen** replaces the timer with the retro prompt:

  > **"What did you claim?"**  
  > *(a bug slain, a path cleared, a truth discovered)*

- A required `Input` field is auto-focused.
- Break choice buttons (`[enter] Take your rest` / `[s] Press on`) are **hidden** until the deed is submitted.
- On submit: deed text is saved, break buttons appear, break starts.
- If the user presses `[x]` to stop the session before submitting the deed: the pomo is saved but **marked `deed_skipped: true`** and excluded from the daily receipt.

**Wording rationale:**  
- "What did you claim?" is outcome-oriented, not activity-oriented. It pushes the user away from "I worked on X" toward "X is now mine — done / decided / unblocked."
- The parenthetical examples lower blank-page anxiety without narrowing the answer.
- After a deed is submitted, if more pomos remain in the session, the **next Charge Gate** (5.2) fires immediately after the break ends.

---

### 5.4 Full Pomo Cycle — Screen Flow

Each pomo in a multi-pomo run goes through the same four screens in order. For a 3-pomo run the sequence is:

```
[Start Modal]
    ↓  (set count = 3, press Ride Out)
[Charge Gate]  ← pomo 1
    ↓  (name your charge, press ⏎)
[Focus Screen] ← 25 min timer runs
    ↓  (bell fires)
[Deed Gate]    ← fill in what you claimed
    ↓  (press ⏎ → take rest  or  [s] → press on)
[Break Screen] ← 5 min  (or skipped)
    ↓
[Charge Gate]  ← pomo 2
    ↓
[Focus Screen]
    ↓
[Deed Gate]
    ↓
[Break Screen]
    ↓
[Charge Gate]  ← pomo 3
    ↓
[Focus Screen]
    ↓
[Deed Gate]
    ↓  (no more pomos — session ends)
[Session Complete]
```

---

### 5.5 Pomo Panel — Immersive Layout

The panel is promoted from a `ModalScreen` overlay to a full `Screen`. It uses a **two-column layout**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  🍅  Auth Refactor                          🍅 2/3  ⚔ in battle    │  ← header
├────────────────────────────────┬────────────────────────────────────┤
│                                │                                    │
│   🔨  F O C U S               │  📋 TODAY'S RECEIPT                │
│                                │  ════════════════                  │
│           24:13                │  09:12  🍅 Auth Refactor           │  ← RichLog
│                                │  ⚔  Write the refresh token test  │  (scrollable,
│   ████████████████░░░░░░       │  ✦  Test written, null claim edge │   auto-appends)
│              68%               │     case found                     │
│                                │                                    │
│  ⚔ YOUR CHARGE                 │  09:52  🍅 Auth Refactor           │
│  ┌──────────────────────────┐  │  ⚔  [running…]                    │
│  │ Squash the expiry bug …  │  │                                    │
│  └──────────────────────────┘  │                                    │
│                                │                                    │
│  ✦ ─── ☕ ─── ✦ ─── ☕ ───    │                                    │
│  🔨    ★    🔨    🔨           │                                    │
│                                │                                    │
│  [x] stop   ESC · hide         │                                    │
└────────────────────────────────┴────────────────────────────────────┘
```

**Left column — Focus Zone:**

| Element | Textual Widget | Notes |
|---|---|---|
| Segment label (`F O C U S`) | `Static` (Rich markup) | Large, colour-coded per seg type |
| Countdown timer | **`Digits`** | Large-digit display; topmost element in the focus area |
| Progress bar | **`ProgressBar`** | Single bar below the timer; depletes during work, fills during break |
| Percentage label | `Static` | Centred below the bar; updates every tick (e.g. `68%`) |
| "⚔ Your Charge" block | `Static` inside `Vertical` | Shows charge text for current pomo; border-styled |
| Journey track | `Static` (Rich `Text`) | Existing cycle-node row; unchanged |
| Footer hints | `Static` | Contextual key hints |

**Right column — Daily Receipt:**

| Element | Textual Widget | Notes |
|---|---|---|
| Section header | `Label` | "📋 TODAY'S RECEIPT" |
| Separator | **`Rule`** | `line_style="heavy"` |
| Log entries | **`RichLog`** | Auto-scrolls to latest; appends on each deed submit |

Receipt uses `⚔` for Charge lines and `✦` for Deed lines. The `RichLog` persists for the session. On panel open/re-open, it is repopulated from today's sessions in `pomodoros.json`.

---

### 5.6 Charge Gate Screen (Mock)

Shown before every work segment begins (full-width, two-column layout maintained):

```
┌─────────────────────────────────────────────────────────────────────┐
│  🍅  Auth Refactor                          🍅 2/3                  │
├────────────────────────────────┬────────────────────────────────────┤
│                                │                                    │
│  ⚔  Prepare your charge       │  📋 TODAY'S RECEIPT                │
│                                │  ════════════════                  │
│  What will you have forged     │  09:12  🍅 Auth Refactor           │
│  when this 🍅 ends?            │  ⚔  Trace the OAuth flow          │
│                                │  ✦  Found expiry bug in middleware │
│  (name the one thing — a fix,  │                                    │
│   a decision, a draft)         │                                    │
│                                │                                    │
│  ┌──────────────────────────┐  │                                    │
│  │ ▌                        │  │                                    │
│  └──────────────────────────┘  │                                    │
│                                │                                    │
│  [enter] ride out              │                                    │
│  [x] abandon session           │                                    │
│                                │                                    │
└────────────────────────────────┴────────────────────────────────────┘
```

- Timer does not start until `Input` is submitted non-empty.
- `[enter]` / `[Ride Out]` is disabled while field is empty.

---

### 5.7 Deed Gate Screen (Mock)

Shown after every work segment ends (between work end and break):

```
┌─────────────────────────────────────────────────────────────────────┐
│  🍅  Auth Refactor                          🍅 2/3                  │
├────────────────────────────────┬────────────────────────────────────┤
│                                │                                    │
│  🍅  Pomo 2 of 3 complete!     │  📋 TODAY'S RECEIPT                │
│                                │  ════════════════                  │
│  What did you claim?           │  09:12  🍅 Auth Refactor           │
│                                │  ⚔  Trace the OAuth flow          │
│  (a bug slain, a path cleared, │  ✦  Found expiry bug in middleware │
│   a truth discovered)          │                                    │
│                                │  09:52  🍅 Auth Refactor           │
│  ┌──────────────────────────┐  │  ⚔  Squash the expiry bug         │
│  │ ▌                        │  │  ✦  [awaiting your deed…]         │
│  └──────────────────────────┘  │                                    │
│                                │                                    │
│  (submit to unlock your rest)  │                                    │
│                                │                                    │
│  [x] abandon session           │                                    │
│                                │                                    │
└────────────────────────────────┴────────────────────────────────────┘
```

After deed is submitted:

```
│  [enter] take your rest   [s] press on   [x] abandon               │
```

- Break buttons are **hidden** until deed `Input` is non-empty and submitted.
- On submit: deed is saved, `RichLog` updates `✦` line, break buttons appear.
- If the user presses `[x]` before submitting: pomo saved with `deed_skipped: true`, excluded from receipt.

---

### 5.8 Daily Receipt — Always-On Log (Main Board)

The `#stats` bar at the bottom of the main quest board is extended:

**When no pomo is running:**
```
⚔ Total 12   🔥 3   🧱 1   🏆 8   ⏱ 14h logged   |   📋 4 🍅 today  [p] view receipt
```

**When pomo is running:**
```
🍅 Auth Refactor  🔨 Work  24:13  🍅 2/3   |   📋 3 🍅 today  [p] view receipt
```

Pressing `[p]` opens the `DailyReceiptModal`:

```
┌──────────────────────────────────────────────────────────────────────┐
│  📋  Daily Receipt  ·  The 7th of April · Anno MMXXVI                │
│                                                                      │
│  ┌─ 09:12  🍅 Auth Refactor ──────────────────────────────────────┐  │
│  │  ⚔  Trace the OAuth token flow                                 │  │
│  │  ✦  Found expiry bug in middleware — not the flow itself       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ 09:52  🍅 Auth Refactor ──────────────────────────────────────┐  │
│  │  ⚔  Squash the expiry bug in token middleware                  │  │
│  │  ✦  Bug squashed, fix is minimal — one missing null check      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ 10:35  🍅 Auth Refactor ──────────────────────────────────────┐  │
│  │  ⚔  Write the refresh token unit test                          │  │
│  │  ✦  Test written, null claim edge case found and documented    │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  3 pomodoros  ·  ⏱ 1h 15m focused today                             │
│                                                                      │
│  [ESC] Close                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

- Entries rendered with `Rule` separators between blocks.
- `⚔` / `✦` rows rendered as a two-row `Static` per entry (future: `Markdown` for LLM output).
- Only pomodoros with both `charge` and `deed` appear. Incomplete sessions are silently excluded.

---

## 6. Data Model Changes

### `pomodoros.json` — segment shape (additions marked `NEW`)

```json
{
  "type": "work",
  "lap": 2,
  "cycle": 1,
  "completed": true,
  "interruptions": 0,
  "started_at": "2026-04-07T09:52:00Z",
  "ended_at": "2026-04-07T10:17:00Z",
  "charge": "Squash the expiry bug in token middleware",   // NEW — set before work segment
  "deed":   "Bug squashed, fix is minimal — one null check" // NEW — set after work segment
}
```

- `charge`: string | null. Set when the Charge Gate is submitted, immediately before the work timer starts.  
- `deed`: string | null. Set when the Deed Gate is submitted, before the break.  
- Both fields are per work-segment (every lap gets its own charge + deed).  
- A segment with `deed: null` is **excluded from the daily receipt**.  
- A session where `actual_pomos == 0` (stopped before any pomo completes) is also excluded.

---

## 7. Widget Map (Textual)

| Current | Replacement / Addition | Why |
|---|---|---|
| `Static` (MM:SS, hand-rolled) | **`Digits`** | Purpose-built large-digit display; accessible, styled by framework |
| ASCII progress bar in `Static` | **`ProgressBar`** + `Static` (%) | Single bar; percentage rendered as a centred `Static` below — not inline |
| `Static` (daily log) | **`RichLog`** | Scrollable, appendable, handles Rich renderables |
| Nothing (receipt blocks) | **`Rule`** | Semantic separators between receipt entries |
| `Static` (charge display) | `Static` in bordered `Vertical` | Clear visual boundary around the pomo contract |
| `ModalScreen` (pomo panel) | **Full `Screen`**  | Owns the whole terminal; truly immersive |

---

## 8. File Change Surface

| File | Change |
|---|---|
| `pomodoro.py` | `add_segment()` gains `charge` / `deed` params. New helper: `get_today_receipt()` returns today's completed, deed'd segments sorted by `started_at`. |
| `main.py` | `PomodoroStartModal`: collect pomo count only. No charge field here. |
| `main.py` | `PomodoroPanel`: promote to full `Screen`; two-column layout; `Digits` timer; `ProgressBar`; `RichLog` for receipt; "⚔ Your Charge" zone. |
| `main.py` | New `ChargeScreen`: shown before every work segment; required `Input` labelled "What will you have forged when this 🍅 ends?"; timer does not start until submitted. |
| `main.py` | New `DeedScreen`: shown after every work segment; required `Input` labelled "What did you claim?"; break buttons hidden until submitted; on submit appends to `RichLog`. |
| `main.py` | `QuestLogApp._update_stats()`: add pomo-today count + `[p]` receipt hint to stats bar. |
| `main.py` | New `DailyReceiptModal`: reads `get_today_receipt()`, renders ⚔/✦ blocks with `Rule` separators. |
| `styles.tcss` | New styles for: two-column pomo screen, charge zone, deed zone, receipt modal, `Digits` sizing, `ProgressBar` colouring. |

**No new files. No new dependencies.**

---

## 9. Acceptance Criteria

| ID | Criteria |
|---|---|
| AC-1 | Pomo timer does not start until the Charge Gate `Input` is submitted non-empty. |
| AC-2 | Break cannot start until the Deed Gate `Input` is submitted. |
| AC-3 | Charge Gate fires before **every** work segment in a multi-pomo run — not just the first. |
| AC-4 | Deed Gate fires after **every** work segment in a multi-pomo run. |
| AC-5 | Pomo panel renders as a full screen with `Digits` timer and `ProgressBar`. |
| AC-6 | Right sidebar shows `RichLog` of today's receipt, live-updating after each deed submit. |
| AC-7 | Daily receipt log is visible (count + shortcut) in stats bar on main board at all times. |
| AC-8 | `[p]` opens `DailyReceiptModal` showing ⚔/✦ blocks for today only. |
| AC-9 | Segments with `deed: null` are excluded from receipt. |
| AC-10 | `DailyReceiptModal` timestamps use wall-clock time (HH:MM), not ISO. |
| AC-11 | Stopping a session mid-deed saves the segment but excludes it from receipt. |
| AC-12 | Existing pomo behaviour (lap history, journey track, interruptions, break nudge) is unchanged. |

---

## 10. v0.2 Hook

Every entry in the daily receipt maps cleanly to an LLM prompt:

```
Pomodoro 1 — 09:12
  Charge: Trace the OAuth token flow
  Deed:   Found expiry bug in middleware — not the flow itself

Pomodoro 2 — 09:52
  Charge: Squash the expiry bug in token middleware
  Deed:   Bug squashed, one missing null check

Pomodoro 3 — 10:35
  Charge: Write the refresh token unit test
  Deed:   Test written, null claim edge case found and documented

Generate a 3-sentence standup summary and identify any pattern in charge vs. deed drift.
```

The `get_today_receipt()` function returns exactly this payload. In v0.2, a `[g]` keybind calls the LLM and renders the summary in a new pane of the `DailyReceiptModal`.

---

*End of spec. Ready for implementation.*
