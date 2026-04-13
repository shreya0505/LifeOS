from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Rule, Static
from textual.containers import Vertical, Horizontal

from rich.console import Group as RichGroup
from rich.table import Table
from rich.text import Text

from core.config import POMO_CONFIG, USER_TZ
from core.pomo_queries import get_today_receipt
from core.metrics import compute_metrics, compute_pomo_metrics
from core.utils import fantasy_date
from core.storage.json_backend import JsonPomoRepo, JsonQuestRepo
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data" / "tui"
_pomo_repo = JsonPomoRepo(_DATA_DIR / "pomodoros.json")
_quest_repo = JsonQuestRepo(_DATA_DIR / "quests.json")


class AddQuestModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-body"):
            yield Label("📜  Inscribe Your Quest")
            yield Input(id="quest-input", placeholder="What must be done...")
            with Horizontal(id="modal-buttons"):
                yield Button("⚔  Add Quest", id="add", variant="primary")
                yield Button("✕  Cancel",    id="cancel")

    def on_mount(self) -> None:
        self.query_one("#quest-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        val = self.query_one("#quest-input", Input).value.strip()
        self.dismiss(val or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, quest_title: str) -> None:
        super().__init__()
        self._quest_title = quest_title

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-body"):
            yield Label("🗑  Erase from the Chronicles?")
            yield Static(f'"{self._quest_title}"', id="confirm-title")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, Destroy It", id="yes", variant="error")
                yield Button("Cancel",          id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class DashboardModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="dash-body"):
            yield Label("📊  Chronicle of Progress")
            yield Static(id="dash-metrics")
            yield Static("[dim]ESC · Return to the Chronicles[/dim]", id="dash-footer")

    def on_mount(self) -> None:
        quest_metrics = compute_metrics(_quest_repo.load_all())
        pomo_metrics  = compute_pomo_metrics(_pomo_repo.load_all())
        self.query_one("#dash-metrics", Static).update(
            self._build_table(quest_metrics, pomo_metrics)
        )

    def _build_table(self, quest_metrics: list[dict], pomo_metrics: list[dict]) -> RichGroup:
        COLORS = {"good": "green", "bad": "red", "neutral": "dim"}

        def _make_section(metrics):
            tbl = Table(show_header=False, show_edge=False, padding=(0, 1), expand=True, box=None)
            tbl.add_column("Metric",   style="bold", min_width=24, no_wrap=True)
            tbl.add_column("Value",    min_width=20, no_wrap=True)
            tbl.add_column("Δ Change", min_width=26, no_wrap=True)
            for m in metrics:
                col = COLORS[m["color"]]
                tbl.add_row(
                    f"{m['icon']} {m['name']}",
                    Text.assemble(m["value"], "  ", (m["context"], "dim")),
                    Text(f"{m['arrow']} {m['delta']}", style=col),
                )
            return tbl

        return RichGroup(
            Text("⚔  Quest Metrics", style="bold cyan"),
            _make_section(quest_metrics),
            Text(""),
            Text("🍅  Pomodoro Metrics", style="bold cyan"),
            _make_section(pomo_metrics),
        )


class DailyReceiptModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="receipt-body"):
            yield Label(f"📋  Daily Receipt  ·  {fantasy_date()}", id="receipt-title")
            yield Rule(line_style="heavy")
            yield RichLog(id="receipt-log", markup=True, auto_scroll=False, wrap=True)
            yield Static("[dim]ESC · Close[/dim]", id="receipt-footer")

    def on_mount(self) -> None:
        entries = get_today_receipt(_pomo_repo.load_all())
        log = self.query_one("#receipt-log", RichLog)
        if not entries:
            log.write("[dim]No completed 🍅 with charge & deed today.[/dim]")
            return
        berserker_count = 0
        hollow_count = 0
        for entry in entries:
            try:
                dt = datetime.fromisoformat(entry["started_at"])
                time_str = dt.astimezone(USER_TZ).strftime("%H:%M")
            except Exception:
                time_str = "??:??"
            forge_type = entry.get("forge_type")
            if forge_type == "berserker":
                icon = "⚡"
                color = "bold yellow"
                berserker_count += 1
            elif forge_type == "hollow":
                icon = "💀"
                color = "dim"
                hollow_count += 1
            else:
                icon = "🍅"
                color = "cyan bold"
            log.write(f"[{color}]── {time_str}  {icon} {entry['quest_title']}[/{color}]")
            log.write(f"  [yellow]⚔[/yellow]  {entry['charge']}")
            log.write(f"  [green]✦[/green]  {entry['deed']}")
            log.write("")
        # Exclude hollows from focus time count
        real_pomos = len(entries) - hollow_count
        total_mins = real_pomos * POMO_CONFIG["work_secs"] // 60
        noun = "pomodoro" if real_pomos == 1 else "pomodoros"
        summary = f"[dim]{real_pomos} {noun}  ·  ⏱ {total_mins} min focused today[/dim]"
        if berserker_count:
            summary += f"  [bold yellow]⚡ {berserker_count} berserker[/bold yellow]"
        if hollow_count:
            summary += f"  [dim]💀 {hollow_count} hollow[/dim]"
        log.write(summary)
