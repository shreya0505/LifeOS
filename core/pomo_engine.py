"""Pomodoro state machine — shared between TUI and web.

Manages the session lifecycle: charge → work → deed → break_choice → charge.
Emits event dataclasses. Does NOT own UI, timers, or notifications.
The caller (TUI or web) is responsible for:
  - Running a tick interval and calling remaining()
  - Detecting when remaining() <= 0 and calling end_segment(completed=True)
  - Rendering UI based on returned events
  - Scheduling break nudges
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.config import POMO_CONFIG
from core.storage.protocols import PomoRepo


# ── Events ───────────────────────────────────────────────────────────────────

@dataclass
class SegmentStarted:
    seg_type: str
    duration: int
    lap: int
    started_at: str
    session: dict


@dataclass
class SegmentEnded:
    next_gate: str          # "deed" | "charge" | "break_choice" | "summary"
    completed: bool
    seg_type: str
    early_completion: bool = False


@dataclass
class DeedSubmitted:
    forge_type: str | None
    actual_pomos: int
    streak: int
    notification: str       # Pre-formatted notification message


@dataclass
class BreakChosen:
    action: str             # "start_break" | "skip_to_charge" | "end_session"
    seg_type: str | None    # Set if action == "start_break"


@dataclass
class Interrupted:
    new_lap: int
    total_interruptions: int


@dataclass
class SessionStopped:
    quest_title: str
    actual_pomos: int


# ── Engine ───────────────────────────────────────────────────────────────────

class PomoEngine:
    """Pomo session state machine.

    Usage:
        engine = PomoEngine(pomo_repo)
        engine.start_session(quest_id, quest_title)
        engine.submit_charge("fix the bug")
        event = engine.start_segment("work")
        # ... caller runs timer ...
        event = engine.end_segment(completed=True)
        # event.next_gate == "deed"
        event = engine.submit_deed("bug fixed")
        # event -> DeedSubmitted
        event = engine.choose_break("short")
        # event -> BreakChosen(action="start_break", seg_type="short_break")
    """

    def __init__(self, pomo_repo: PomoRepo, config: dict | None = None) -> None:
        self._repo = pomo_repo
        self._config = config or POMO_CONFIG

        # Session state
        self.session: dict | None = None
        self.seg_type: str = "work"
        self.seg_start: datetime | None = None
        self.seg_interruptions: int = 0
        self.lap: int = 0
        self.lap_history: dict = {}
        self.is_resume: bool = False
        self.charge: str = ""
        self.deed_lap: int = -1
        self.deed_seg_started: str = ""
        self.last_early: bool = False

        # War Room state
        self.streak: int = 0
        self.streak_peak: int = 0
        self.momentum: int = 0
        self.total_interruptions: int = 0
        self.session_focus_secs: float = 0.0
        self.last_interruption_reason: str = ""

    @property
    def is_active(self) -> bool:
        return self.session is not None

    @property
    def is_timing(self) -> bool:
        return self.session is not None and self.seg_start is not None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start_session(
        self,
        quest_id: str,
        quest_title: str,
        prior_pomos: int = 0,
        lap_history: dict | None = None,
    ) -> dict:
        """Start a new pomo session. Returns the session dict."""
        self.lap_history = dict(lap_history) if lap_history else {}
        self.lap = prior_pomos
        self.is_resume = prior_pomos > 0
        self.session = self._repo.start_session(quest_id, quest_title)

        # Reset per-session state
        self.seg_type = "work"
        self.seg_start = None
        self.seg_interruptions = 0
        self.charge = ""
        self.deed_lap = -1
        self.last_early = False
        self.streak = 0
        self.streak_peak = 0
        self.momentum = 0
        self.total_interruptions = 0
        self.session_focus_secs = 0.0
        self.last_interruption_reason = ""

        return self.session

    def seg_duration(self) -> int:
        """Duration in seconds for current segment type."""
        return {
            "work":           self._config["work_secs"],
            "short_break":    self._config["short_break_secs"],
            "extended_break": self._config["extended_break_secs"],
            "long_break":     self._config["long_break_secs"],
        }[self.seg_type]

    def remaining(self) -> float:
        """Seconds remaining in current segment."""
        if self.seg_start is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self.seg_start).total_seconds()
        return max(0.0, self.seg_duration() - elapsed)

    def submit_charge(self, charge: str) -> None:
        """Record charge text. Caller should then call start_segment('work')."""
        self.charge = charge

    def start_segment(self, seg_type: str) -> SegmentStarted:
        """Begin a work or break segment. Returns event with timing info."""
        self.seg_type = seg_type
        self.seg_start = datetime.now(timezone.utc)
        self.seg_interruptions = 0

        return SegmentStarted(
            seg_type=seg_type,
            duration=self.seg_duration(),
            lap=self.lap,
            started_at=self.seg_start.isoformat(),
            session=self.session,
        )

    def end_segment(
        self,
        completed: bool,
        interruption_reason: str = "",
        break_size: str | None = None,
        early_completion: bool = False,
    ) -> SegmentEnded:
        """End current segment. Returns event indicating next gate."""
        now = datetime.now(timezone.utc)
        seg_secs = (now - self.seg_start).total_seconds() if self.seg_start else 0.0

        if self.seg_type == "work":
            self.lap_history[self.lap] = "done" if completed else "broken"

        # Determine break_size for storage (extended_break → short_break + break_size)
        stored_type = self.seg_type
        if self.seg_type == "extended_break":
            stored_type = "short_break"
            break_size = "extended"

        self._repo.add_segment(
            session_id=self.session["id"],
            seg_type=stored_type,
            lap=self.lap,
            cycle=0,
            completed=completed,
            interruptions=self.seg_interruptions,
            started_at=self.seg_start.isoformat(),
            ended_at=now.isoformat(),
            charge=self.charge if self.seg_type == "work" else None,
            break_size=break_size,
            interruption_reason=interruption_reason or None,
            early_completion=early_completion,
        )
        self.session = self._repo.get_session(self.session["id"])

        if not completed:
            return SegmentEnded(
                next_gate="charge",
                completed=False,
                seg_type=self.seg_type,
            )

        if self.seg_type == "work":
            # Track focus time
            self.session_focus_secs += seg_secs
            self.last_early = early_completion
            # Streak & momentum
            self.streak += 1
            self.momentum += 1
            if self.streak > self.streak_peak:
                self.streak_peak = self.streak
            # Store deed-gate context
            self.deed_lap = self.lap
            self.deed_seg_started = self.seg_start.isoformat()
            self.lap += 1

            return SegmentEnded(
                next_gate="deed",
                completed=True,
                seg_type="work",
                early_completion=early_completion,
            )
        else:
            # Break finished — reset streak/momentum for long break
            if self.seg_type == "long_break":
                self.streak = 0
                self.momentum = 0

            return SegmentEnded(
                next_gate="charge",
                completed=True,
                seg_type=self.seg_type,
            )

    def submit_deed(
        self, deed: str, forge_type: str | None = None,
    ) -> DeedSubmitted:
        """Record deed + forge type. Returns event with notification info."""
        if not (self.session and self.deed_lap >= 0):
            raise RuntimeError("No active deed gate")

        self._repo.update_segment_deed(
            self.session["id"], self.deed_lap, deed, forge_type=forge_type,
        )
        self.session = self._repo.get_session(self.session["id"])

        actual = self.session.get("actual_pomos", 0)

        if forge_type == "hollow":
            notification = "Hollow forge logged. Onwards, warrior."
        elif forge_type == "berserker":
            notification = f"BERSERKER! Pomo {actual} forged in fury! Streak: {self.streak}"
        else:
            notification = f"Pomo {actual} complete! Streak: {self.streak}"

        self.deed_lap = -1

        return DeedSubmitted(
            forge_type=forge_type,
            actual_pomos=actual,
            streak=self.streak,
            notification=notification,
        )

    def choose_break(self, choice: str) -> BreakChosen:
        """Handle break choice. Returns event indicating what to do next."""
        if choice == "end":
            return BreakChosen(action="end_session", seg_type=None)
        if choice == "skip":
            return BreakChosen(action="skip_to_charge", seg_type=None)

        # Map choice → seg_type
        break_map = {
            "short":    "short_break",
            "extended": "extended_break",
            "long":     "long_break",
        }
        seg_type = break_map.get(choice, "short_break")

        # Long break resets streak + momentum
        if choice == "long":
            self.streak = 0
            self.momentum = 0

        return BreakChosen(action="start_break", seg_type=seg_type)

    def interrupt(self, reason: str) -> Interrupted:
        """Record interruption, advance lap. Returns event."""
        self.last_interruption_reason = reason
        self.total_interruptions += 1
        self.streak = 0
        self.momentum = 0

        now = datetime.now(timezone.utc)
        self.seg_interruptions += 1
        self.lap_history[self.lap] = "broken"

        self._repo.add_segment(
            session_id=self.session["id"],
            seg_type="work",
            lap=self.lap,
            cycle=0,
            completed=False,
            interruptions=self.seg_interruptions,
            started_at=self.seg_start.isoformat(),
            ended_at=now.isoformat(),
            charge=self.charge or None,
            interruption_reason=reason or None,
        )
        self.session = self._repo.get_session(self.session["id"])

        # Update streak_peak on session
        if self.session and self.streak_peak > self.session.get("streak_peak", 0):
            self.session["streak_peak"] = self.streak_peak

        self.lap += 1
        new_lap = self.lap

        return Interrupted(
            new_lap=new_lap,
            total_interruptions=self.total_interruptions,
        )

    def complete_early(self) -> SegmentEnded:
        """Swiftblade — complete current work pomo early."""
        if not (self.session and self.seg_type == "work" and self.seg_start):
            raise RuntimeError("No active work segment to complete early")
        return self.end_segment(completed=True, early_completion=True)

    def stop_session(self) -> SessionStopped:
        """End the session. Returns summary."""
        if not self.session:
            raise RuntimeError("No active session")

        quest_title = self.session["quest_title"]
        actual = self.session.get("actual_pomos", 0)

        self._repo.end_session(self.session["id"])

        # Reset all state
        self.session = None
        self.seg_type = "work"
        self.seg_start = None
        self.is_resume = False
        self.lap_history = {}
        self.charge = ""
        self.deed_lap = -1
        self.last_early = False
        self.streak = 0
        self.streak_peak = 0
        self.momentum = 0
        self.total_interruptions = 0
        self.session_focus_secs = 0.0
        self.last_interruption_reason = ""

        return SessionStopped(
            quest_title=quest_title,
            actual_pomos=actual,
        )

    def abandon_mid_segment(self) -> None:
        """Record current in-progress segment as incomplete (for quit/abandon).
        Does NOT end the session — caller should call stop_session() after.
        """
        if not (self.session and self.seg_start):
            return

        now = datetime.now(timezone.utc)
        interruptions = self.seg_interruptions
        if self.seg_type == "work":
            interruptions += 1

        stored_type = self.seg_type
        if self.seg_type == "extended_break":
            stored_type = "short_break"

        self._repo.add_segment(
            session_id=self.session["id"],
            seg_type=stored_type,
            lap=self.lap,
            cycle=0,
            completed=False,
            interruptions=interruptions,
            started_at=self.seg_start.isoformat(),
            ended_at=now.isoformat(),
        )
        self.session = self._repo.get_session(self.session["id"])
