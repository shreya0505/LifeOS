# QuestLog — The Adventurer's Productivity Companion

**A terminal-native quest board + pomodoro timer with RPG theming and trophy gamification.**

---

## Quick Start

```bash
# Run the app
python3 main.py

# Clear all data and start fresh
./clear_data.sh
```

---

## Navigation & Core Keys

| Key | Action | Where |
|-----|--------|-------|
| `↑`/`↓` | Move selection | Quest roster |
| `Enter` | Select/activate quest | Quest roster |
| `q` | Quit app | Anywhere |
| `r` | Refresh all panels | Anywhere |
| `Esc` | Close modal/panel | Modal/panel |

---

## Quest Management

### Quest Lifecycle

Quests flow through these states:
- **Log** → Backlog (not started)
- **Active** → Currently working on
- **Blocked** → Waiting on something
- **Done** → Completed

### Quest Keys

| Key | Action |
|-----|--------|
| `a` | Add new quest |
| `Enter` | Activate quest (from Log) |
| `b` | Block quest |
| `u` | Unblock quest |
| `d` | Mark quest as Done |
| `x` | Delete quest |
| `f` | Toggle 🐸 frog flag (dreaded task) |

**Eating the Frog:** Mark difficult/dreaded tasks with `f` to flag them as 🐸. Completing frog quests earns special trophies in the Hall of Valor.

---

## Pomodoro Sessions

### Starting a Session

1. Select a quest with `Enter`
2. Press `t` to start a pomodoro
3. Enter your **charge** — what you'll conquer in this 🍅
4. Timer begins

### During Work (🔨 25 min)

| Key | Action |
|-----|--------|
| `c` | **Swift finish** — complete early (records time saved) |
| `i` | **Interrupt** — pause and log reason, then resume |
| `x` | **Abandon quest** — end entire session |
| `Esc` | Hide panel (timer continues) |

### After Work Completes

- Bell rings
- **Deed gate** appears: "What spoils did you claim, warrior?"
- Enter what you accomplished
- **Forge type** (optional, before pressing Enter):
  - `h` 💀 **Hollow** — forge burned cold, barely worked
  - *(default)* 🍅 **Normal** — standard forge
  - `b` ⚡ **Berserker** — battle fury, flow state, exceeded expectations
- Choose rest:
  - `1` Short rest (5m) ☕
  - `2` Camp fire (10m) 🌿
  - `3` Full rest (15m) 🏖 *(resets streak)*
  - `4` Press on — skip break
  - `e` End quest

### Forge Types

**Hollow** 💀 = The forge burned cold — you went through the motions but barely worked. Hollow forges are recorded but **do not count** as completed pomos in stats or trophies.

**Berserker** ⚡ = Battle fury consumed you — deep flow state, forged far beyond a single pomo's worth. Berserker forges count as 1 pomo but are flagged as exceptional. When a session has a berserker forge, the `⚡ BERSERKER` badge appears in the pomo header.

Toggle forge type with `h`/`b` in the deed gate before submitting. Press again to deselect (reverts to normal).

### Key Concepts

**Charge** = Your battle cry before work (intent)  
**Deed** = Your spoils after work (outcome)  
**Streak** = Consecutive pomos without breaks  
**Momentum** = Consecutive pomos without interruptions  
**Hollow** = Forge that burned cold (💀)  
**Berserker** = Flow state forge (⚡)

---

## Panels

### 1. Quest Roster (Left)
- Current quest (Active)
- Blocked quests
- Backlog (Log)
- Completed (Done) — today only

### 2. Adventure's Chronicle (Center)
Daily, weekly, and all-time stats:
- Pomos completed today/week
- Focus time
- Quest completion rate
- Interrupt analysis
- Visual heatmap of the week

Press `o` for full dashboard with detailed metrics.

### 3. Hall of Valor (Right)
**Daily-resetting trophy case** with 7 trophies:

