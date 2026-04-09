# QuestLog — Product & Design Documentation

The complete guide to QuestLog's philosophy, features, UI design, and visual identity.

---

## What Is QuestLog?

QuestLog is a **personal productivity tool** that combines a Kanban quest board with a structured Pomodoro timer. It exists as both a terminal TUI and a web application.

### The Core Insight

> Every productivity tool captures activity. None capture intention. QuestLog closes that loop.

Two questions, asked at the two natural pause points of every Pomodoro cycle, are the entire product surface:

- **Before:** *"What will you have forged when this 🍅 ends?"* — the **Charge**
- **After:** *"What did you claim?"* — the **Deed**

The gap between those two lines — intention vs. execution — accumulated across a day, a week, a quarter — is the most honest productivity data a developer can generate about themselves.

---

## The Accountability Loop

### The Problem

Existing Pomodoro tools solve *scheduling*. They don't solve *accountability*. At the end of a 10-pomo day, a developer sees `🍅 × 10` and feels productive but cannot prove or debrief it.

Three compounding failure modes:

| Failure | Manifestation |
|---------|---------------|
| **Parkinson's Law** | Work expands with no declared scope |
| **Invisible Output** | Effort logged, output is not |
| **No Calibration** | Charge vs. Deed drift never surfaced |

### The Solution

QuestLog owns the 25-minute window — the atomic unit of deep work — where no other tool captures the before-and-after.

```
[Charge Gate]  →  [Focus Timer]  →  [Deed Gate]  →  [Break Choice]  →  repeat
```

- **Charge Gate** is a hard gate. The timer does not start until you declare what you will forge. No skip. The friction is the feature.
- **Deed Gate** holds the break hostage. Break buttons are hidden until you name what you claimed. This exploits the natural decompression desire.
- **Daily Receipt** accumulates `⚔ Charge / ✦ Deed` pairs into a structured, machine-readable work ledger.

---

## Feature Map

### Quest Board (Kanban)

Four-column board with RPG-flavored statuses:

| Status | Meaning | Visual |
|--------|---------|--------|
| **Log** | Backlog | Default surface |
| **In Battle** (active) | Currently working | Copper left border |
| **Blocked** | Waiting on something | Ember left border |
| **Done** | Completed (today only shown in TUI) | Sage left border |

**State machine:**
```
log → active → done
log → blocked → active → done
any → delete
```

**Frog Flag (🐸):** Mark dreaded tasks. Completing frogs earns special trophies. "Eat the frog" — do the hardest thing first.

### Pomodoro Sessions

Sessions are attached to active quests. The flow cycles through modes:

1. **Charge Gate** — Declare your intent. Hard gate. War cry quote shown for motivation.
2. **Focus Timer** — 25-minute countdown with health bar, streak counter, charge intent always visible.
3. **Deed Gate** — Record your outcome. Forge type tagging available:
   - 🍅 **Normal** — standard forge (default)
   - 💀 **Hollow** — barely worked; does not count in stats
   - ⚡ **Berserker** — flow state, exceeded expectations
4. **Break Choice** — You earn a break after every pomo:
   - ☕ Short rest (5m) — streak continues
   - 🌿 Extended rest (10m) — streak continues
   - 🏖 Long rest (30m) — resets streak (natural cycle boundary)
   - ⚡ Skip rest — streak continues, Iron Will badge
   - End session

**Mid-work options:**
- **Swift finish (c/e)** — complete early (Swiftblade)
- **Interrupt (i)** — categorical reason capture (distracted/blocked/emergency/personal), then resume
- **Abandon (x)** — end entire session

### Streaks & Momentum

- **Streak** = Consecutive pomos without long breaks or interruptions
  - `🔥 1` → `🔥🔥 N Hot Streak` (3+) → `🔥🔥🔥 N Unstoppable` (5+) → `⚔ DEEP WORK` (7+)
- **Momentum** = Consecutive clean pomos (no interruptions). Visual bar fills per clean pomo.

### Daily Receipt

A named output, not a log file. Shows all completed `⚔ Charge / ✦ Deed` pairs for the day:

```
09:52  🍅 Auth Refactor
⚔  Squash the expiry bug in token middleware
✦  Bug squashed — one missing null check
```

Only pomos with both charge and deed appear. Incomplete entries silently excluded.

### Chronicle Panel

- **Heatmap** — Activity grid showing pomo density per day (empty/light/medium/heavy)
- **Today's Timeline** — Chronological view of all segments across all tasks today
- **Stats** — Daily, weekly, and all-time: pomos completed, focus time, quest completion rate, interrupt analysis

### Trophy System — Hall of Valor

7 daily-resetting trophies with tiered progression:

| Trophy | Icon | Tiers | Tracks |
|--------|------|-------|--------|
| **Frog Slayer** | 🐸 | Eaten / Before noon / First thing | Completing dreaded tasks early |
| **Swamp Clearer** | 🐸 | 1/2/4 frogs | Volume of frogs on bad days |
| **Forge Master** | 🔨 | 2/6/10 pomos | Focused work volume |
| **Untouchable** | 🛡️ | 2/4/7 clean | Pomos without interruptions |
| **Quest Closer** | ⚔️ | 3/5/8 quests | Quests completed |
| **Scribe** | 📜 | 1/3/all documented | Pomos with deed logged |
| **Ironclad** | ☕ | 1/3/all with break | Taking breaks after pomos |

**Tiers:** 🥉 Bronze → 🥈 Silver → 🥇 Gold

**Personal Records (PR):** Your best-ever single-day performance per trophy, shown with ★.

### Dashboard

Full metrics overlay accessible via `o` (TUI) or dashboard route (web):
- Quest velocity, cycle time, pickup speed
- Pomo completion rates, interruption analysis
- Berserker/Hollow stats
- Delta arrows showing improvement/regression

