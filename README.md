# LifeOS (QuestLog) ⚔️🍅

**A productivity companion featuring an active quest board and pomodoro timer with RPG theming and trophy gamification.**

LifeOS provides two distinct interfaces built on a shared core logic layer:
1. **Terminal User Interface (TUI):** A focused, keyboard-driven experience.
2. **Web Interface:** A sleek, interactive browser-based dashboard.

---

## ✨ Features

- **RPG-Themed Quest Board:** Manage tasks as "quests" to conquer. Prioritize dreaded tasks by marking them as "Frogs" (🐸).
- **Advanced Pomodoro Timer:** Go into "The Fray" with Pomodoros, logging your "Charge" (intent) and "Deed" (outcome). Track "Hollow" (💀) and "Berserker" (⚡) flows.
- **Gamification & Trophies:** Earn trophies in the "Hall of Valor" for eating frogs early, deep focus, and consistent logging. Features tiers (🥉, 🥈, 🥇) and personal records.
- **Detailed Analytics (Adventure's Chronicle):** View daily/weekly stats, focus heatmaps, and interruption analysis.
- **Dual Interfaces:** Seamlessly switch between the terminal and web frontend depending on your workflow.

---

## 🛠️ Tech Stack

- **Core:** Python 3.10+
- **Terminal UI:** Textual, Rich (File-based JSON storage)
- **Web App:** FastAPI, Jinja2, HTMX, Alpine.js, SSE (Async SQLite storage)
- **Containerization:** Docker & Docker Compose

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have **Python 3.10+** installed, or use **Docker**.

### 2. Local Setup
```bash
# Enter project directory
cd LifeOS

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install textual rich fastapi uvicorn[standard] jinja2 aiosqlite sse-starlette httpx
```

### 3. Run the App

You can choose to run the app via the TUI, Web App, or use Docker.

#### Option A: Terminal UI (TUI)
```bash
python3 -m tui
```
*Note: Uses localized JSON file storage.*

#### Option B: Web Application
```bash
uvicorn web.app:app --reload
```
Access the web app at `http://127.0.0.1:8000`.
*Note: Uses async SQLite storage.*

#### Option C: Docker (Web App)
For a containerized setup, simply run:
```bash
docker compose up --build
```
Access the app at `http://localhost:8000`.

---

## 🧹 Maintenance

To clear all data and start fresh (this creates backups first):
```bash
./clear_data.sh
```

---

## 🏗️ Architecture

QuestLog shares a common `core` across both frontends.
- `core/`: Shared business logic, storage interfaces (`Protocols`), state machines, and metrics computation.
- `tui/`: Textual application reading/writing to local JSON files (`json_backend.py`).
- `web/`: FastAPI application utilizing HTMX, Alpine.js, and Server-Sent Events (SSE) backed by a SQLite database (`sqlite_backend.py`).

---

## 🧪 Testing

Testing requires additional dependencies:
```bash
pip install pytest pytest-asyncio httpx aiosqlite

# Run all tests
pytest

# Run tests with verbose output
pytest -v
```
Tests are executed against a temporary in-memory SQLite database setup via pytest fixtures.

---

## 📖 Instructions & Manuals

- For an in-depth guide on the Pomodoro flow, Quest Lifecycle, RPG mechanics, and keyboard shortcuts, please read [`INSTRUCTIONS.md`](./INSTRUCTIONS.md).
- For contribution guidelines and deeper architectural details, check [`CLAUDE.md`](./CLAUDE.md).

---

*May your quests be many and your focus unbreakable. ⚔️*
