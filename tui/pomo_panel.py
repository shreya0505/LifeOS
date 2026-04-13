from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Vertical

from rich.align import Align
from rich.table import Table
from rich.text import Text

from core.config import POMO_CONFIG
from core.pomo_queries import get_quest_segment_journey
from tui.renderers import POMO_WAR_CRIES, render_block_clock, render_health_bar, render_momentum_bar
from core.utils import format_duration
from core.storage.json_backend import JsonPomoRepo
from pathlib import Path

_pomo_repo = JsonPomoRepo(Path(__file__).parent.parent / "data" / "tui" / "pomodoros.json")


class PomodoroPanel(Screen):
    """The War Room — immersive focus panel with block clock, health bar,
    momentum, per-task journey track, break-choice gate,
    interruption log, and session summary."""

    # priority=True ensures these fire even when an Input widget has focus.
    # Single-char bindings (c, i, 1-4) intentionally omit priority so they
    # type normally into charge/deed inputs; they only bind in non-input modes.
    BINDINGS = [
        Binding("alt+x",  "stop_pomo",       "Abandon",     show=True,  priority=True),
        Binding("alt+e",  "end_session",     "End Session", show=False, priority=True),
        Binding("alt+h",  "forge_hollow",    "Hollow",      show=False, priority=True),
        Binding("alt+b",  "forge_berserker", "Berserker",   show=False, priority=True),
        Binding("c",      "complete_early",  "Swift",       show=False),
        Binding("enter",  "primary_opt",     "Continue",    show=False),
        Binding("1",      "break_opt_1",     "Short",       show=False),
        Binding("2",      "break_opt_2",     "Extended",    show=False),
        Binding("3",      "break_opt_3",     "Long",        show=False),
        Binding("4",      "break_opt_4",     "Skip/End",    show=False),
        Binding("i",      "interrupt",       "Interrupt",   show=False),
    ]

    _SEG_COLOR = {
        "work":           "red",
        "short_break":    "cyan",
        "extended_break": "cyan",
        "long_break":     "teal",
    }
    _SEG_NAME = {
        "work":           "F O C U S",
        "short_break":    "S H O R T   B R E A K",
        "extended_break": "E X T E N D E D   B R E A K",
        "long_break":     "L O N G   B R E A K",
    }
    _SEG_ICON = {
        "work":           "🔨",
        "short_break":    "☕",
        "extended_break": "🌿",
        "long_break":     "🏖",
    }

    @staticmethod
    def _streak_label(streak: int) -> str:
        """Return a milestone label for the current streak."""
        if streak <= 0:
            return ""
        if streak >= 7:
            return "⚔  DEEP WORK"
        if streak >= 5:
            return f"🔥🔥🔥 {streak}  Unstoppable"
        if streak >= 3:
            return f"🔥🔥 {streak}  Hot Streak"
        return f"🔥 {streak}"

    def __init__(self, initial_mode: str = "timer",
                 initial_transition: dict | None = None) -> None:
        super().__init__()
        self._mode = initial_mode
        self._transition: dict | None = initial_transition
        self._last_display_kwargs: dict = {}
        self._forge_type: str | None = None  # None = normal, "hollow", "berserker"

    def compose(self) -> ComposeResult:
        with Vertical(id="pomo-screen-root"):
            yield Static(id="pomo-header")
            with Vertical(id="pomo-left-col"):
                # Timer zone — bordered box; charge intent appears as border_title
                with Vertical(id="pomo-timer-zone"):
                    yield Static(id="pomo-seg-label")
                    yield Static(id="pomo-block-clock")
                    yield Static(id="pomo-health-bar")
                    yield Static(id="pomo-momentum-bar")
                # Charge display (shown in deed mode for accountability mirror)
                with Vertical(id="pomo-charge-display-zone"):
                    yield Static("⚔  Y O U R  C H A R G E", id="pomo-charge-display-header")
                    yield Static(id="pomo-charge-display-text")
                # Charge gate (before each work segment)
                with Vertical(id="pomo-charge-zone"):
                    yield Static("⚔  Declare your intent", id="pomo-charge-zone-header")
                    yield Static(
                        "[bold]What will you have conquered when this 🍅 ends?[/bold]",
                        id="pomo-charge-prompt",
                    )
                    yield Static(
                        "[dim](name the foe — a bug to slay, a path to forge, a scroll to draft)[/dim]",
                        id="pomo-charge-hint",
                    )
                    yield Static(id="pomo-war-cry")
                    yield Input(id="pomo-charge-input", placeholder="")
                # Deed gate (after each work segment)
                with Vertical(id="pomo-deed-zone"):
                    yield Static(id="pomo-deed-work-done")
                    yield Static("🔥 VICTORY", id="pomo-victory-flash")
                    yield Static(
                        "[bold]⚔ What spoils did you claim, warrior?[/bold]",
                        id="pomo-deed-prompt",
                    )
                    yield Static(
                        "[dim](a beast felled, a dungeon cleared, a rune deciphered)[/dim]",
                        id="pomo-deed-hint",
                    )
                    yield Input(id="pomo-deed-input", placeholder="")
                    yield Static(id="pomo-forge-flash")
                    yield Static(id="pomo-forge-type-selector")
                # Break choice gate (after deed is recorded)
                with Vertical(id="pomo-break-choice-zone"):
                    yield Static(id="pomo-break-choice-header")
                    yield Static(id="pomo-break-choice-options")
                # Interruption reason gate
                with Vertical(id="pomo-interrupt-zone"):
                    yield Static("⚠  What felled you, adventurer?", id="pomo-interrupt-header")
                    yield Static(id="pomo-interrupt-options")
                # Session summary
                with Vertical(id="pomo-summary-zone"):
                    yield Static(id="pomo-summary-content")
                # Per-task journey track
                yield Static(id="pomo-journey")
        yield Static(id="pomo-footer")

    def on_mount(self) -> None:
        app = self.app
        if self._mode == "charge":
            self._enter_charge_mode()
        elif self._mode == "deed":
            self._enter_deed_mode()
        elif self._mode == "break_choice":
            self._enter_break_choice_mode()
        elif self._mode == "transition" and self._transition:
            self._enter_transition_mode(self._transition)
        elif app._pomo_session and app._pomo_seg_start:
            self._enter_timer_mode()
            self.refresh_display(
                seg_type=app._pomo_seg_type,
                remaining=app._pomo_remaining(),
                total=app._seg_duration(),
                lap=app._pomo_lap,
                session=app._pomo_session,
                lap_history=app._pomo_lap_history,
                is_resume=app._pomo_is_resume,
            )

    # ── Mode entry helpers ────────────────────────────────────────────────────

    def _all_zones(self) -> list[Static | Widget]:
        return [
            self.query_one("#pomo-timer-zone"),       # hides seg-label/clock/bars as a unit
            self.query_one("#pomo-charge-display-zone"),
            self.query_one("#pomo-charge-zone"),
            self.query_one("#pomo-deed-zone"),
            self.query_one("#pomo-break-choice-zone"),
            self.query_one("#pomo-interrupt-zone"),
            self.query_one("#pomo-summary-zone"),
            self.query_one("#pomo-journey"),
        ]

    def _hide_all_zones(self) -> None:
        for z in self._all_zones():
            z.display = False

    def _enter_timer_mode(self) -> None:
        self._mode = "timer"
        self._transition = None
        self._hide_all_zones()
        self.query_one("#pomo-timer-zone").display = True
        self.query_one("#pomo-journey").display    = True
        # Explicitly clear focus so hidden Input widgets don't swallow key bindings
        self.set_focus(None)

    def _enter_charge_mode(self) -> None:
        self._mode = "charge"
        self._hide_all_zones()
        self.query_one("#pomo-charge-zone").display = True
        cry = random.choice(POMO_WAR_CRIES)
        # Box frame around the war cry for visual presence
        bar = "─" * (len(cry) + 2)
        boxed_cry = f"[dim]┌{bar}┐\n│ {cry} │\n└{bar}┘[/dim]"
        self.query_one("#pomo-war-cry", Static).update(boxed_cry)
        session = self.app._pomo_session
        if session:
            actual    = session.get("actual_pomos", 0)
            title     = session.get("quest_title", "")
            headliner = getattr(self.app, "_pomo_headliner", "⚔  Into the Fray")
            self.query_one("#pomo-header", Static).update(
                f"[dim]{headliner}  ·  {title}  🍅 {actual}[/dim]\n"
                f"[bold]What will you forge this pomo?[/bold]"
            )
        self.query_one("#pomo-footer", Static).update(
            "[dim]\\[enter] charge forth    \\[alt+e] end quest    \\[alt+x] abandon quest[/dim]"
        )
        charge_input = self.query_one("#pomo-charge-input", Input)
        charge_input.value = ""
        charge_input.placeholder = cry  # War cry echoes as dim placeholder
        charge_input.focus()

    def _populate_deed_content(self) -> None:
        """Pre-populate all deed mode widgets so the transition is instant."""
        self.query_one("#pomo-charge-display-header", Static).update("[dim]⚔  Your battle cry was:[/dim]")
        charge_text = getattr(self.app, "_pomo_charge", "") or ""
        self.query_one("#pomo-charge-display-text", Static).update(
            f"[dim]│[/dim] [italic]{charge_text}[/italic]" if charge_text else ""
        )
        session = self.app._pomo_session
        if session:
            actual = session.get("actual_pomos", 0)
            early = getattr(self.app, "_pomo_last_early", False)
            if early:
                self.query_one("#pomo-deed-work-done", Static).update(
                    f"[bold yellow]⚡  Pomo {actual} — Swiftblade finish![/bold yellow]"
                )
            else:
                self.query_one("#pomo-deed-work-done", Static).update(
                    f"[bold green]🍅  Pomo {actual} conquered![/bold green]"
                )
        self._update_forge_selector()
        self.query_one("#pomo-forge-flash").display = False
        self.query_one("#pomo-footer", Static).update(
            "[dim](inscribe your deed to unlock rest)  ·  \\[alt+h] 💀 hollow  \\[alt+b] ⚡ berserker[/dim]"
        )
        self.query_one("#pomo-deed-input", Input).value = ""

    def _enter_deed_mode(self) -> None:
        self._mode = "deed"
        self._forge_type = None  # reset for each new deed
        self._hide_all_zones()
        self._populate_deed_content()
        self.query_one("#pomo-deed-zone").display         = True
        self.query_one("#pomo-journey").display           = True
        self.query_one("#pomo-victory-flash").display     = False
        self.query_one("#pomo-charge-display-zone").display = True
        self.query_one("#pomo-deed-input", Input).focus()

    def _enter_break_choice_mode(self) -> None:
        self._mode = "break_choice"
        self._hide_all_zones()
        self.query_one("#pomo-break-choice-zone").display = True
        self.query_one("#pomo-journey").display           = True
        short_m = POMO_CONFIG["short_break_secs"] // 60
        ext_m   = POMO_CONFIG["extended_break_secs"] // 60
        long_m  = POMO_CONFIG["long_break_secs"] // 60
        self.query_one("#pomo-break-choice-header", Static).update(
            "[bold]⛺  Choose your respite, warrior[/bold]"
        )
        table = Table(box=None, padding=(0, 2, 0, 0), show_header=False)
        table.add_column(justify="center", no_wrap=True)  # key
        table.add_column(justify="left",   no_wrap=True)  # label
        table.add_column(justify="right",  no_wrap=True)  # time
        table.add_row("[bold cyan]\\[1][/bold cyan]", "☕  Short rest",              f"{short_m}m")
        table.add_row("[bold cyan]\\[2][/bold cyan]", "🌿  Camp fire",               f"{ext_m}m")
        table.add_row("[bold cyan]\\[3][/bold cyan]", "🏖  Full rest [dim](resets streak)[/dim]", f"{long_m}m")
        table.add_row("[bold cyan]\\[4][/bold cyan]", "⚡  Press on — charge next",  "")
        table.add_row("[bold cyan]\\[alt+e][/bold cyan]", "End session",              "")
        self.query_one("#pomo-break-choice-options", Static).update(Align(table, align="center"))
        self.query_one("#pomo-footer", Static).update(
            "[dim]\\[1-4] choose respite   \\[alt+e] end quest[/dim]"
        )

    def _enter_interrupt_mode(self) -> None:
        self._mode = "interrupt"
        self._hide_all_zones()
        self.query_one("#pomo-interrupt-zone").display = True
        self.query_one("#pomo-interrupt-options", Static).update(
            "[bold red]\\[1][/bold red] 💭 Mind wandered     "
            "[bold red]\\[2][/bold red] ⛔ Path blocked\n\n"
            "[bold red]\\[3][/bold red] 🚨 Ambush (urgent)  "
            "[bold red]\\[4][/bold red] 🌀 Called away"
        )
        self.query_one("#pomo-footer", Static).update(
            "[dim]\\[1–4] name your foe    \\[alt+x] abandon quest[/dim]"
        )

    # ── Forge type selector helpers ──────────────────────────────────────────

    def _update_forge_selector(self) -> None:
        """Render the forge type selector with current selection highlighted."""
        ft = self._forge_type
        if ft == "hollow":
            text = (
                "[bold white on rgb(80,0,0)]  💀 Hollow  [/bold white on rgb(80,0,0)]"
                "    [dim]🍅 Normal[/dim]"
                "    [dim]⚡ Berserker[/dim]"
            )
        elif ft == "berserker":
            text = (
                "    [dim]💀 Hollow[/dim]"
                "    [dim]🍅 Normal[/dim]"
                "    [bold yellow on rgb(60,40,0)]  ⚡ Berserker  [/bold yellow on rgb(60,40,0)]"
            )
        else:
            text = (
                "    [dim]💀 Hollow[/dim]"
                "    [bold]🍅 Normal[/bold]"
                "    [dim]⚡ Berserker[/dim]"
            )
        self.query_one("#pomo-forge-type-selector", Static).update(
            f"\n{text}"
        )

    def _show_berserker_flash(self) -> None:
        """Brief visceral flash when berserker is activated."""
        flash = self.query_one("#pomo-forge-flash", Static)
        flash.display = True
        flash.update(
            "\n[bold red]⚡⚡⚡  B E R S E R K E R   M O D E  ⚡⚡⚡[/bold red]"
        )
        self.set_timer(0.8, self._clear_forge_flash)

    def _show_hollow_flash(self) -> None:
        """Dim acknowledgment when hollow is selected."""
        flash = self.query_one("#pomo-forge-flash", Static)
        flash.display = True
        flash.update("\n[dim]💀 Hollow forge...[/dim]")
        self.set_timer(0.8, self._clear_forge_flash)

    def _clear_forge_flash(self) -> None:
        try:
            self.query_one("#pomo-forge-flash", Static).display = False
        except Exception:
            pass

    def _enter_summary_mode(self) -> None:
        self._mode = "summary"
        self._hide_all_zones()
        self.query_one("#pomo-summary-zone").display = True
        app = self.app
        s   = app._pomo_session or {}
        actual      = s.get("actual_pomos", 0)
        streak_peak = s.get("streak_peak", app._pomo_streak_peak)
        interrupts  = s.get("total_interruptions", app._pomo_total_interruptions)
        focus_secs  = app._pomo_session_focus_secs
        title       = s.get("quest_title", "")
        focus_str   = format_duration(focus_secs) if focus_secs else "—"
        lines = Text()
        lines.append("┌─────────────────────────────────┐\n", "dim")
        lines.append("│  📊  Session Complete           │\n", "bold cyan")
        lines.append("├─────────────────────────────────┤\n", "dim")
        lines.append(f"\n  Quest          {title}\n")
        lines.append(f"  🍅 Forged       {actual}\n")
        lines.append(f"  🔥 Streak peak  {streak_peak}\n")
        lines.append(f"  ⏱ Focus        {focus_str}\n")
        lines.append(f"  ⚠ Interrupts  {interrupts}\n")
        if app._pomo_last_interruption_reason:
            lines.append(f"  └ last: {app._pomo_last_interruption_reason}\n", "dim")
        lines.append("\n└─────────────────────────────────┘\n", "dim")
        self.query_one("#pomo-summary-content", Static).update(lines)
        self.query_one("#pomo-footer", Static).update("[dim]ESC · close[/dim]")

    def _enter_transition_mode(self, t: dict) -> None:
        self._mode = "transition"
        self._transition = t
        self._hide_all_zones()
        self.query_one("#pomo-seg-label").display = True
        self._render_transition_content(t)

    # ── Public API called by the App ──────────────────────────────────────────

    def show_charge_mode(self) -> None:
        kw = self._last_display_kwargs
        if kw:
            self._update_header(kw)
        self._enter_charge_mode()

    def show_deed_mode(self) -> None:
        kw = self._last_display_kwargs
        if kw:
            self._update_header(kw)
        self._update_journey()
        # Enter deed mode fully before showing — no delayed content pop-in
        self._enter_deed_mode()

    def show_break_choice_mode(self) -> None:
        kw = self._last_display_kwargs
        if kw:
            self._update_header(kw)
        self._update_journey()
        self._enter_break_choice_mode()

    def show_interrupt_mode(self) -> None:
        self._enter_interrupt_mode()

    def show_summary_mode(self) -> None:
        self._enter_summary_mode()

    def show_transition(self, transition: dict, session: dict | None = None) -> None:
        if session is not None and self._last_display_kwargs:
            self._last_display_kwargs = {**self._last_display_kwargs, "session": session}
        kw = self._last_display_kwargs
        if kw:
            self._update_header(kw)
        self._update_journey()
        self._enter_transition_mode(transition)

    def show_timer_mode(self, **kwargs) -> None:
        self._enter_timer_mode()
        self.refresh_display(**kwargs)

    def refresh_display(self, seg_type: str, remaining: float,
                        total: int, lap: int, session: dict,
                        lap_history: dict | None = None,
                        is_resume: bool = False) -> None:
        if self._mode != "timer":
            return
        self._last_display_kwargs = dict(
            seg_type=seg_type, remaining=remaining, total=total,
            lap=lap, session=session,
            lap_history=lap_history if lap_history is not None else {},
            is_resume=is_resume,
        )
        actual = session.get("actual_pomos", 0)
        urgent = remaining < 60 and seg_type == "work"
        pulse  = bool(int(remaining) % 2)

        # Dynamic color based on remaining fraction (work only)
        if seg_type == "work":
            frac = remaining / total if total > 0 else 0.0
            if frac > 0.60:
                col = "green"
            elif frac > 0.25:
                col = "yellow"
            else:
                col = "red"
        else:
            col = "cyan"

        # Break clock counts UP (elapsed time — recovery, not countdown)
        # Work clock counts DOWN (remaining)
        display_secs = (total - remaining) if seg_type != "work" else remaining
        mins_disp = int(display_secs) // 60
        secs_disp = int(display_secs) % 60

        self._update_header(self._last_display_kwargs)
        self.query_one("#pomo-seg-label", Static).update(
            f"\n[bold {col}]{self._SEG_ICON[seg_type]}  {self._SEG_NAME[seg_type]}[/bold {col}]\n"
        )
        self.query_one("#pomo-block-clock", Static).update(
            render_block_clock(mins_disp, secs_disp, col, urgent=urgent, pulse=pulse)
        )

        is_break = seg_type != "work"
        self.query_one("#pomo-health-bar", Static).update(
            render_health_bar(remaining, total, is_break=is_break)
        )

        app = self.app
        self.query_one("#pomo-momentum-bar").display = seg_type == "work"
        if seg_type == "work":
            self.query_one("#pomo-momentum-bar", Static).update(
                render_momentum_bar(app._pomo_momentum)
            )

        # Charge intent is now always in the header — hide the separate zone
        self.query_one("#pomo-charge-display-zone").display = False

        self._update_journey()
        if seg_type == "work":
            headliner  = getattr(app, "_pomo_headliner", "⚔")
            streak     = getattr(app, "_pomo_streak", 0)
            focus_secs = getattr(app, "_pomo_session_focus_secs", 0.0)
            focus_m    = int(focus_secs // 60)
            streak_part = f"  {self._streak_label(streak)}" if streak >= 1 else ""
            focus_part  = f"  ⏱ {focus_m}m focused" if focus_m > 0 else ""
            self.query_one("#pomo-footer", Static).update(
                f"[dim]{headliner}  ·  🍅 {actual}{streak_part}{focus_part}"
                f"    ──    \\[c] swift finish    \\[i] interrupt    \\[alt+x] abandon    ESC · hide[/dim]"
            )
        else:
            self.query_one("#pomo-footer", Static).update(
                "[dim]\\[alt+x] abandon    ESC · hide[/dim]"
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _update_header(self, kw: dict) -> None:
        session   = kw.get("session", {})
        is_resume = kw.get("is_resume", False)
        actual    = session.get("actual_pomos", 0)
        title     = session.get("quest_title", "")
        app       = self.app
        streak    = getattr(app, "_pomo_streak", 0)
        headliner = getattr(app, "_pomo_headliner", "⚔  Into the Fray")
        resume_badge = "⏯  " if is_resume else ""
        streak_str = f"  {self._streak_label(streak)}" if streak >= 1 else ""
        berserker_badge = ""
        if session:
            for seg in session.get("segments", []):
                if seg.get("forge_type") == "berserker":
                    berserker_badge = "  [bold yellow]⚡ BERSERKER[/bold yellow]"
                    break
        self.query_one("#pomo-header", Static).update(
            f"[bold]{headliner}[/bold]"
            f"  [dim]·[/dim]  "
            f"[bold]{resume_badge}{title}[/bold]"
            f"  [dim]🍅 {actual}{streak_str}[/dim]"
            f"{berserker_badge}"
        )

    def _render_transition_content(self, t: dict) -> None:
        self.query_one("#pomo-seg-label", Static).update(
            f"\n[bold]{t['message']}[/bold]\n"
        )
        opts = [t["primary"][2]]
        if t.get("skip"):
            opts.append(t["skip"][2])
        opts.append("\\[x] abandon")
        self.query_one("#pomo-footer", Static).update(
            "    ".join(f"[bold cyan]{o}[/bold cyan]" for o in opts)
        )

    def _update_journey(self) -> None:
        kw = self._last_display_kwargs
        if not kw:
            return
        app      = self.app
        session  = kw.get("session") or app._pomo_session or {}
        seg_type = kw.get("seg_type", app._pomo_seg_type or "work")
        lap      = kw.get("lap", app._pomo_lap)
        hist     = kw.get("lap_history") or app._pomo_lap_history or {}
        in_trans = self._mode in ("deed", "break_choice")
        self.query_one("#pomo-journey", Static).update(
            self._build_journey(seg_type, lap, session, hist, in_transition=in_trans)
        )

    # Per-category interrupt glyph: (symbol, color)
    _INTERRUPT_STYLE: dict[str, tuple[str, str]] = {
        "distracted": ("💭", "yellow"),
        "blocked":    ("⛔", "dark_orange"),
        "emergency":  ("🚨", "red"),
        "personal":   ("🌀", "magenta"),
    }
    # Break type → (icon, color)
    _BREAK_GLYPH: dict[str, tuple[str, str]] = {
        "short_break":    ("☕", "green"),
        "extended_break": ("🌿", "cyan"),
        "long_break":     ("🏖", "cyan"),
    }

    def _build_journey(self, seg_type: str, lap: int, session: dict,
                       lap_history: dict, in_transition: bool = False) -> Text:
        """Per-task journey track — chronological trail of segment symbols.

        Work symbols:
          ✓          completed pomo (bright_green)
          [●]        live active pomo (red bold)
          ◑          broken, no reason (yellow dim)
          ◑d         broken: distracted (yellow)
          ◑b         broken: blocked (dark_orange)
          ◑!         broken: emergency (red)
          ◑p         broken: personal (magenta)

        Break symbols:
          ☕  🌿  🏖   completed short / extended / long break
          →          break abandoned early (not completed)
          [☕]/[🌿]/[🏖]  live break

        Transition symbols:
          ✓          just-forged pomo (in deed / break-choice transition)
          ?          pending break-choice decision
        """
        app      = self.app
        quest_id = (session or app._pomo_session or {}).get("quest_id")
        if not quest_id:
            return Text()

        all_sessions       = get_quest_segment_journey(_pomo_repo.load_all(), quest_id)
        current_session_id = (app._pomo_session or {}).get("id")

        # (seg_type, completed, is_live, interruption_reason, forge_type)
        trail: list[tuple[str, bool, bool, str, str]] = []

        for sess_entry in all_sessions:
            for seg in sess_entry["segments"]:
                is_cur_sess = sess_entry["session_id"] == current_session_id
                is_live = (
                    is_cur_sess
                    and not seg.get("completed")
                    and sess_entry["status"] == "running"
                )
                trail.append((
                    seg.get("type", "work"),
                    seg.get("completed", False),
                    is_live,
                    seg.get("interruption_reason") or "",
                    seg.get("forge_type") or "",
                ))

        if not trail:
            return Text()

        result = Text()
        result.append("JOURNEY  ", "bold dim")

        work_count = 0
        for stype, completed, is_live, ireason, forge_type in trail:
            if stype == "work":
                # Insert a thin separator every 4 completed work pomos
                if work_count > 0 and work_count % 4 == 0:
                    result.append(" · ", "dim")
                work_count += 1

                if is_live and in_transition:
                    # Just forged — show forge-type-aware glyph
                    if self._forge_type == "berserker":
                        result.append("⚡", "bold yellow")
                    elif self._forge_type == "hollow":
                        result.append("💀", "dim")
                    else:
                        result.append("✓", "bright_green bold")
                elif is_live:
                    result.append("[●]", "red bold")
                elif completed:
                    if forge_type == "berserker":
                        result.append("⚡", "bold yellow")
                    elif forge_type == "hollow":
                        result.append("💀", "dim")
                    else:
                        result.append("✓", "bright_green")
                else:
                    # Broken pomo — show category if available
                    if ireason in self._INTERRUPT_STYLE:
                        symbol, col = self._INTERRUPT_STYLE[ireason]
                        result.append(symbol, col)
                    else:
                        result.append("◑", "yellow dim")
            else:
                # Break segment
                icon, col = self._BREAK_GLYPH.get(stype, ("•", "white"))
                if is_live:
                    result.append(f"[{icon}]", col + " bold")
                elif completed:
                    result.append(icon, col)
                else:
                    result.append("→", "dim")

            result.append(" ")

        # Pending break-choice marker
        if self._mode == "break_choice":
            result.append("?", "yellow bold")

        return Text.assemble("\n", result, "\n")

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_hide_panel(self) -> None:
        if self._mode in ("charge", "deed"):
            return
        self.dismiss()

    def action_stop_pomo(self) -> None:
        self.app._stop_pomo_and_close_panel()

    def action_primary_opt(self) -> None:
        if self._mode == "charge":
            charge = self.query_one("#pomo-charge-input", Input).value.strip()
            if charge:
                self.app._handle_charge_submit(charge)
        elif self._mode == "transition" and self._transition:
            action_type, action_val, _ = self._transition["primary"]
            choice = f"break:{action_val}" if action_type == "break" else action_type
            self.app._handle_panel_transition(choice)
        elif self._mode == "deed":
            deed = self.query_one("#pomo-deed-input", Input).value.strip()
            if deed:
                self.app._handle_deed_submit(deed, forge_type=self._forge_type)

    def action_break_opt_1(self) -> None:
        if self._mode == "break_choice":
            self.app._handle_break_choice("short")
        elif self._mode == "interrupt":
            self.app._handle_interruption_reason("distracted")

    def action_break_opt_2(self) -> None:
        if self._mode == "break_choice":
            self.app._handle_break_choice("extended")
        elif self._mode == "interrupt":
            self.app._handle_interruption_reason("blocked")

    def action_break_opt_3(self) -> None:
        if self._mode == "break_choice":
            self.app._handle_break_choice("long")
        elif self._mode == "interrupt":
            self.app._handle_interruption_reason("emergency")

    def action_break_opt_4(self) -> None:
        if self._mode == "break_choice":
            self.app._handle_break_choice("skip")
        elif self._mode == "interrupt":
            self.app._handle_interruption_reason("personal")

    def action_end_session(self) -> None:
        if self._mode in ("break_choice", "charge"):
            self.app._handle_break_choice("end")

    def action_interrupt(self) -> None:
        if self._mode == "timer":
            self.app._initiate_interruption()

    def action_complete_early(self) -> None:
        if self._mode == "timer":
            self.app._complete_early()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pomo-deed-input":
            deed = event.input.value.strip()
            if deed:
                self.app._handle_deed_submit(deed, forge_type=self._forge_type)
        elif event.input.id == "pomo-charge-input":
            charge = event.input.value.strip()
            if charge:
                self.app._handle_charge_submit(charge)

    def action_forge_hollow(self) -> None:
        if self._mode != "deed":
            return
        # Toggle: if already hollow, revert to normal
        if self._forge_type == "hollow":
            self._forge_type = None
        else:
            self._forge_type = "hollow"
            self._show_hollow_flash()
        self._update_forge_selector()
        # Re-focus the deed input after key press
        self.query_one("#pomo-deed-input", Input).focus()

    def action_forge_berserker(self) -> None:
        if self._mode != "deed":
            return
        # Toggle: if already berserker, revert to normal
        if self._forge_type == "berserker":
            self._forge_type = None
        else:
            self._forge_type = "berserker"
            self._show_berserker_flash()
        self._update_forge_selector()
        # Re-focus the deed input after key press
        self.query_one("#pomo-deed-input", Input).focus()