---

## Visual Identity & Design

### Design Direction: "Tavern Workbench"

A well-lit craftsman's desk in a warm tavern. Parchment warmth, wood-grain depth, ink-dark text, accent colors from nature. **Not** dark mode by default. **Not** SaaS gray.

Three sources of soul:

1. **Texture** — Subtle noise overlay on card surfaces
2. **Typography with character** — Serif for display headings, clean sans for body
3. **Motion that breathes** — Spring physics, earned celebrations

### Color Palette

```
Surfaces:
  parchment  #faf6f0    page background
  cream      #f3ede4    card background
  tan        #ebe3d7    hover, active
  deep tan   #ddd3c3    borders, dividers

Ink:
  walnut     #2c2418    primary text
  brown      #5c4f3c    secondary text
  muted      #8a7d6b    tertiary, timestamps

Accents:
  sage       #7a9e7e    active, success, done
  copper     #c07040    warm action, CTA, start
  hearth     #d4943a    gold/amber, celebration
  ember      #b5493a    blocked, delete, danger
  slate      #6b7f8a    neutral info
```

### Semantic Color Mapping

| Element | Color |
|---------|-------|
| Quest card: log | surface-1, border surface-3 |
| Quest card: active | left border copper |
| Quest card: blocked | left border ember |
| Quest card: done | left border sage |
| Frog badge | sage background |
| Pomo work timer | copper progress bar |
| Pomo break timer | sage progress bar |
| Celebration flash | hearth-glow |
| Trophy gold | hearth |
| Trophy silver | surface-3 |
| Trophy bronze | copper-dim |
| Heatmap levels | surface-3 → sage-dim → sage → deep forest |

### Typography

| Role | Font | Fallback |
|------|------|----------|
| Display / headings | Crimson Pro | Georgia, serif |
| Body / UI | Inter | system-ui, sans-serif |
| Timer / monospace | JetBrains Mono | monospace |

Key usage:
- Page title / section headers → Crimson Pro 600
- Gate prompts ("What will you forge?") → Crimson Pro 400 italic
- Quest card titles, body → Inter 400-500
- Timer countdown → JetBrains Mono 700

### Animation & Motion (Web)

All animations use **Motion** (motion.dev) for spring physics. Key moments:

| Moment | Effect |
|--------|--------|
| Quest → Done | Gold ring pulse + 16 particle burst (hearth/copper/sage colors) |
| Quest → Active | Slide right, copper border fade, subtle glow |
| Quest → Blocked | Ember border pulse, slight shake |
| Quest deleted | Scale down, rotate 2deg, fade out |
| Frog toggle | Badge bounces in (scale 0 → 1.2 → 1.0) |
| Pomo complete | Screen edges flash hearth-glow; streak counter punch |
| Berserker forge | Lightning flash on screen edges |
| Trophy earned | Badge scale + shimmer sweep |
| Heatmap load | Cells fill with 20ms stagger, left-to-right |
| Card hover | Lifts from shadow-2 to shadow-4 |

### TUI Visual Drama (War Room)

The terminal pomo panel ("War Room") uses ASCII-art drama:

- **Pixel Scoreboard Clock** — 7-row tall block-character digits, color-coded by remaining time (green → yellow → red → burning reverse)
- **Depleting Health Bar** — `█▓▒░` gradient bar with color shifts
- **Urgency Pulse** — Clock blinks in final 60 seconds
- **Victory Flash** — Bordered banner on pomo completion
- **Journey Track** — Growing history of symbols: `✓` done, `☕` break, `◑` interrupted, `[●]` active

---

## RPG Flavor Glossary

| Term | Real-World Meaning |
|------|-------------------|
| Quest | Task or project |
| Charge | Your declared intention before a pomo |
| Deed | Your recorded outcome after a pomo |
| Forge | A completed pomodoro |
| Hollow | Pomo where you barely worked (💀) |
| Berserker | Deep flow state pomo (⚡) |
| Frog | A dreaded task (🐸) |
| Eat the frog | Complete the dreaded task first |
| Swiftblade | Complete a pomo early |
| War Cry | Motivational quote at the charge gate |
| Hall of Valor | Trophy panel |
| Chronicle | Activity history / heatmap panel |
| The Fray | Active work |
| Respite | Break |
| Abandon | Stop session |
| Iron Will | Skipping a break |

---

## Workflow Patterns

### Morning Ritual
1. Review backlog, mark hardest task as 🐸 frog
2. Activate frog quest
3. Start pomo — eat the frog first

### Focus Sprint
1. Activate quest
2. Start pomo → charge with a specific, single outcome
3. Work 25 minutes
4. Log deed — what you actually claimed
5. Choose rest or press on

### End of Day
1. Open dashboard for metrics overview
2. Review Hall of Valor trophies
3. View daily receipt — your structured work ledger
4. Block remaining quests or log new ones for tomorrow

---

## Product Roadmap

| Version | Scope | Status |
|---------|-------|--------|
| v0.1 | TUI: Charge/Deed loop, receipt, quest board | ✅ Complete |
| v1.0 | TUI: War Room visual drama, break system, streaks, trophies | ✅ Complete |
| v2.0 | Web app: shared core architecture, full browser UI | 🔄 In progress |
| v0.2 | LLM standup generation from receipt data | 🔮 Future |
| v0.3 | Cross-day pattern analysis (charge/deed drift trends) | 🔮 Future |

### Planned Extensions (Post-Launch)
- Recurring tasks module
- Habit dashboard
- Tiny experiments (time-boxed A/B self-experiments)
- LLM standup generation
- Weekly review summaries