| Trophy | Icon | Tiers | What it tracks |
|--------|------|-------|----------------|
| **Frog Slayer** | 🐸 | Eaten / Before noon / First thing | Completing dreaded tasks early |
| **Swamp Clearer** | 🐸 | 1/2/4 frogs | Volume of frogs on bad days |
| **Forge Master** | 🔨 | 2/6/10 pomos | Focused work (~1hr/3hr/5hr) |
| **Untouchable** | 🛡️ | 2/4/7 clean | Pomos without interruptions |
| **Quest Closer** | ⚔️ | 3/5/8 quests | Quests completed |
| **Scribe** | 📜 | 1/3/all documented | Pomos with deed logged |
| **Ironclad** | ☕ | 1/3/all with break | Taking breaks after pomos |

**Tiers:** 🥉 Bronze → 🥈 Silver → 🥇 Gold

**Personal Records (PR):** Your best-ever single-day performance for each trophy (shown with ★).

---

## Daily Receipt

Press `p` to view **today's completed work**:

```
── 09:30  🍅 Fix auth bug
  ⚔  Nail the OAuth flow redirect
  ✦  Bug squashed, PR merged

── 11:00  🍅 Design review doc
  ⚔  Draft API contract section
  ✦  Contract drafted, team reviewed
```

Shows all work with charge (⚔) and deed (✦).

---

## Data Storage

All data is stored locally in JSON files:
- `quests.json` — Quest state and history
- `pomodoros.json` — All pomo sessions and segments
- `trophies.json` — Personal records

**Timezone:** UI displays in **IST (Asia/Kolkata)**, data stored in UTC.

---

## Workflow Tips

### Morning Ritual
1. Review backlog, mark hardest task as 🐸 frog
2. Activate frog quest
3. Start pomo — eat the frog first

### Focus Sprint
1. Activate quest
2. Press `t` → charge with specific outcome
3. Work 25 min
4. Log deed (what you claimed)
5. Take break or press on

### End of Day
1. Press `o` for dashboard overview
2. Review Hall of Valor trophies
3. Press `p` for today's receipt
4. Mark remaining quests as blocked or log new ones

---

## RPG Theming Guide

| Term | Means |
|------|-------|
| Quest | Task/project |
| Charge | Your intent before work |
| Deed | Your outcome after work |
| Forge | Complete pomos |
| Hollow | Pomo where you barely worked (💀) |
| Berserker | Flow state pomo, exceeded expectations (⚡) |
| Frog | Dreaded task |
| Eat the frog | Complete dreaded task |
| Swiftblade | Complete pomo early |
| Warrior/Adventurer | You |
| Hall of Valor | Trophy panel |
| The Fray | Active work |
| Respite | Break |
| Abandon | Stop session |

---

## Troubleshooting

**Timer not visible?**  
Press `t` while a quest is selected.

**Can't activate quest?**  
Make sure it's in the Log section (not Active/Blocked/Done).

**Lost work after interruption?**  
Press `i` instead of `x` — interrupt resumes the session, abandon ends it.

**Wrong day displayed?**  
App uses IST timezone. If you're not in IST, edit `USER_TZ` in `utils.py`.

**Clear all data?**  
Run `./clear_data.sh` (creates backups first).

---

## Architecture

- **Framework:** Textual (Python TUI)
- **Rendering:** Rich (tables, progress bars, markup)
- **Styling:** `styles.tcss` (CSS-like)
- **Data:** JSON files (no database)

---

## Files

```
questlog/
├── main.py              # App entry, pomo timer logic
├── quest_store.py       # Quest CRUD + frog toggle
├── quest_panel.py       # Quest roster widget
├── pomo_store.py        # Pomo session/segment persistence
├── pomo_panel.py        # Pomo timer UI
├── pomo_queries.py      # Daily receipt queries
├── chronicle_panel.py   # Stats + heatmap widget
├── trophy_store.py      # Trophy computation + PRs
├── trophy_panel.py      # Hall of Valor widget
├── modals.py            # Dashboard, receipt modals
├── renderers.py         # Block clock, health bar, etc.
├── utils.py             # Metrics, fantasy date, timezone
├── styles.tcss          # UI styling
├── clear_data.sh        # Data reset script
└── INSTRUCTIONS.md      # This file
```

---

**May your quests be many and your focus unbreakable. ⚔️**
