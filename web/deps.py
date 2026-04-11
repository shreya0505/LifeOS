"""FastAPI dependency injection for storage repositories."""

from __future__ import annotations

from fastapi import Request

from core.storage.sqlite_backend import (
    SqliteQuestRepo,
    SqlitePomoRepo,
    SqliteTrophyPRRepo,
)


def get_quest_repo(request: Request) -> SqliteQuestRepo:
    return SqliteQuestRepo(request.app.state.db)


def get_pomo_repo(request: Request) -> SqlitePomoRepo:
    return SqlitePomoRepo(request.app.state.db)


def get_trophy_repo(request: Request) -> SqliteTrophyPRRepo:
    return SqliteTrophyPRRepo(request.app.state.db)
