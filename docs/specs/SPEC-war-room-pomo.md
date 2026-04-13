# SPEC: The War Room — Pomodoro v2

**Author:** Senior Product Engineer  
**Status:** Ready for Implementation  
**Version:** 1.0  
**Last Updated:** April 7, 2026  
**Builds on:** `SPEC-intentional-pomo.md` (v1.1) — the Charge/Deed loop is preserved in full

---

## 1. Overview

The existing pomodoro screen is functionally correct but visually muted and behaviourally passive. This spec transforms it into **The War Room** — a full-screen immersive focus environment that is dramatic to look at, ritually structured to interact with, and honest in what it records.

Three design pillars:

| Pillar | Goal |
|---|---|
| **Visual Drama** | The timer dominates. Every state transition is felt, not just seen. |
| **Behavioural Depth** | Every interaction builds accountability and self-awareness. |
| **Organic History** | The journey and timeline grow from what actually happened, not a predetermined blueprint. |

---

## 2. What Changes

### 2.1 Removed

- `laps_before_long` config key and all logic depending on it. There is no longer an automatic long-break trigger based on lap count.
- The fixed 8-node future-blueprint journey track. The journey no longer predicts the future — it records the past.
- The concept of "Cycle N". Replaced by natural cycle boundaries the user defines themselves (see §5).
- The right-column `TODAY'S RECEIPT` rich log. Replaced by the **Global Pomo Timeline** (see §6).

### 2.2 Added Config Key

```python
POMO_CONFIG = {
    "work_secs":             25 * 60,
    "short_break_secs":       5 * 60,
    "extended_break_secs":   10 * 60,   # new
    "long_break_secs":       30 * 60,
    # laps_before_long → removed
}
```

---

## 3. Visual Drama

### 3.1 Big Block Clock

Replace the `MM:SS` Static with a full ASCII block-digit clock rendered from a lookup table of Unicode block characters. No new dependencies. The clock is the dominant visual anchor of the left panel.

```
██╗ ██████╗
╚═╝ ╚════██╗
██╗  █████╔╝
╚═╝  ╚═══██╗
██╗ ██████╔╝
```

The clock color matches the current segment state (see §3.5).

### 3.2 Depleting Health Bar

Replace `ProgressBar` with a custom `Static` widget rendering a `█▓▒░` gradient bar.

- **During work:** bar depletes left to right
  - `> 40%` remaining → green `████████░░░░░░░░`
  - `15–40%` remaining → yellow `████░░░░░░░░░░░░`
  - `< 15%` remaining → red `█░░░░░░░░░░░░░░░`
- **During break:** bar fills left to right (progress, not drain), color is teal/cyan throughout

### 3.3 Urgency Pulse (Final 60 Seconds)

In the last 60 seconds of any work segment, the clock label and segment icon toggle between `bold` and `dim` every second using a CSS class toggle on a separate 1s interval. Creates a heartbeat effect without any animation library.

### 3.4 Victory Flash Banner

When a work segment completes, before transitioning to the deed gate, the left panel briefly renders a full-height centered banner for ~1.5 seconds:

```
╔══════════════════════════════╗
║      🍅  FORGED  🍅          ║
║   Pomo 2 of 4 done           ║
║   🔥 3-streak                ║
╚══════════════════════════════╝
```

Implemented via `set_timer(1.5, ...)` + display toggle on a dedicated `Static`. No extra library.

### 3.5 Segment Palette Contrast

Work and break are visually distinct environments:

| State | Clock Color | Bar Direction | Bar Color | Label Icon |
|---|---|---|---|---|
| Work | Red | Depletes → | Red/Yellow/Green | `⚔` |
| Short break | Cyan | Fills → | Cyan | `☕` |
| Extended break | Cyan | Fills → | Cyan | `☕+` |
| Long break | Teal | Fills → | Teal | `🏖` |

### 3.6 Danger Zone Styling

When `actual_pomos > target_pomos`, the panel border changes to **yellow** and the header gains a `⚡ BONUS ROUND` badge. Celebrates going over rather than flagging it as a warning.

---

## 4. Accountability & Behavioural Depth

### 4.1 Accountability Mirror

The deed gate shows the original charge in a bordered yellow box **above** the deed input, before any text is entered:

```
┌─────────────────────────────────────────┐
│ ⚔  You charged:                         │
│  "Write auth tests for the login route" │
└─────────────────────────────────────────┘
What did you claim?
▸ _
```

No new data required — `_pomo_charge` is already in memory.

### 4.2 Interruption Log

When the user presses `x` to interrupt mid-pomo, instead of silently stopping, a single-keypress prompt is shown:

```
⚠  Why did you stop?

  [1] Distracted    [2] Blocked
  [3] Emergency     [4] Personal
```

The reason is stored on the segment as `interruption_reason: str`. Feeds the dashboard interruption rate metric with richer categorical data. Shown in the end-of-session summary.

### 4.3 Charge History (↑/↓)

