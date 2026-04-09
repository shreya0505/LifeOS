# QuestLog — Setup Guide

A terminal-native quest board + pomodoro timer with RPG theming and trophy gamification.

## Prerequisites

- **Python 3.10+** (tested on 3.12)

## Setup

```bash
# 1. Unzip
unzip questlog.zip -d questlog
cd questlog

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Activate it
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 4. Install dependencies
pip install textual rich

# 5. Run
python3 main.py
```

## Timezone

The app defaults to **IST (Asia/Kolkata)**. To change it, edit `USER_TZ` in `utils.py`.

## Data

All data lives in local JSON files — no database needed:

| File | Purpose |
|------|---------|
| `quests.json` | Quest state and history |
| `pomodoros.json` | Pomodoro sessions and segments |
| `trophies.json` | Personal records |

Run `./clear_data.sh` to reset all data (creates backups first).

## Quick Reference

| Key | Action |
|-----|--------|
| `a` | Add quest |
| `Enter` | Activate quest |
| `t` | Start pomodoro |
| `d` | Mark quest done |
| `o` | Dashboard |
| `p` | Daily receipt |
| `q` | Quit |

See `INSTRUCTIONS.md` for the full manual.

---

*May your quests be many and your focus unbreakable. ⚔️*
