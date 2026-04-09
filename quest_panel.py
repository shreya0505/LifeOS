from __future__ import annotations

from datetime import datetime, timezone

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Static

from utils import get_elapsed, format_duration

# Lazygit-style panel definitions: (status, icon, rpg_name)
PANELS: list[tuple[str, str, str]] = [
    ("log",     "📜", "Quest Board"),
    ("active",  "🔥", "Active Quests"),
    ("blocked", "🧱", "Cursed"),
    ("done",    "🏆", "Hall of Fame"),
]


def _age_days(quest: dict) -> float | None:
    ref = quest.get("started_at") or quest.get("created_at")
    if not ref:
        return None
    try:
        dt = datetime.fromisoformat(ref)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


# ── StatusPane ────────────────────────────────────────────────────────────────


class StatusPane(Widget):
    """One lazygit-style panel for a single quest status."""

    can_focus = False

    def __init__(self, status: str, icon: str, rpg_name: str, index: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.status = status
        self.icon = icon
        self.rpg_name = rpg_name
        self.panel_index = index
        self._quests: list[dict] = []
        self._pomo_counts: dict = {}
        self._cursor: int = 0
        self._is_active: bool = False

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id=f"pane-scroll-{self.status}"):
            yield Static("", id=f"pane-content-{self.status}", markup=True)

    def set_quests(self, quests: list[dict], pomo_counts: dict) -> None:
        self._quests = [q for q in quests if q["status"] == self.status]
        self._pomo_counts = pomo_counts
        self._clamp_cursor()
        self._update_title()
        self._redraw()

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self.set_class(active, "active-pane")
        self._redraw()

    def _update_title(self) -> None:
        n = len(self._quests)
        self.border_title = f"{self.panel_index + 1} {self.icon} {self.rpg_name} ({n})"

    def _clamp_cursor(self) -> None:
        if not self._quests:
            self._cursor = 0
        else:
            self._cursor = max(0, min(self._cursor, len(self._quests) - 1))

    def move_cursor(self, delta: int) -> None:
        if not self._quests:
            return
        old = self._cursor
        self._cursor = max(0, min(self._cursor + delta, len(self._quests) - 1))
        if self._cursor != old:
            self._redraw()

    def selected_quest(self) -> dict | None:
        if not self._quests or self._cursor >= len(self._quests):
            return None
        return self._quests[self._cursor]

    def _redraw(self) -> None:
        lines: list[str] = []
        if not self._quests:
            lines.append("[dim]  (empty)[/dim]")
        else:
            for i, quest in enumerate(self._quests):
                selected = self._is_active and i == self._cursor
                self._render_quest(lines, quest, selected)
        try:
            self.query_one(f"#pane-content-{self.status}", Static).update("\n".join(lines))
        except Exception:
            pass

    def _render_quest(self, lines: list[str], quest: dict, selected: bool) -> None:
        status  = quest["status"]
        title   = escape(quest["title"])
        qid     = quest["id"]
        days    = _age_days(quest)
        elapsed = get_elapsed(quest)

        # Frog badge
        frog_tag = " [green]🐸[/green]" if quest.get("frog") else ""

        # Age badge and color
        if status in ("log", "active", "blocked") and days is not None:
            if days >= 8:
                badge   = " [red]💀[/red]"
                age_col = "red"
            elif days >= 5:
                badge   = " [yellow]⚠️[/yellow]"
                age_col = "yellow"
            else:
                badge   = ""
                age_col = "dim"
        else:
            badge   = ""
            age_col = "dim"

        # Pomo dots (max 5 shown as emoji, then ×N)
        pomo_n   = self._pomo_counts.get(qid, 0)
        pomo_str = ("🍅" * min(pomo_n, 5)) if 0 < pomo_n <= 5 else (f"🍅×{pomo_n}" if pomo_n > 5 else "")

        # Human-readable age
        if days is None:
            age_label = "new"
        elif days < 0.083:
            age_label = "just now"
        elif days < 1:
            age_label = f"{int(days * 24)}h"
        else:
            age_label = f"{int(days)}d"

        gutter = "[bold]❯[/bold]" if selected else " "

        if status == "done":
            line1 = f" {gutter} [dim]✅ [strike]{title}[/strike][/dim]{frog_tag}"
            line2 = f"    [{age_col}]{age_label}[/{age_col}]"

        elif status == "blocked":
            line1 = f" {gutter} [red]{title}[/red]{frog_tag}{badge}"
            parts = ([pomo_str] if pomo_str else []) + [f"[{age_col}]{age_label} blocked[/{age_col}]"]
            line2 = f"    [dim]{'  ·  '.join(parts)}[/dim]"

        elif status == "active":
            line1 = f" {gutter} [bold]{title}[/bold]{frog_tag}{badge}"
            parts = [pomo_str] if pomo_str else []
            line2 = f"    [dim]{'  ·  '.join(parts)}[/dim]" if parts else ""

        else:  # log
            line1 = f" {gutter} {title}{frog_tag}{badge}"
            parts = [pomo_str] if pomo_str else []
            parts.append(f"[{age_col}]{age_label}[/{age_col}]" if (days and days > 0.5) else f"[{age_col}]new[/{age_col}]")
            line2 = f"    [dim]{'  ·  '.join(parts)}[/dim]"

        lines.append(line1)
        if line2:
            lines.append(line2)


# ── RosterPanel (container) ──────────────────────────────────────────────────


class RosterPanel(Widget):
    """Lazygit-style stacked 4-panel quest roster.

    Navigation:
      1-4     focus panel
      j / ↓   move down in panel
      k / ↑   move up in panel
      ] / [   next / prev panel
    """

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_pane: int = 0
        self._panes: list[StatusPane] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="roster-stack"):
            for i, (status, icon, rpg_name) in enumerate(PANELS):
                yield StatusPane(
                    status=status, icon=icon, rpg_name=rpg_name, index=i,
                    id=f"pane-{status}",
                )

    def on_mount(self) -> None:
        self._panes = list(self.query(StatusPane))
        if self._panes:
            self._panes[0].set_active(True)

    def refresh_quests(self, quests: list[dict], pomo_counts: dict | None = None) -> None:
        pomo = pomo_counts or {}
        for pane in self._panes:
            pane.set_quests(quests, pomo)

    def selected_quest(self) -> dict | None:
        if not self._panes:
            return None
        return self._panes[self._active_pane].selected_quest()

    def _switch_pane(self, index: int) -> None:
        if 0 <= index < len(self._panes) and index != self._active_pane:
            self._panes[self._active_pane].set_active(False)
            self._active_pane = index
            self._panes[self._active_pane].set_active(True)

    # ── Keyboard navigation ───────────────────────────────────────────────────

    def on_key(self, event) -> None:
        k = event.key

        # Number keys switch panels
        if k in ("1", "2", "3", "4"):
            self._switch_pane(int(k) - 1)
            event.prevent_default()
            event.stop()
            return

        if not self._panes:
            return

        # j / k navigate within active pane
        if k in ("down", "j"):
            self._panes[self._active_pane].move_cursor(1)
            event.prevent_default()
            event.stop()
        elif k in ("up", "k"):
            self._panes[self._active_pane].move_cursor(-1)
            event.prevent_default()
            event.stop()

        # ] / [ cycle between panes
        elif k in ("]", "right_square_bracket"):
            self._switch_pane((self._active_pane + 1) % len(self._panes))
            event.prevent_default()
            event.stop()
        elif k in ("[", "left_square_bracket"):
            self._switch_pane((self._active_pane - 1) % len(self._panes))
            event.prevent_default()
            event.stop()
