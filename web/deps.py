"""FastAPI dependency injection for storage repositories."""

from __future__ import annotations

from fastapi import Request

from core.storage.sqlite_backend import (
    SqliteArtifactKeyRepo,
    SqliteQuestRepo,
    SqlitePomoRepo,
    SqliteTrophyPRRepo,
    SqliteWorkspaceRepo,
)
from core.storage.saga_backend import SqliteSagaRepo
from core.storage.challenge_backend import (
    SqliteChallengeRepo,
    SqliteChallengeTaskRepo,
    SqliteChallengeEntryRepo,
    SqliteChallengeEraRepo,
)


def get_quest_repo(request: Request) -> SqliteQuestRepo:
    return SqliteQuestRepo(request.app.state.db)


def get_pomo_repo(request: Request) -> SqlitePomoRepo:
    return SqlitePomoRepo(request.app.state.db)


def get_trophy_repo(request: Request) -> SqliteTrophyPRRepo:
    return SqliteTrophyPRRepo(request.app.state.db)


def get_workspace_repo(request: Request) -> SqliteWorkspaceRepo:
    return SqliteWorkspaceRepo(request.app.state.db)


def get_challenge_repo(request: Request) -> SqliteChallengeRepo:
    return SqliteChallengeRepo(request.app.state.db)


def get_challenge_task_repo(request: Request) -> SqliteChallengeTaskRepo:
    return SqliteChallengeTaskRepo(request.app.state.db)


def get_challenge_entry_repo(request: Request) -> SqliteChallengeEntryRepo:
    return SqliteChallengeEntryRepo(request.app.state.db)


def get_challenge_era_repo(request: Request) -> SqliteChallengeEraRepo:
    return SqliteChallengeEraRepo(request.app.state.db)


def get_artifact_key_repo(request: Request) -> SqliteArtifactKeyRepo:
    return SqliteArtifactKeyRepo(request.app.state.db)


def get_saga_repo(request: Request) -> SqliteSagaRepo:
    return SqliteSagaRepo(request.app.state.db)
