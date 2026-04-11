# QuestLog Web UI — Page Descriptions for UX/UI Review

> **Purpose:** This document describes every page and view in the QuestLog web app. It is intended for a UI/UX expert to use as a starting point for theme, design, typography, and layout decisions.
>
> **What QuestLog is:** A personal productivity tool built around a Pomodoro timer with an RPG/fantasy skin. The core loop: declare what you'll do (Charge), work a timed session, then record what you actually did (Deed). Quests are tasks. Pomos are focused work sessions. Trophies are achievements. The language is fantasy-flavored — forge, warrior, conquered, chronicles — but the UX should feel calm, intentional, and readable, not noisy or over-themed.

---

## 1. Main Hub (`/`)

The single-page entry point. Everything lives here through tabs and overlays.

**Header:** App title ("STARFORGE") with a fantasy-formatted date beneath it (e.g., "The 10th of April, 2026 in the Age of Code").

**Three tabs:**

| Tab | Content |
|-----|---------|
| **Inscribe** | Form to create a new quest (title input + submit button) |
| **Board** | Kanban view of all quests by status |
| **Metrics** | Two-panel split: Chronicle (left) + Hall of Valor (right) |

**Footer stats bar:** Persistent row showing quest counts (total, active, done) and today's pomo count. Polls every 60s.

**Keyboard shortcuts:** `n` = jump to Inscribe, `d` = open War Room, `r` = open Receipt, `t` = start pomo on first active quest, `Escape` = close any overlay.

**Feel needed:** The hub should feel like a home base — warm, spacious, not cluttered. The tab bar should be prominent but not heavy. The header should feel ceremonial without being loud. The stats bar should be glanceable and unobtrusive.

---

## 2. Inscribe Tab (Quest Creation)

A simple centered form: one text input for the quest title and a submit button.

**Behavior:** After submitting, the view auto-switches to the Board tab so the user sees their new quest appear. The button should have a satisfying micro-interaction on click (currently an electric zap animation).

**Feel needed:** This should feel like a moment of intention-setting. The form should be large, centered vertically, and invite focus. Not a throwaway input — this is the start of a commitment. The button press should feel rewarding.

---

## 3. Quest Board (Kanban)

Four vertical columns representing the quest lifecycle:

| Column | Status | Emotional Tone |
|--------|--------|----------------|
| Quest Board | New/unstarted quests | Neutral, waiting |
| In Battle | Active quests being worked on | Energized, warm |
| Blocked | Paused quests | Cautionary, tense |
| Conquered | Completed quests | Satisfied, calm |

**Each quest card shows:**
- Quest title
- Optional frog marker (high-priority indicator)
- Elapsed time since creation
- Today's pomo count for that quest
- Action buttons (context-dependent: start, complete, block, unblock, delete, start pomo, toggle frog)

**Interactions:** All actions are button clicks (no drag-and-drop). Clicking an action updates the board in-place via HTMX.

**Feel needed:** Cards should be compact but readable. The four columns need clear visual differentiation. Cards should have subtle hover states. The board should handle 0-20 quests per column gracefully. Empty columns should not look broken. This is the view users will stare at most — it needs to be scannable at a glance.

---

## 4. Pomodoro Timer (Full-Screen Overlay)

When a user starts a pomo, a full-screen overlay takes over. This overlay is a **state machine** with four sequential modes. The user cannot leave without explicitly ending the session.

### 4a. Charge Gate

**Purpose:** Force the user to declare what they will accomplish before the timer starts. This is a hard gate — no skip button.

- Shows the quest title at top
- Prompt: "What will you have forged when this pomo ends?"
- Hint: "(name the one thing — a fix, a decision, a draft)"
- Text input (3-120 chars, required)
- Single submit button: "Begin Forging"

**Feel needed:** Focused, almost meditative. The question should feel important. The input should be large and inviting. No distractions. The user should feel like they're making a promise to themselves.

### 4b. Timer

**Purpose:** Countdown display during focused work (default 25 min).

- Large monospaced countdown (MM:SS)
- Horizontal progress bar that fills as time passes
- Percentage remaining label
- "Your Charge" box reminding the user of their declared intent
- Journey dots showing session progress (e.g., `done done current empty empty`)
- Two escape hatches: Interrupt (abandon) and Swiftblade (complete early)

**Feel needed:** Immersive and distraction-free. The timer should be the dominant element — large, readable from across the room. The progress bar should feel satisfying as it fills. The charge reminder keeps the user anchored. Color should shift between work (warm) and break (cool) segments. This screen needs to feel like a focused cockpit, not a screensaver.

### 4c. Deed Gate

**Purpose:** Capture what the user actually accomplished, immediately after the timer ends. Another hard gate.

- Prompt: "Time's up, warrior. What did you claim?"
- Hint: "(a bug slain, a path cleared, a truth discovered)"
- Text input (3+ chars, required)
- Three submit options:
  - Normal submit (standard forge)
  - Hollow (mark as subpar/distracted session)
  - Berserker (mark as high-intensity session)

**Feel needed:** The energy shifts here — the timer pressure is gone, replaced by a moment of honest reflection. The three forge types should be visually distinct but not confusing. The normal path should be obvious; hollow and berserker are secondary options for power users.

### 4d. Break Choice

**Purpose:** Let the user choose their break after completing a pomo.

- Shows pomos forged this session and streak info
- Five options: Short break (5m), Extended break (10m), Long break (30m), Skip break, End session

**Feel needed:** Relaxed, rewarding. The user just finished focused work — this should feel like a breath. The break options should be easy to scan and quick to choose. Ending the session should be clearly available but not the default path.

---

## 5. Pomo Summary

Shown when the user ends a pomo session (after one or more completed pomos).