At the charge gate, pressing `↑` / `↓` cycles through the last 10 unique charge strings from `pomodoros.json` (deduplicated, most recent first). Supports repeated-task patterns with zero re-typing. No new storage — read from existing segments.

### 4.4 Session War Cry

At the charge gate, a randomly selected one-liner from an internal list of ~20 quest-themed phrases is shown dimly above the input field:

> *"The realm does not wait. Charge forth."*  
> *"One pomo at a time. Make it count."*  
> *"No charge is too small. Begin."*

Rotates randomly per charge gate. Internal constant list, no network call.

---

## 5. The Break System — "The Chosen Rest"

### 5.1 Core Principle

**You earn a break after every pomo. What kind is entirely your call.**

There is no automatic long-break trigger. After every work segment deed is submitted, the user sees a break choice transition screen:

```
🍅 Pomo 3 forged — 🔥 3-streak

  ☕  How long do you rest?

  [enter]  Short rest      5m
  [e]      Extended rest  10m
  [l]      Long rest      30m
  [s]      Skip rest  →  charge now
  [x]      End session
```

### 5.2 Break Tiers

| Key | Label | Duration | Journey Symbol | Notes |
|---|---|---|---|---|
| `enter` | Short rest | 5m | `☕` | Normal rhythm |
| `e` | Extended rest | 10m | `☕+` | Mid-session fatigue |
| `l` | Long rest | 30m | `🏖` | Full cycle boundary — resets streak |
| `s` | Skip rest | — | `→` | Bypass arrow in journey; shows ⚡ Iron Will badge |
| `x` | End session | — | — | Goes to end-of-session summary |

### 5.3 Streak Behaviour per Break Choice

| Break choice | Streak effect |
|---|---|
| Short | Continues |
| Extended | Continues (rest is longer, focus intent intact) |
| Long | **Resets to 0** — long rest is a natural cycle boundary, a fresh start |
| Skip | Continues + ⚡ Iron Will badge shown momentarily |
| Interruption (`x` mid-pomo) | **Resets to 0** |

### 5.4 Data Model

Break segments gain a `break_size` field: `"short" | "extended" | "long"`. The existing `type` field (`short_break` / `long_break`) is retained for backward compatibility:

- `short` and `extended` map to `type: "short_break"`
- `long` maps to `type: "long_break"`

Skipped breaks are **not logged as a segment** — the journey shows two adjacent work nodes connected by `→`.

---

## 6. Journey Tracks

There are now two journey views, each serving a different scope.

### 6.1 Per-Task Track (Left Panel — replaces the old cycle track)

Shows the pomo history for **the currently active quest in the current session only**, growing rightward from actual events:

```
Task: Write auth module
──────────────────────────────────────────────────────
✓ ── ☕ ── ✓ ── 🏖 ── ✓ ── ☕+ ── [●] ── ?
🔨        🔨         🔨              🔨
```

**Node rules:**

| Symbol | Meaning |
|---|---|
| `✓` | Completed work pomo |
| `◑` | Interrupted/broken pomo |
| `☕` | Short break (taken) |
| `☕+` | Extended break (taken) |
| `🏖` | Long break (taken) |
| `→` | Break skipped (bypass arrow between two work nodes; no break node added) |
| `[●]` | Currently active segment (pulses — see §6.3) |
| `?` | Pending break choice (shown after pomo completes, before user picks) |

**No future nodes.** The track does not show a predetermined plan. It shows what happened.

**Long break as organic boundary:** A `🏖` node in the track is simply a record that you took a long rest here. It carries no special structural meaning beyond that.

### 6.2 Global Timeline (Right Panel — replaces TODAY'S RECEIPT log)

Shows a **full chronological timeline of all pomos across all tasks today**, in a single scrollable view:

```
TODAY'S TIMELINE
────────────────────────────────────────────────────────────────
[Write auth module ]  ✓ ── ☕ ── ✓ ── 🏖
[Fix login bug     ]                      ✓ ── ☕+ ── ✓ ── ☕
[Write auth module ]                                          ✓ ── ☕ ── [●]
09:00              09:30              10:00               10:30
```

- Each row = one session (quest), positioned chronologically
- Task label shown at left of each row
- Nodes use the same symbol set as the per-task track
- The active pomo `[●]` is always at the rightmost edge
- Timestamps shown at meaningful intervals below
- This is a read-only live view — no interaction required

The daily receipt (charge/deed log) remains accessible via `[p]` keybind as today.

### 6.3 Pulsing Current Node

The `[●]` node in both tracks toggles between `[●]` and `[·]` on a 0.8s interval via a separate `set_interval`, independent of the main timer tick. When a pomo completes, the node briefly shows `[✦]` in bright green before settling to `✓`.

---

## 7. Streak & Momentum

### 7.1 Live Streak Counter

Shown in the pomo header, adjacent to the pomo count:

```
⚔ Write auth module   🍅 2/4   🔥 3
```

Milestone labels at key thresholds:

