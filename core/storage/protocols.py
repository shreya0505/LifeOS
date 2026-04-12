"""Repository protocols for QuestLog storage backends.

Both JSON and SQLite backends implement these interfaces, ensuring
core business logic works identically against either storage layer.
"""

from __future__ import annotations

from typing import Protocol


class QuestRepo(Protocol):
    def load_all(self) -> list[dict]: ...
    def add(self, title: str) -> dict: ...
    def update_status(self, quest_id: str, status: str) -> dict | None: ...
    def abandon(self, quest_id: str) -> dict | None: ...
    def toggle_frog(self, quest_id: str) -> dict | None: ...


class PomoRepo(Protocol):
    def load_all(self) -> list[dict]: ...
    def start_session(self, quest_id: str, quest_title: str) -> dict: ...
    def get_session(self, session_id: str) -> dict | None: ...
    def add_segment(
        self,
        session_id: str,
        seg_type: str,
        lap: int,
        cycle: int,
        completed: bool,
        interruptions: int,
        started_at: str,
        ended_at: str,
        charge: str | None = None,
        deed: str | None = None,
        break_size: str | None = None,
        interruption_reason: str | None = None,
        early_completion: bool = False,
        forge_type: str | None = None,
    ) -> dict | None: ...
    def update_segment_deed(
        self, session_id: str, lap: int, deed: str,
        forge_type: str | None = None,
    ) -> None: ...
    def end_session(self, session_id: str) -> dict | None: ...


class TrophyPRRepo(Protocol):
    def load_prs(self) -> dict: ...
    def save_prs(self, prs: dict) -> None: ...
