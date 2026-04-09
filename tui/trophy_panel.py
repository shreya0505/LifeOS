"""Hall of Valor — Daily Trophy Case panel widget."""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static

from pathlib import Path
from core.trophy_compute import compute_trophies
from core.storage.json_backend import JsonPomoRepo, JsonQuestRepo, JsonTrophyPRRepo

_DATA_DIR = Path(__file__).parent.parent
_pomo_repo = JsonPomoRepo(_DATA_DIR / "pomodoros.json")
_quest_repo = JsonQuestRepo(_DATA_DIR / "quests.json")
_trophy_pr_repo = JsonTrophyPRRepo(_DATA_DIR / "trophies.json")


# ── Tier styling ─────────────────────────────────────────────────────────────

_TIER_BADGE = {
    "gold":   "[bold #ffffff]🥇 GOLD[/bold #ffffff]",
    "silver": "[bold #ffcc00]🥈 SILVER[/bold #ffcc00]",
    "bronze": "[bold #ff9933]🥉 BRONZE[/bold #ff9933]",
    "locked": "[dim]░░ LOCKED[/dim]",
}

_TIER_COLOR = {
    "gold":   "#ffffff",
    "silver": "#ffcc00",
    "bronze": "#ff9933",
    "locked": "dim",
}

_TIER_BAR_COLOR = {
    "gold":   "bold #ffffff",
    "silver": "bold #ffcc00",
    "bronze": "bold #ff9933",
    "locked": "dim",
}


def _spaced(name: str) -> str:
    """Convert 'Frog Slayer' to 'F R O G   S L A Y E R'."""
    result = []
    for ch in name.upper():
        if ch == " ":
            result.append(" ")
        else:
            result.append(ch)
    return " ".join(result)


def _progress_bar(progress: float, target: float, tier: str, width: int = 24) -> Text:
    """Render a filled progress bar."""
    pct = min(1.0, progress / target) if target > 0 else 0.0
    filled = int(pct * width)
    empty = width - filled
    bar = Text()
    color = _TIER_BAR_COLOR.get(tier, "dim")
    bar.append("█" * filled, color)
    bar.append("░" * empty, "dim")
    return bar


class TrophyPanel(Widget):
    """Right-side panel: Hall of Valor — daily trophy case."""

    BORDER_TITLE = "⚔ Hall of Valor"
    can_focus = True

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="trophy-scroll"):
            yield Static("", id="trophy-content", markup=True)

    def refresh_data(self) -> None:
        try:
            sessions = _pomo_repo.load_all()
            quests = _quest_repo.load_all()
            prs = _trophy_pr_repo.load_prs()
            self._data, updated_prs = compute_trophies(sessions, quests, prs)
            _trophy_pr_repo.save_prs(updated_prs)
        except Exception:
            self._data = None
        self._redraw()

    def _redraw(self) -> None:
        d = self._data
        if d is None:
            self._update(Text("  Loading...", style="dim"))
            return

        trophies = d["trophies"]
        summary = d["summary"]
        best_day = d["best_day"]

        # Empty state
        if all(t["tier"] == "locked" for t in trophies):
            self._render_empty()
            return

        parts: list = []
        parts.append(Text.from_markup(
            "\n  [dim]── TODAY'S TROPHIES ────────────────────────[/dim]\n"
        ))

        # Single table for all trophies — consistent column widths
        tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        tbl.add_column(min_width=3)   # icon
        tbl.add_column(min_width=28)  # name / desc / bar
        tbl.add_column(min_width=14)  # badge / progress+PR

        for t in trophies:
            tier = t["tier"]
            color = _TIER_COLOR.get(tier, "dim")
            badge = _TIER_BADGE.get(tier, "")

            # Row 1: icon | spaced name | tier badge
            tbl.add_row(
                Text(t["icon"]),
                Text.from_markup(f"[{color}]{_spaced(t['name'])}[/{color}]"),
                Text.from_markup(badge),
            )

            # Row 2: | description |
            tbl.add_row(
                Text(""),
                Text.from_markup(f"[dim]{t['desc']}[/dim]"),
                Text(""),
            )

            # Row 3: | progress bar |
            bar = _progress_bar(t["progress"], t["target"], tier)
            tbl.add_row(Text(""), bar, Text(""))

            # Row 4: | progress label | 🏅 PR (celebrated)
            pr_text = t["pr"]
            if pr_text != "never earned":
                pr_display = f"[bold #ffcc00]★[/bold #ffcc00] [dim]{pr_text}[/dim]"
            else:
                pr_display = f"[dim]{pr_text}[/dim]"

            tbl.add_row(
                Text(""),
                Text.from_markup(f"[{color}]{t['progress_label']}[/{color}]"),
                Text.from_markup(pr_display),
            )

            # Spacer row
            tbl.add_row(Text(""), Text(""), Text(""))

        parts.append(tbl)

        # ── Summary footer ────────────────────────────────────────────────
        parts.append(Text.from_markup(
            "  [dim]────────────────────────────────────────────[/dim]"
        ))

        gold = summary["gold"]
        silver = summary["silver"]
        bronze = summary["bronze"]
        locked = summary["locked"]

        summary_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        summary_tbl.add_column(min_width=6)
        summary_tbl.add_column()

        medal_parts = []
        if gold:
            medal_parts.append(f"[bold #ffffff]🥇×{gold}[/bold #ffffff]")
        if silver:
            medal_parts.append(f"[bold #ffcc00]🥈×{silver}[/bold #ffcc00]")
        if bronze:
            medal_parts.append(f"[bold #ff9933]🥉×{bronze}[/bold #ff9933]")
        if locked:
            medal_parts.append(f"[dim]░░×{locked}[/dim]")

        summary_tbl.add_row(
            Text.from_markup("[dim]Today[/dim]"),
            Text.from_markup("   ".join(medal_parts)),
        )

        if best_day.get("count", 0) > 0:
            summary_tbl.add_row(
                Text.from_markup("[dim]Best[/dim]"),
                Text.from_markup(
                    f"[dim]{best_day['count']} trophies · {best_day['date'][5:]}[/dim]"
                ),
            )

        parts.append(summary_tbl)
        self._update(Group(*parts))

    def _render_empty(self) -> None:
        self._update(Text.from_markup(
            "\n\n\n"
            "  [dim]Your trophy case awaits.[/dim]\n\n"
            "  [dim]Complete pomodoros and close quests[/dim]\n"
            "  [dim]to earn your first trophy.[/dim]\n\n"
            "  [dim]Mark a quest as [bold]🐸 frog[/bold] with [bold]f[/bold][/dim]\n"
            "  [dim]to unlock the Frog Slayer trophy.[/dim]"
        ))

    def _update(self, content) -> None:
        try:
            self.query_one("#trophy-content", Static).update(content)
        except Exception:
            pass