| Streak | Display |
|---|---|
| 1 | `🔥 1` |
| 3 | `🔥🔥 3 — Hot Streak` |
| 5 | `🔥🔥🔥 5 — Unstoppable` |
| 7+ | `⚔ DEEP WORK` |

### 7.2 Momentum Bar

A second, narrower bar below the health bar that **fills** with one green block per clean completed pomo. Does not drain. Resets on any interruption or long break (streak-aligned).

```
Momentum  ████████░░░░░░░░  (3 clean)
```

Visually distinct from the timer bar — represents cumulative clean work within this run.

---

## 8. Atmosphere & Narrative

### 8.1 Time-of-Day Header Flavour

The pomo header prefix changes based on wall-clock hour:

| Hours | Badge |
|---|---|
| 06:00–11:59 | `⚔ Morning Sortie` |
| 12:00–17:59 | `☀ Afternoon Campaign` |
| 18:00–21:59 | `🌙 Night Watch` |
| 22:00–05:59 | `🦉 Midnight Vigil` |

### 8.2 Live Narrative Footer

During the work timer, the footer replaces the raw keybind hint with a live narrative line (keybinds still shown, but dead space is used):

```
Night Watch · Pomo 3 · 🔥 3-streak · ⏱ 42m focused today  ──  [x] stop · ESC hide
```

All values already in memory. No extra state required.

### 8.3 End-of-Session Summary Screen

When the user ends a session (via `x` at the break transition or interruption), before returning to the quest log, a brief full-panel summary is shown:

```
╔══════════════════════════════════════════════╗
║   ⚔  Session Complete                        ║
║                                              ║
║  Quest:  Write auth module                   ║
║  🍅  2 of 4 forged                           ║
║  🔥  Best streak this session: 3             ║
║  ⏱  50 min focused                          ║
║  ⚡  1 interruption  (Distracted)            ║
║                                              ║
║  "The realm is stronger for your effort."    ║
╚══════════════════════════════════════════════╝
         [enter]  Return to the Chronicles
```

One screen, one keybind. The closing quote is drawn from the same war-cry list as the charge gate (§4.4).

---

## 9. Data Model Changes

### 9.1 Config

```python
POMO_CONFIG = {
    "work_secs":             25 * 60,
    "short_break_secs":       5 * 60,
    "extended_break_secs":   10 * 60,   # new
    "long_break_secs":       30 * 60,
    # removed: laps_before_long
}
```

### 9.2 Segment Schema Additions

```json
{
  "type": "short_break",
  "break_size": "extended",          // new: "short" | "extended" | "long" | null (work segs)
  "interruption_reason": null,       // new: "distracted" | "blocked" | "emergency" | "personal" | null
  "lap": 3,
  "cycle": 1,
  "completed": true,
  "interruptions": 0,
  "charge": "...",
  "deed": "..."
}
```

### 9.3 Session Schema Additions

```json
{
  "streak_peak": 3,                  // new: highest streak reached in this session
  "total_interruptions": 1           // new: count for summary screen
}
```

---

## 10. Feature Checklist

| # | Feature | Section | Effort |
|---|---|---|---|
| 1 | Big block ASCII clock | §3.1 | M |
| 2 | Depleting health bar (█▓▒░, colour shifts) | §3.2 | S |
| 3 | Urgency pulse final 60s | §3.3 | S |
| 4 | Victory flash banner | §3.4 | S |
| 5 | Segment palette contrast (work vs break) | §3.5 | S |
| 6 | Danger zone styling (over target) | §3.6 | XS |
| 7 | Accountability mirror at deed gate | §4.1 | S |
| 8 | Interruption log with reason | §4.2 | M |
| 9 | Charge history ↑/↓ | §4.3 | M |
| 10 | Session war cry at charge gate | §4.4 | XS |
| 11 | 3-tier break choice transition | §5 | M |
| 12 | Skip break → Iron Will badge | §5.2 | S |
| 13 | Per-task journey track (grows from history) | §6.1 | M |
| 14 | Global timeline (right panel) | §6.2 | L |
| 15 | Pulsing current node | §6.3 | S |
| 16 | Live streak counter + milestones | §7.1 | S |
| 17 | Momentum bar | §7.2 | S |
| 18 | Time-of-day header flavour | §8.1 | XS |
| 19 | Live narrative footer | §8.2 | S |
| 20 | End-of-session summary screen | §8.3 | M |

---

## 11. What Is Explicitly Preserved

All decisions from `SPEC-intentional-pomo.md` (v1.1) remain in force:

- The **Charge Gate** is a hard gate before every work segment. No skip.
- The **Deed Gate** holds the break hostage. Break options are hidden until deed is submitted.
- The **`[p]` Daily Receipt** modal remains accessible from any screen.
- The `get_today_receipt()` interface is unchanged — it is the v0.2 LLM payload contract.
- `pomodoros.json` remains flat-file, append-only, no new dependencies.

---

## 12. Out of Scope (this spec)

- LLM standup generation (v0.2)
- Cross-day pattern analysis (v0.3)
- User-configurable timer durations via UI
- Subtask checklists or per-pomo notes beyond charge/deed
