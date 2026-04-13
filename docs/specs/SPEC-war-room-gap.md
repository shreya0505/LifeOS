# SPEC: War Room — Implementation Gap Analysis

**Author:** Senior Product Engineer  
**Status:** Tracking  
**Version:** 1.1  
**Last Updated:** April 7, 2026  
**Ref Spec:** `SPEC-war-room-pomo.md`

---

## Summary

The War Room spec defines 20 features. This document also tracks post-spec additions.

| Status | Count |
|---|---|
| ✅ Fully implemented | 13 |
| ⚠️ Partially implemented | 3 |
| ❌ Not implemented | 3 |
| ⬜ Deferred / Obsolete | 2 |

---

## ✅ Fully Implemented

| # | Feature | Notes |
|---|---|---|
| 1 | Big block ASCII clock (§3.1) | 6-cell wide digits, always bold, urgent = reverse video |
| 2 | Depleting health bar (§3.2) | 52-char wide bar; color shifts green → yellow → red; break fills cyan; both bars CSS-flush (no gap) |
| 10 | Session war cry at charge gate (§4.4) | `POMO_WAR_CRIES` list, random per charge gate |
| 11 | 3-tier break choice transition (§5) | Short / Extended / Long / Skip / End all wired |
| 8 | Interruption Categorical Menu (§4.2) | `[1–4]` key menu replaces freeform input; stores categorical reason ("distracted", "blocked", "emergency", "personal") on segment |
| 13 | Journey Track Symbols (§6.1) | Full symbol set: `✓` done, `[●]` live, `◑` broken (no reason), `💭` distracted / `⛔` blocked / `🚨` emergency / `🌀` personal, `☕`/`🌿`/`🏖` breaks, `→` abandoned break, `?` pending break choice |
| 17 | Momentum bar (§7.2) | Fills with each clean pomo; shows `N clean · X%`; resets on interrupt or long break |
| 5 | Segment Palette Contrast (§3.5) | `short_break` → cyan; `long_break` → teal |
| 7 | Accountability Mirror (§4.1) | Charge display zone reused in deed mode with "⚔ You charged:" header + italic quoted charge text |
| 16 | Streak Milestone Labels (§7.1) | `_streak_label()` helper: `🔥 1` / `🔥🔥 N Hot Streak` / `🔥🔥🔥 N Unstoppable` / `⚔ DEEP WORK`; shown from streak=1 |
| 19 | Live Narrative Footer (§8.2) | Work timer footer: `{headliner} · 🍅 N · streak · ⏱ Xm focused  ──  [i]/[x]/ESC`; break footer simplified |
| — | RPG Session Headliner *(post-spec)* | 20-item `POMO_RPG_HEADLINERS` list; one chosen randomly per session; shown as `{headliner} · {quest_title}` in the War Room header |
| — | Fluid session start *(post-spec)* | `PomodoroStartModal` and `target_pomos` removed entirely; `[t]` launches the session immediately; resume works without confirmation |

---

## ⚠️ Partially Implemented

**Spec:** Clock and segment label toggle between `bold` and `dim` every second via a separate 1s interval. True heartbeat effect.  
**Current:** Static `reverse` video style when `remaining < 60`. No interval toggle.  
**Gap:** Add `_urgency_pulse_handle` interval; toggle between two styles on the clock/label widgets each tick.

---

### #4 — Victory Flash Banner (§3.4)

**Spec:**
```
╔══════════════════════════════╗
║      🍅  FORGED  🍅          ║
║   Pomo 3 done                ║
║   🔥 3-streak                ║
╚══════════════════════════════╝
```
**Current:** Plain `Static("🔥 VICTORY")` that fades after 1.5s.  
**Gap:** Replace with rich bordered markup including pomo count and current streak. Note: "of N" target removed — show count only.

---

