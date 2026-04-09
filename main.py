from __future__ import annotations

import random

from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Static

from config import POMO_CONFIG, VALID_SOURCES
from quest_store import load_quests, add_quest, update_quest, delete_quest, toggle_frog
from pomo_store import (
    start_session as start_pomo_session,
    add_segment,
    update_segment_deed,
    end_session as end_pomo_session,
    get_session,
)
from pomo_queries import (
    get_today_receipt,
    get_all_pomo_counts_today,
    get_quest_pomo_total,
    get_quest_lap_history,
)
from utils import format_duration, fantasy_date, get_elapsed
from renderers import POMO_RPG_HEADLINERS
from modals import (
    AddQuestModal, ConfirmModal,
    DashboardModal, DailyReceiptModal,
)
from pomo_panel import PomodoroPanel
from quest_panel import RosterPanel
from chronicle_panel import ChroniclePanel
from trophy_panel import TrophyPanel

# ── App ───────────────────────────────────────────────────────────────────────

class QuestLogApp(App):
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("a", "add_quest",    "Add",     show=True),
        Binding("s", "start_quest",  "Start",   show=True),
        Binding("b", "block_quest",  "Block",   show=True),
        Binding("d", "done_quest",   "Done",    show=True),
        Binding("x", "delete_quest", "Delete",  show=True),
        Binding("o", "dashboard",    "Overview", show=True),
        Binding("p", "receipt",      "Receipt", show=True),
        Binding("t", "pomo",         "Pomo",    show=True),
        Binding("f", "toggle_frog",  "Frog",    show=True),
        Binding("r", "refresh",      "Refresh", show=True),
        Binding("q", "quit",         "Quit",    show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        with Horizontal(id="main-area"):
            yield RosterPanel(id="roster")
            yield ChroniclePanel(id="chronicle")
            yield TrophyPanel(id="trophy")
        yield Static(id="stats")
        yield Footer()

    def on_mount(self) -> None:
        self._pomo_session: dict | None = None
        self._pomo_seg_type: str = "work"
        self._pomo_lap: int = 0
        self._pomo_seg_start: datetime | None = None
        self._pomo_seg_interruptions: int = 0
        self._pomo_timer_handle = None
        self._pomo_panel: PomodoroPanel | None = None
        self._pomo_lap_history: dict = {}
        self._pomo_is_resume: bool = False
        self._pomo_break_due_at: datetime | None = None
        self._pomo_nudge_handle = None
        # Charge & deed gate state
        self._pomo_charge: str = ""
        self._pomo_deed_lap: int = -1
        self._pomo_deed_seg_started: str = ""
        self._pomo_last_early: bool = False
        # War Room new state
        self._pomo_streak: int = 0
        self._pomo_streak_peak: int = 0
        self._pomo_momentum: int = 0
        self._pomo_total_interruptions: int = 0
        self._pomo_session_focus_secs: float = 0.0
        self._pomo_last_interruption_reason: str = ""
        self._pomo_headliner: str = ""
        self._refresh_all()
        self.query_one(RosterPanel).focus()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        quests = load_quests()
        pomo_counts = get_all_pomo_counts_today()
        self.query_one(RosterPanel).refresh_quests(quests, pomo_counts)
        self.query_one(ChroniclePanel).refresh_data()
        self.query_one(TrophyPanel).refresh_data()
        self._update_header()
        if self._pomo_session:
            self._update_pomo_status()
        else:
            self._update_stats(quests)

    def _update_header(self) -> None:
        self.query_one("#header", Static).update(
            f"[bold #bf40ff]✧[/bold #bf40ff]  "
            f"[bold #e0e0ff]S T A R F O R G E[/bold #e0e0ff]"
            f"  [bold #bf40ff]✧[/bold #bf40ff]\n"
            f"[dim #8888cc]⟡  {fantasy_date()}  ⟡[/dim #8888cc]"
        )

    def _update_stats(self, quests: list[dict]) -> None:
        total      = len(quests)
        active     = sum(1 for q in quests if q["status"] == "active")
        blocked    = sum(1 for q in quests if q["status"] == "blocked")
        done       = sum(1 for q in quests if q["status"] == "done")
        total_secs = sum(get_elapsed(q) or 0 for q in quests if q.get("started_at"))
        receipt_n  = len(get_today_receipt())
        self.query_one("#stats", Static).update(
            f"[dim]⚔ Total [bold white]{total}[/bold white]"
            f"   🔥 [yellow]{active}[/yellow]"
            f"   🧱 [red]{blocked}[/red]"
            f"   🏆 [green]{done}[/green]"
            f"   ⏱ [bold white]{format_duration(total_secs)}[/bold white] logged"
            f"   |   📋 [bold white]{receipt_n}[/bold white] 🍅 today"
            f"  [bold cyan]\\[p] receipt[/bold cyan][/dim]"
        )

    def _selected_quest(self) -> tuple[None, dict | None]:
        try:
            return None, self.query_one(RosterPanel).selected_quest()
        except Exception:
            return None, None

    # ── Pomodoro helpers ──────────────────────────────────────────────────────

    def _seg_duration(self) -> int:
        return {
            "work":           POMO_CONFIG["work_secs"],
            "short_break":    POMO_CONFIG["short_break_secs"],
            "extended_break": POMO_CONFIG["extended_break_secs"],
            "long_break":     POMO_CONFIG["long_break_secs"],
        }[self._pomo_seg_type]

    def _pomo_remaining(self) -> float:
        if self._pomo_seg_start is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self._pomo_seg_start).total_seconds()
        return max(0.0, self._seg_duration() - elapsed)

    def _update_pomo_status(self) -> None:
        if not self._pomo_session:
            return
        remaining = self._pomo_remaining()
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        seg_labels = {
            "work":           "🔨 Work",
            "short_break":    "☕ Break",
            "extended_break": "🌿 Extended",
            "long_break":     "🏖 Long Break",
        }
        seg_label  = seg_labels.get(self._pomo_seg_type, self._pomo_seg_type)
        actual  = self._pomo_session.get("actual_pomos", 0)
        title   = self._pomo_session["quest_title"]
        resume_badge = "⏯  " if self._pomo_is_resume else ""
        streak_str = f"  🔥×{self._pomo_streak}" if self._pomo_streak >= 2 else ""
        receipt_n = len(get_today_receipt())
        self.query_one("#stats", Static).update(
            f"[bold cyan]{resume_badge}🍅 {title}[/bold cyan]"
            f"  {seg_label}"
            f"  [bold white]{mins:02d}:{secs:02d}[/bold white]"
            f"  🍅 [green]{actual}[/green]{streak_str}"
            f"  [dim]|   📋 [bold white]{receipt_n}[/bold white] 🍅 today"
            f"  [bold cyan]\\[p] receipt[/bold cyan][/dim]"
            f"  [dim][t] stop[/dim]"
        )

    def _start_segment(self, seg_type: str) -> None:
        self._clear_break_nudge()
        self._pomo_seg_type = seg_type
        self._pomo_seg_start = datetime.now(timezone.utc)
        self._pomo_seg_interruptions = 0
        self._pomo_timer_handle = self.set_interval(1.0, self._pomo_tick)
        if self._pomo_panel is not None:
            self._pomo_panel.show_timer_mode(
                seg_type=seg_type,
                remaining=float(self._seg_duration()),
                total=self._seg_duration(),
                lap=self._pomo_lap,
                session=self._pomo_session,
                lap_history=self._pomo_lap_history,
                is_resume=self._pomo_is_resume,
            )
        self._update_pomo_status()

    def _pomo_tick(self) -> None:
        if self._pomo_remaining() <= 0:
            self._end_segment(completed=True)
        else:
            if self._pomo_panel is not None:
                self._pomo_panel.refresh_display(
                    seg_type=self._pomo_seg_type,
                    remaining=self._pomo_remaining(),
                    total=self._seg_duration(),
                    lap=self._pomo_lap,
                    session=self._pomo_session,
                    lap_history=self._pomo_lap_history,
                    is_resume=self._pomo_is_resume,
                )
            self._update_pomo_status()

    def _end_segment(self, completed: bool,
                     interruption_reason: str = "",
                     break_size: str | None = None,
                     early_completion: bool = False) -> None:
        if self._pomo_timer_handle:
            self._pomo_timer_handle.stop()
            self._pomo_timer_handle = None

        now = datetime.now(timezone.utc)
        seg_secs = (now - self._pomo_seg_start).total_seconds() if self._pomo_seg_start else 0.0

        if self._pomo_seg_type == "work":
            self._pomo_lap_history[self._pomo_lap] = "done" if completed else "broken"

        # Determine break_size for storage (extended_break is stored as short_break + break_size)
        stored_type = self._pomo_seg_type
        if self._pomo_seg_type == "extended_break":
            stored_type = "short_break"
            break_size  = "extended"

        add_segment(
            session_id=self._pomo_session["id"],
            seg_type=stored_type,
            lap=self._pomo_lap,
            cycle=0,
            completed=completed,
            interruptions=self._pomo_seg_interruptions,
            started_at=self._pomo_seg_start.isoformat(),
            ended_at=now.isoformat(),
            charge=self._pomo_charge if self._pomo_seg_type == "work" else None,
            break_size=break_size,
            interruption_reason=interruption_reason or None,
            early_completion=early_completion,
        )
        self._pomo_session = get_session(self._pomo_session["id"])

        if not completed:
            return  # caller handles cleanup

        if self._pomo_seg_type == "work":
            # Track focus time
            self._pomo_session_focus_secs += seg_secs
            self._pomo_last_early = early_completion
            # Streak & momentum
            self._pomo_streak   += 1
            self._pomo_momentum += 1
            if self._pomo_streak > self._pomo_streak_peak:
                self._pomo_streak_peak = self._pomo_streak
            # Store deed-gate context
            self._pomo_deed_lap         = self._pomo_lap
            self._pomo_deed_seg_started = self._pomo_seg_start.isoformat()
            self._pomo_lap += 1

            self.bell()
            if self._pomo_panel is not None:
                self._pomo_panel.show_deed_mode()
            else:
                self._open_pomo_panel(initial_mode="deed")
        else:
            # Break finished — reset streak/momentum for long break
            if self._pomo_seg_type == "long_break":
                self._pomo_streak   = 0
                self._pomo_momentum = 0
            self.bell()
            self.notify("☕ Rest complete — back to the fray!", title="Break ended", timeout=4)
            self.query_one(TrophyPanel).refresh_data()
            if self._pomo_panel is not None:
                self._pomo_panel.show_charge_mode()
            else:
                self._open_pomo_panel(initial_mode="charge")

    def _handle_deed_submit(self, deed: str, forge_type: str | None = None) -> None:
        """Called when user submits deed text in the deed gate."""
        if not (self._pomo_session and self._pomo_deed_lap >= 0):
            return

        update_segment_deed(self._pomo_session["id"], self._pomo_deed_lap, deed,
                            forge_type=forge_type)
        self._pomo_session = get_session(self._pomo_session["id"])

        actual   = self._pomo_session.get("actual_pomos", 0)
        if forge_type == "hollow":
            self.notify(
                f"💀 Hollow forge logged. Onwards, warrior.",
                title="Hollow forge", timeout=5,
            )
        elif forge_type == "berserker":
            self.notify(
                f"⚡ BERSERKER! Pomo {actual} forged in fury! Streak: {self._pomo_streak} 🔥",
                title="Berserker forge", timeout=5,
            )
        else:
            self.notify(
                f"🍅 Pomo {actual} complete! Streak: {self._pomo_streak} 🔥",
                title="Focus session finished", timeout=5,
            )

        self._pomo_deed_lap = -1
        self._schedule_break_nudge()

        # Refresh trophies — pomo + deed now recorded
        self.query_one(TrophyPanel).refresh_data()

        # Show break choice gate
        if self._pomo_panel is not None:
            self._pomo_panel.show_break_choice_mode()
        else:
            self._open_pomo_panel(initial_mode="break_choice")

    def _handle_break_choice(self, choice: str) -> None:
        """Called when user picks a break option from the break choice gate."""
        self._clear_break_nudge()

        if choice == "end":
            self._show_summary_then_stop()
            return
        if choice == "skip":
            self._show_charge_gate()
            return

        # Map choice → seg_type
        break_map = {
            "short":    "short_break",
            "extended": "extended_break",
            "long":     "long_break",
        }
        seg_type = break_map.get(choice, "short_break")

        # Long break resets streak + momentum
        if choice == "long":
            self._pomo_streak   = 0
            self._pomo_momentum = 0

        self._start_segment(seg_type)

    def _show_charge_gate(self) -> None:
        if self._pomo_panel is not None:
            self._pomo_panel.show_charge_mode()
        else:
            self._open_pomo_panel(initial_mode="charge")

    def _handle_charge_submit(self, charge: str) -> None:
        self._pomo_charge = charge
        self._start_segment("work")

    def _handle_panel_transition(self, choice: str) -> None:
        # Legacy path — keep for any remaining transition flows
        if choice in ("work", "charge"):
            self._show_charge_gate()
        elif choice.startswith("break:"):
            self._start_segment(choice.split(":")[1])

    def _initiate_interruption(self) -> None:
        """Mid-work interruption — stop timer, ask for reason."""
        if not (self._pomo_session and self._pomo_seg_type == "work"):
            return
        if self._pomo_timer_handle:
            self._pomo_timer_handle.stop()
            self._pomo_timer_handle = None
        if self._pomo_panel is not None:
            self._pomo_panel.show_interrupt_mode()

    def _complete_early(self) -> None:
        """Swiftblade — complete current pomo ahead of schedule."""
        if not (self._pomo_session and self._pomo_seg_type == "work"
                and self._pomo_timer_handle):
            return
        self._end_segment(completed=True, early_completion=True)

    def _handle_interruption_reason(self, reason: str) -> None:
        """User submitted (or skipped) an interruption reason — log it, resume session."""
        self._pomo_last_interruption_reason = reason
        self._pomo_total_interruptions     += 1
        self._pomo_streak   = 0
        self._pomo_momentum = 0
        now = datetime.now(timezone.utc)
        self._pomo_seg_interruptions += 1
        self._pomo_lap_history[self._pomo_lap] = "broken"
        add_segment(
            session_id=self._pomo_session["id"],
            seg_type="work",
            lap=self._pomo_lap,
            cycle=0,
            completed=False,
            interruptions=self._pomo_seg_interruptions,
            started_at=self._pomo_seg_start.isoformat(),
            ended_at=now.isoformat(),
            charge=self._pomo_charge or None,
            interruption_reason=reason or None,
        )
        self._pomo_session = get_session(self._pomo_session["id"])

        # Update streak_peak
        sess = self._pomo_session
        if sess and self._pomo_streak_peak > sess.get("streak_peak", 0):
            sess["streak_peak"] = self._pomo_streak_peak

        # Advance lap and resume — go back to charge gate for next pomo
        self._pomo_lap += 1
        self.notify("⚠ Interrupted — regroup and charge again!", timeout=3)
        self.query_one(TrophyPanel).refresh_data()
        if self._pomo_panel is not None:
            self._pomo_panel.show_charge_mode()
        else:
            self._open_pomo_panel(initial_mode="charge")

    def _show_summary_then_stop(self) -> None:
        if self._pomo_panel is not None:
            self._pomo_panel.dismiss()
        self._stop_pomo()
        self._refresh_all()

    def _schedule_break_nudge(self) -> None:
        """Fire a break reminder every 5 min while no segment is running."""
        self._clear_break_nudge()
        self._pomo_break_due_at = datetime.now(timezone.utc)
        self._pomo_nudge_handle = self.set_interval(5 * 60, self._break_nudge)

    def _clear_break_nudge(self) -> None:
        if self._pomo_nudge_handle:
            self._pomo_nudge_handle.stop()
            self._pomo_nudge_handle = None
        self._pomo_break_due_at = None

    def _break_nudge(self) -> None:
        if not self._pomo_break_due_at:
            self._clear_break_nudge()
            return
        elapsed_mins = int(
            (datetime.now(timezone.utc) - self._pomo_break_due_at).total_seconds() // 60
        )
        self.notify(
            f"🔔 You finished a 🍅 {elapsed_mins} min ago — take your break!",
            title="Break reminder",
            timeout=8,
        )

    def _stop_pomo(self, quiet: bool = False) -> None:
        if self._pomo_timer_handle:
            self._pomo_timer_handle.stop()
            self._pomo_timer_handle = None
        self._clear_break_nudge()
        if self._pomo_session:
            end_pomo_session(self._pomo_session["id"])
            title  = self._pomo_session["quest_title"]
            actual = self._pomo_session.get("actual_pomos", 0)
            self._pomo_session              = None
            self._pomo_seg_type             = "work"
            self._pomo_seg_start            = None
            self._pomo_is_resume            = False
            self._pomo_lap_history          = {}
            self._pomo_charge               = ""
            self._pomo_deed_lap             = -1
            self._pomo_last_early           = False
            self._pomo_streak               = 0
            self._pomo_streak_peak          = 0
            self._pomo_momentum             = 0
            self._pomo_total_interruptions  = 0
            self._pomo_session_focus_secs   = 0.0
            self._pomo_last_interruption_reason = ""
            if not quiet:
                self._refresh_all()
                self.notify(f"[cyan]🍅 Pomodoro stopped:[/cyan] {title} — {actual} 🍅 completed", timeout=3)

    def _open_pomo_panel(self, initial_mode: str = "timer",
                         initial_transition: dict | None = None) -> None:
        panel = PomodoroPanel(initial_mode=initial_mode, initial_transition=initial_transition)
        self._pomo_panel = panel
        def on_dismiss(_: object) -> None:
            self._pomo_panel = None
        self.push_screen(panel, callback=on_dismiss)

    def _stop_pomo_and_close_panel(self) -> None:
        # Mid-work stop: enter interruption reason flow
        if (self._pomo_session and self._pomo_seg_start and
                self._pomo_timer_handle and self._pomo_seg_type == "work"):
            self._initiate_interruption()
            return
        # Mid-break stop: silent clean stop
        if self._pomo_session and self._pomo_seg_start and self._pomo_timer_handle:
            self._pomo_timer_handle.stop()
            self._pomo_timer_handle = None
            now = datetime.now(timezone.utc)
            add_segment(
                session_id=self._pomo_session["id"],
                seg_type=self._pomo_seg_type,
                lap=self._pomo_lap,
                cycle=0,
                completed=False,
                interruptions=self._pomo_seg_interruptions,
                started_at=self._pomo_seg_start.isoformat(),
                ended_at=now.isoformat(),
            )
            self._pomo_session = get_session(self._pomo_session["id"])
        if self._pomo_panel is not None:
            self._pomo_panel.dismiss()
        self._stop_pomo()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_dashboard(self) -> None:
        self.push_screen(DashboardModal())

    def action_receipt(self) -> None:
        self.push_screen(DailyReceiptModal())

    def action_quit(self) -> None:
        if self._pomo_session:
            if self._pomo_timer_handle:
                self._pomo_timer_handle.stop()
                self._pomo_timer_handle = None
            self._clear_break_nudge()
            if self._pomo_seg_start:
                if self._pomo_seg_type == "work":
                    self._pomo_seg_interruptions += 1
                add_segment(
                    session_id=self._pomo_session["id"],
                    seg_type=self._pomo_seg_type,
                    lap=self._pomo_lap,
                    cycle=0,
                    completed=False,
                    interruptions=self._pomo_seg_interruptions,
                    started_at=self._pomo_seg_start.isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                )
            end_pomo_session(self._pomo_session["id"])
            self._pomo_session = None
        self.exit()

    def action_refresh(self) -> None:
        self._refresh_all()
        self.notify("🔄 Adventures refreshed", timeout=1.5)

    def action_add_quest(self) -> None:
        def on_done(title: str | None) -> None:
            if title:
                add_quest(title)
                self._refresh_all()
                self.notify(f"[cyan]📜 Quest added:[/cyan] {title}", timeout=2)

        self.push_screen(AddQuestModal(), callback=on_done)

    def action_start_quest(self) -> None:
        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return
        if quest["status"] not in VALID_SOURCES["start"]:
            self.notify("Can only start quests from the Log or Blocker", severity="warning", timeout=2)
            return
        update_quest(quest["id"], "active")
        self._refresh_all()
        self.notify(f"[yellow]🔥 Started:[/yellow] {quest['title']}", timeout=2)

    def action_block_quest(self) -> None:
        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return
        if quest["status"] not in VALID_SOURCES["block"]:
            self.notify("Can only block quests from Log or In Battle", severity="warning", timeout=2)
            return
        update_quest(quest["id"], "blocked")
        self._refresh_all()
        self.notify(f"[red]🧱 Blocked:[/red] {quest['title']}", timeout=2)

    def action_done_quest(self) -> None:
        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return
        if quest["status"] not in VALID_SOURCES["done"]:
            self.notify("Can only complete quests In Battle or at the Blocker", severity="warning", timeout=2)
            return
        update_quest(quest["id"], "done")
        self._refresh_all()
        self.notify(f"[green]🏆 Completed:[/green] {quest['title']}", timeout=2)

    def action_delete_quest(self) -> None:
        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                delete_quest(quest["id"])
                self._refresh_all()
                self.notify(f"[red]🗑 Erased:[/red] {quest['title']}", timeout=2)

        self.push_screen(ConfirmModal(quest["title"]), callback=on_confirm)

    def action_toggle_frog(self) -> None:
        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return
        updated = toggle_frog(quest["id"])
        if updated and updated.get("frog"):
            self.notify(f"[green]🐸 Marked as frog:[/green] {quest['title']}", timeout=2)
        else:
            self.notify(f"[dim]🐸 Frog removed:[/dim] {quest['title']}", timeout=2)
        self._refresh_all()

    def action_pomo(self) -> None:
        if self._pomo_session:
            if self._pomo_panel is not None:
                self._pomo_panel.dismiss()   # toggle: hide panel, keep running
            else:
                # Re-open panel in correct mode based on whether a timer is active
                if self._pomo_timer_handle:
                    self._open_pomo_panel()   # timer running → show timer
                else:
                    self._open_pomo_panel(initial_mode="charge")  # between segments
            return

        _, quest = self._selected_quest()
        if quest is None:
            self.notify("No quest selected", severity="warning", timeout=2)
            return
        if quest["status"] != "active":
            self.notify("Pomodoros can only be started for active quests", severity="warning", timeout=2)
            return

        prior_pomos = get_quest_pomo_total(quest["id"])
        self._pomo_lap_history = get_quest_lap_history(quest["id"])
        self._pomo_lap         = prior_pomos
        self._pomo_is_resume   = prior_pomos > 0
        self._pomo_headliner   = random.choice(POMO_RPG_HEADLINERS)
        self._pomo_session     = start_pomo_session(quest["id"], quest["title"])
        self._refresh_all()
        badge = "⏯  Resumed" if self._pomo_is_resume else "🍅  Forging begins"
        self.notify(f"[cyan]{badge}:[/cyan] {quest['title']}", timeout=2)
        self._open_pomo_panel(initial_mode="charge")


if __name__ == "__main__":
    QuestLogApp().run()
