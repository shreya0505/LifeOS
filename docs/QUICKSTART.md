# QuestLog — Quick Start

## Terminal UI

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install textual rich
python -m tui.main
```

### Keys

**Quests**

| Key | Action |
|-----|--------|
| `a` | Add quest |
| `s` | Start (log → active) |
| `b` | Block / unblock |
| `d` | Done |
| `x` | Delete |
| `f` | Toggle 🐸 frog |
| `o` | Dashboard |
| `p` | Daily receipt |
| `q` | Quit |

**Pomodoro** — press `t` on an active quest

| Key | Action |
|-----|--------|
| `c` | Swift finish (complete early) |
| `i` | Interrupt (logs reason) |
| `x` | Abandon session |
| `Esc` | Hide panel (timer continues) |

After the timer fires, the **deed gate** appears. Type what you accomplished, then pick a break:

| Key | Break |
|-----|-------|
| `1` | Short (5m) |
| `2` | Camp fire (10m) |
| `3` | Full rest (20m) — resets streak |
| `4` | Press on |
| `e` | End session |

Tag forge type before submitting: `h` = Hollow 💀, `b` = Berserker ⚡

---

## Web UI

```bash
pip install fastapi uvicorn[standard] jinja2 aiosqlite sse-starlette python-multipart
uvicorn web.app:app --reload --port 8000
```

Open **http://localhost:8000**.

### Docker

```bash
docker compose up
```

DB persists in a named volume. Runs on port 8000.

---

## The Loop

Every pomo asks two questions:

1. **Charge** — *"What will you forge?"* (before)
2. **Deed** — *"What did you claim?"* (after)

These pairs accumulate into your **Daily Receipt** — a structured work ledger.

---

## Timezone

Default: `Asia/Kolkata`. Change via `USER_TZ` in `core/config.py` or set `QUESTLOG_TZ` env var.

## Data

- **TUI:** `quests.json`, `pomodoros.json`, `trophies.json`
- **Web:** `questlog.db` (auto-created)
- **Reset:** `./clear_data.sh`

Requires Python 3.10+.