**Spec (revised — no target count):**
```
╔══════════════════════════════════════════════╗
║   ⚔  Session Complete                        ║
║                                              ║
║  Quest:  Write auth module                   ║
║  🍅  3 forged                                ║
║  🔥  Best streak this session: 3             ║
║  ⏱  50 min focused                          ║
║  ⚡  1 interruption  (Distracted)            ║
║                                              ║
║  "The realm is stronger for your effort."    ║
╚══════════════════════════════════════════════╝
         [enter]  Return to the Chronicles
```
**Current:** Plain text `Text()` block; no box, no closing quote, no `[enter]` binding.  
**Gap:** Render bordered markup; append random war cry quote; add `[enter]` action that calls `dismiss()`.

---

## ❌ Not Implemented

### #9 — Charge History ↑/↓ (§4.3)

At the charge gate, `↑` / `↓` cycles through the last 10 unique charge strings from `pomodoros.json` (deduplicated, most recent first). Zero re-typing for repeated tasks.

Needs:
- A helper in `pomo_queries.py` to read past charges
- State on `PomodoroPanel` to store the history list and current index
- Key handlers for `up` / `down` on the charge input

---

### #12 — Iron Will Badge on Skip Break (§5.2)

When the user chooses **Skip** at the break choice gate, briefly show an `⚡ Iron Will` badge for ~1.5s before entering the charge gate.

Currently: skip immediately calls `_show_charge_gate()`. Needs a timed intermediate state.

---

### #15 — Pulsing `[●]` Current Node (§6.3)

A separate `set_interval(0.8, ...)` toggles the active journey node between `[●]` and `[·]`.  
On pomo complete: briefly show `[✦]` in bright green before it settles to `✓`.

Needs:
- `_pulse_handle` interval started in `_enter_timer_mode()`, stopped on exit
- `_pulse_state: bool` toggle
- Journey re-render on each pulse tick (lightweight — only updates `#pomo-journey`)

---

### #18 — Time-of-Day Header Flavour (§8.1)

| Hours | Badge |
|---|---|
| 06:00–11:59 | `⚔ Morning Sortie` |
| 12:00–17:59 | `☀ Afternoon Campaign` |
| 18:00–21:59 | `🌙 Night Watch` |
| 22:00–05:59 | `🦉 Midnight Vigil` |

Badge injected into the pomo header line. Pure wall-clock lookup, no state required.

---

## ⬜ Deferred / Obsolete

### #6 — Danger Zone Styling (§3.6) — **Obsolete**

**Original spec:** When `actual_pomos > target_pomos`, panel border turns yellow + `⚡ BONUS ROUND` badge.  
**Current status:** `target_pomos` has been removed from the data model and UX entirely. The "over target" trigger no longer exists.  
**Decision:** Feature retired as-designed. If a "bonus round" celebration is wanted in future, it needs a new trigger (e.g. exceeding a personal best streak, or a time-based milestone).

---

### #14 — Global Timeline Right Panel (§6.2)

**Decision:** Removed from pomo screen. Will be reintroduced as part of the quest page revamp.  
`get_today_timeline()` in `pomo_queries.py` is preserved and ready.

---

## Implementation Order (updated)

### Pass 1 — ✅ Complete
All 4 items done: `#5` palette, `#16` streak milestones, `#7` accountability mirror, `#19` narrative footer.

### Pass 2 — Interaction upgrades (S/M)
1. `#3` Urgency pulse — separate interval, CSS toggle
2. `#4` Victory banner — rich bordered markup (count only, no target)
3. `#12` Iron Will badge — timed intermediate state
4. `#20` Summary polish — bordered box + quote + enter binding

### Pass 3 — Deeper features (M)
5. `#15` Pulsing node — `_pulse_handle` interval
6. `#9` Charge history — query + state + key handlers

> **Removed from order:** `#6` (Danger Zone) — retired; `#18` (Time-of-Day badge) — superseded by the RPG Session Headliner which fills the same header slot.