- Quest title
- Pomo count: "3 pomos forged" or "No pomos completed this session"
- Two buttons: Return to Board, View Receipt

**Feel needed:** Brief and celebratory if pomos were completed. Graceful and non-judgmental if none were. Quick exit back to the main flow.

---

## 6. Daily Receipt (`/pomos/receipt`)

An overlay showing today's complete Charge/Deed ledger — every pomo from today in reverse chronological order.

**Each entry shows:**
- Timestamp (HH:MM)
- Quest name
- Charge (what was declared)
- Deed (what was accomplished)
- Forge type badge (normal, berserker, hollow)

**Summary footer:** Total real pomos (excluding hollows), total focus time, berserker count, hollow count.

**Empty state:** "No completed pomos with charge & deed today."

**Feel needed:** This is the payoff of the whole system — the accumulated proof of work. It should feel like a ledger or journal. Entries should be clearly structured so the Charge-vs-Deed comparison is instantly visible. The layout should reward scrolling through a productive day. Staggered entry animations make it feel alive. Color-coded borders distinguish forge types (normal, berserker, hollow).

---

## 7. War Room / Dashboard (`/dashboard`)

A full-screen modal overlay showing productivity metrics.

**Two sections:**

### Battlefield Report (Quest Metrics)
- Total quests (all-time)
- Active quests (current)
- Completed quests
- Average quests completed per day
- Completion rate (%)

### Forge Report (Pomo Metrics)
- Total forges today
- Total focus time today
- Forges this week
- Average lap count per session
- Pomo completion rate

**Each metric is a card** with: icon, name, value, context label, and a delta arrow showing change from previous period (positive/negative/neutral color-coded).

**Feel needed:** Information-dense but organized. The metric cards should create a clear grid. Positive deltas should feel good (green/sage), negative should be noticeable but not alarming (red/ember). This is a quick status check, not a deep analytics page — users should be able to glance and leave in 5 seconds.

---

## 8. Chronicle (`/chronicle`)

A retrospective view combining a heatmap and a timeline.

### Week Summary
Quick stats: today's pomo count + time, this week's pomo count + time.

### Activity Heatmap
GitHub-style contribution grid showing 12 weeks of daily pomo activity. Each cell is one day, color intensity reflects pomo count. Today's cell is highlighted. Hover shows exact count.

### Today's Forges (Timeline)
Reverse chronological list of today's completed work segments. Each shows: time, quest, charge, deed, and forge type badge.

**Feel needed:** Zen, retrospective, motivating. The heatmap should feel familiar (GitHub contribution graph is the mental model). The timeline below it provides detail. Together they answer "what have I been doing?" at both macro and micro levels. Empty days should not feel punishing — just neutral.

---

## 9. Hall of Valor / Trophies (`/trophies`)

Achievement system with tiered trophies.

### Summary Bar
Trophy counts by tier: gold, silver, bronze, locked. Plus "best day" stat.

### Trophy Grid
Cards for each trophy showing:
- Tier badge (gold/silver/bronze/locked)
- Trophy name and description (e.g., "The Iron Worker — 5 pomos in a day")
- Progress bar (visual fill from 0-100%)
- Progress label ("3 / 5")
- Personal record display

**Card styling:** Earned trophies are vivid and highlighted. Locked trophies are dimmed/muted. Gold tier trophies should feel special.

**Feel needed:** Gamified and celebratory. This is the long-term motivator. Unlocking a trophy should feel like an event (shimmer animation, particle effects). The grid should make progress visible — seeing a trophy at 4/5 should create healthy pull. But locked trophies should feel aspirational, not discouraging.

---

## 10. Delete Confirmation Modal

Appears when deleting a quest.

- Semi-transparent dark backdrop
- Centered card with: title ("Erase from the Chronicles?"), quest name, Cancel button, Destroy button
- Dismissable with Escape

**Feel needed:** Clear and respectful. The destructive action should be obvious (red/ember button). The cancel path should be easy. The fantasy copy ("Erase from the Chronicles") keeps it on-theme without undermining the seriousness.

---

## Cross-Cutting UX Notes

**Navigation model:** Tab-based with overlays. No page-to-page navigation — everything is within the single hub page or presented as an overlay on top of it.

**Interaction model:** Server-rendered HTML fragments via HTMX. No client-side routing. Alpine.js for local state (timer countdown, tab switching). SSE for live timer updates.

**Celebration moments:** Completing a pomo, unlocking a trophy, and conquering a quest are the three key moments that deserve micro-celebrations (particles, flashes, shimmers). These should feel earned, not constant.

**Empty states:** Every view needs a graceful empty state. New users will see empty boards, zero metrics, and no receipt entries. These states should guide toward action, not feel like error screens.

**Accessibility:** Keyboard shortcuts for power users. Tab navigation throughout. Focus rings on interactive elements. Escape to close overlays. Semantic HTML.

**Responsive:** The app is primarily desktop-focused but should degrade gracefully to tablet. Mobile is secondary but the timer view specifically should work well on phones (people prop up their phone during pomos).

---

## Current Design Direction (For Context)

The current implementation uses a "Tavern Workbench" palette:
- Warm beige/parchment surfaces
- Walnut brown text
- Accent colors: sage (green, success), copper (orange, primary action), hearth (gold, celebration), ember (red, danger), slate (blue-gray, neutral)
- Fonts: Crimson Pro (serif display), Inter (sans body), JetBrains Mono (monospace)

This is open for revision. The fantasy/RPG language is intentional and should be preserved, but the visual treatment is flexible. The key constraint: **the UI should feel like a tool you want to use every day, not a game you play once**. Calm over flashy. Readable over decorative. Warm over cold.
