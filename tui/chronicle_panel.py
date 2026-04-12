from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from core.utils import today_local, to_local_date, fmt_compact, segment_duration
from core.storage.json_backend import JsonPomoRepo, JsonQuestRepo

from rich.align import Align
from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static

from pathlib import Path
_DATA_DIR = Path(__file__).parent.parent
_pomo_repo = JsonPomoRepo(_DATA_DIR / "pomodoros.json")
_quest_repo = JsonQuestRepo(_DATA_DIR / "quests.json")


# ── Heatmap color helpers ────────────────────────────────────────────────────

def _heat_color(count: int) -> str:
    """Classic green heatmap: dim → green → bright green."""
    if count == 0:
        return "dim"
    if count == 1:
        return "dim green"
    if count <= 3:
        return "green"
    return "bold bright_green"


def _heat_block(count: int) -> str:
    """Colored block for the weekly heatmap."""
    if count == 0:
        return "[dim]··[/dim]"
    color = _heat_color(count)
    if count == 1:
        return f"[{color}]█░[/{color}]"
    if count <= 3:
        return f"[{color}]██[/{color}]"
    return f"[{color}]██[/{color}]"


def _delta_str(current: float | None, previous: float | None, unit: str = "%") -> str:
    """Format a ▲/▼/→ delta string."""
    if current is None or previous is None:
        return "[dim]── new[/dim]"
    d = current - previous
    if abs(d) < 0.5:
        return "[dim]→ steady[/dim]"
    arrow = "▲" if d > 0 else "▼"
    color = "green" if d > 0 else "yellow"
    return f"[{color}]{arrow} {abs(d):.0f}{unit}[/{color}]"


# ── Data computation ─────────────────────────────────────────────────────────

def _compute_all(sessions: list[dict], quests: list[dict]) -> dict:
    """Compute every metric the chronicle needs in a single pass."""
    today_str = today_local().isoformat()
    now = datetime.now(timezone.utc)
    td = today_local()
    week_start = (td - timedelta(days=td.weekday())).isoformat()
    last_week_start = (td - timedelta(days=td.weekday() + 7)).isoformat()

    # Collect all work & break segments
    all_work: list[dict] = []
    all_breaks: list[dict] = []
    today_work_completed = 0
    today_deeds: list[dict] = []
    week_pomos_by_day: dict[str, int] = defaultdict(int)
    last_week_pomos_by_day: dict[str, int] = defaultdict(int)
    week_work_secs = 0.0
    week_break_secs = 0.0
    last_week_work_secs = 0.0
    last_week_break_secs = 0.0
    today_berserker = 0
    today_hollow = 0

    for s in sessions:
        qt = s.get("quest_title", "?")
        segs = s.get("segments", [])
        for i, seg in enumerate(segs):
            seg_date = to_local_date(seg.get("started_at", ""))
            secs = segment_duration(seg)

            if seg["type"] == "work":
                all_work.append(seg)

                if seg.get("completed"):
                    forge_type = seg.get("forge_type")
                    # Weekly heatmap (exclude hollows)
                    if forge_type != "hollow":
                        if seg_date >= week_start:
                            week_pomos_by_day[seg_date] += 1
                            week_work_secs += secs
                        elif seg_date >= last_week_start:
                            last_week_pomos_by_day[seg_date] += 1
                            last_week_work_secs += secs

                    # Today count (exclude hollows)
                    if seg_date == today_str:
                        if forge_type != "hollow":
                            today_work_completed += 1
                        if forge_type == "berserker":
                            today_berserker += 1
                        elif forge_type == "hollow":
                            today_hollow += 1

                # Today's deeds (completed work with charge OR deed)
                if seg_date == today_str:
                    charge = seg.get("charge") or seg.get("intent") or ""
                    deed = seg.get("deed") or seg.get("retro") or ""
                    was_clean = seg.get("completed") and seg.get("interruptions", 0) == 0
                    # Check if a break followed
                    took_break = (i + 1 < len(segs) and segs[i + 1]["type"] != "work")
                    today_deeds.append({
                        "time": seg.get("started_at", "")[11:16],
                        "quest": qt,
                        "charge": charge,
                        "deed": deed,
                        "completed": seg.get("completed", False),
                        "clean": was_clean,
                        "took_break": took_break,
                        "reason": seg.get("interruption_reason") or "",
                    })
            else:
                all_breaks.append(seg)
                if seg_date >= week_start:
                    week_break_secs += secs
                elif seg_date >= last_week_start:
                    last_week_break_secs += secs

    today_deeds.sort(key=lambda d: d["time"], reverse=True)

    # ── Focus Quality: % of work segments completed & clean (last 30) ─────
    recent_work = all_work[-30:]
    prev_work = all_work[-60:-30]
    clean_cur = (sum(1 for s in recent_work if s.get("completed") and s.get("interruptions", 0) == 0)
                 / len(recent_work) * 100) if recent_work else None
    clean_prev = (sum(1 for s in prev_work if s.get("completed") and s.get("interruptions", 0) == 0)
                  / len(prev_work) * 100) if prev_work else None

    # ── Recovery: % of completed work segments followed by any break ──────
    recovery_cur = recovery_prev = None
    for sess_slice, target in [(sessions[-15:], "cur"), (sessions[-30:-15], "prev")]:
        scheduled = taken = 0
        for s in sess_slice:
            segs = s.get("segments", [])
            for i, seg in enumerate(segs):
                if seg["type"] == "work" and seg.get("completed"):
                    scheduled += 1
                    if i + 1 < len(segs) and segs[i + 1]["type"] != "work":
                        taken += 1
        val = round(taken / scheduled * 100) if scheduled > 0 else None
        if target == "cur":
            recovery_cur = val
        else:
            recovery_prev = val

    # ── Clean Streak ──────────────────────────────────────────────────────
    current_streak = 0
    best_streak = 0
    streak = 0
    for seg in all_work:
        if seg.get("completed") and seg.get("interruptions", 0) == 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
    current_streak = streak  # streak at end = current

    # ── Quests conquered today ────────────────────────────────────────────
    conquered_today = sum(
        1 for q in quests
        if q["status"] == "done"
        and to_local_date(q.get("completed_at", "")) == today_str
    )

    # ── Weekly summary ────────────────────────────────────────────────────
    week_total_pomos = sum(week_pomos_by_day.values())
    last_week_total = sum(last_week_pomos_by_day.values())
    week_quests_done = sum(
        1 for q in quests
        if q["status"] == "done"
        and to_local_date(q.get("completed_at", "")) >= week_start
    )

    # ── Hall of Records ──────────────────────────────────────────────────
    # Fastest quest (start → done)
    fastest_quest = None
    fastest_secs = float("inf")
    for q in quests:
        if q["status"] == "done" and q.get("started_at") and q.get("completed_at"):
            try:
                s = datetime.fromisoformat(q["started_at"])
                e = datetime.fromisoformat(q["completed_at"])
                secs = (e - s).total_seconds()
                if secs < fastest_secs:
                    fastest_secs = secs
                    fastest_quest = q["title"]
            except Exception:
                pass

    # Best week (most days with ≥1 pomo) — scan all sessions
    days_with_pomos: dict[str, set[str]] = defaultdict(set)  # week_start → set of dates
    for s in sessions:
        for seg in s.get("segments", []):
            if seg["type"] == "work" and seg.get("completed"):
                seg_date = to_local_date(seg.get("started_at", ""))
                if seg_date:
                    try:
                        d = date.fromisoformat(seg_date)
                        ws = (d - timedelta(days=d.weekday())).isoformat()
                        days_with_pomos[ws].add(seg_date)
                    except Exception:
                        pass
    best_week_days = 0
    best_week_label = ""
    for ws, days_set in days_with_pomos.items():
        if len(days_set) > best_week_days:
            best_week_days = len(days_set)
            best_week_label = f"Week of {ws[5:]}"  # MM-DD

    return {
        "today_pomos": today_work_completed,
        "today_deeds": today_deeds,
        "quality_cur": clean_cur,
        "quality_prev": clean_prev,
        "recovery_cur": recovery_cur,
        "recovery_prev": recovery_prev,
        "streak_current": current_streak,
        "streak_best": best_streak,
        "conquered_today": conquered_today,
        "week_pomos_by_day": week_pomos_by_day,
        "week_total": week_total_pomos,
        "last_week_total": last_week_total,
        "week_quests_done": week_quests_done,
        "week_work_secs": week_work_secs,
        "week_break_secs": week_break_secs,
        "fastest_quest": fastest_quest,
        "fastest_secs": fastest_secs if fastest_quest else None,
        "best_week_days": best_week_days,
        "best_week_label": best_week_label,
        "today_berserker": today_berserker,
        "today_hollow": today_hollow,
    }


# ── Formatting helpers ───────────────────────────────────────────────────────



# ── Widget ───────────────────────────────────────────────────────────────────

class ChroniclePanel(Widget):
    """Right-side panel: Adventurer's Chronicle.

    Shows today's stats, weekly heatmap, deed feed, and personal records.
    """

    BORDER_TITLE = "✦ Adventurer's Chronicle"
    can_focus = True

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="chronicle-scroll"):
            yield Static("", id="chronicle-content", markup=True)

    def refresh_data(self) -> None:
        sessions = _pomo_repo.load_all()
        quests = _quest_repo.load_all()
        self._data = _compute_all(sessions, quests)
        self._redraw()

    def _redraw(self) -> None:
        d = getattr(self, "_data", None)
        if d is None:
            self._update_renderable(Text("  Loading...", style="dim"))
            return

        # Empty state
        if d["today_pomos"] == 0 and d["week_total"] == 0 and d["streak_best"] == 0:
            self._render_empty()
            return

        parts: list = []
        sep = "[dim]─────────────────────────────────────────────────[/dim]"
        self._render_hero(parts, d)
        parts.append(Text.from_markup(sep))
        parts.append(Text(""))
        self._render_metrics(parts, d)
        parts.append(Text(""))
        self._render_week(parts, d)
        parts.append(Text(""))
        self._render_deeds(parts, d)
        parts.append(Text(""))
        self._render_berserker_log(parts, d)
        parts.append(Text(""))
        self._render_records(parts, d)
        self._update_renderable(Align.center(Group(*parts)))

    def _update_renderable(self, content) -> None:
        try:
            self.query_one("#chronicle-content", Static).update(content)
        except Exception:
            pass

    def _render_empty(self) -> None:
        self._update_renderable(Align.center(Text.from_markup(
            "\n\n\n"
            "[dim]Your chronicle awaits.[/dim]\n\n"
            "[dim]Complete your first pomodoro to begin[/dim]\n"
            "[dim]forging your legend.[/dim]\n\n"
            "[dim]Select a quest  →  press [bold]t[/bold] to start 🍅[/dim]"
        )))

    # ── Hero number ───────────────────────────────────────────────────────

    def _render_hero(self, parts: list, d: dict) -> None:
        n = d["today_pomos"]
        color = "bold green" if n > 0 else "dim"
        parts.append(Text.from_markup(
            f"\n[{color}]🍅  {n}[/{color}]\n"
            f"[dim]pomos forged today[/dim]\n"
        ))

    # ── Four metrics row ──────────────────────────────────────────────────

    def _render_metrics(self, parts: list, d: dict) -> None:
        q_val = f"{d['quality_cur']:.0f}%" if d["quality_cur"] is not None else "—"
        q_delta = _delta_str(d["quality_cur"], d["quality_prev"])

        r_val = f"{d['recovery_cur']}%" if d["recovery_cur"] is not None else "—"
        r_delta = _delta_str(d["recovery_cur"], d["recovery_prev"])

        s_cur = d["streak_current"]
        s_best = d["streak_best"]
        c_today = d["conquered_today"]

        # Each metric gets an emoji col + text col for proper alignment
        tbl = Table(box=None, show_header=False, padding=(0, 0), expand=False)
        tbl.add_column(width=3)   # 🎯
        tbl.add_column(min_width=11)
        tbl.add_column(width=3)   # ☕
        tbl.add_column(min_width=11)
        tbl.add_column(width=3)   # 🔥
        tbl.add_column(min_width=11)
        tbl.add_column(width=3)   # 🏆
        tbl.add_column(min_width=8)

        tbl.add_row(
            Text("🎯"), Text.from_markup("[bold]Quality[/bold]"),
            Text("☕"), Text.from_markup("[bold]Recovery[/bold]"),
            Text("🔥"), Text.from_markup("[bold]Streak[/bold]"),
            Text("🏆"), Text.from_markup("[bold]Done[/bold]"),
        )
        tbl.add_row(
            Text(""), Text(q_val),
            Text(""), Text(r_val),
            Text(""), Text(f"{s_cur} clean"),
            Text(""), Text(f"{c_today} today"),
        )
        tbl.add_row(
            Text(""), Text.from_markup(f"[dim]{q_delta}[/dim]"),
            Text(""), Text.from_markup(f"[dim]{r_delta}[/dim]"),
            Text(""), Text.from_markup(f"[dim]best: {s_best}[/dim]"),
            Text(""), Text(""),
        )
        parts.append(tbl)
        parts.append(Text(""))

    # ── Weekly heatmap ────────────────────────────────────────────────────

    def _render_week(self, parts: list, d: dict) -> None:
        parts.append(Text.from_markup(
            "[dim]── THIS WEEK ─────────────────────────────────[/dim]\n"
        ))

        today_date = today_local()
        monday = today_date - timedelta(days=today_date.weekday())
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        heat_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        for _ in range(7):
            heat_tbl.add_column(justify="center", min_width=4)

        name_row = []
        block_row = []
        count_row = []
        for i in range(7):
            day = monday + timedelta(days=i)
            day_str = day.isoformat()
            count = d["week_pomos_by_day"].get(day_str, 0)

            name_row.append(Text(day_names[i], style="dim"))
            if day > today_date:
                block_row.append(Text("──", style="dim"))
                count_row.append(Text("·", style="dim"))
            else:
                block_row.append(Text.from_markup(_heat_block(count)))
                ct = str(count) if count > 0 else "·"
                count_row.append(Text.from_markup(f"[{_heat_color(count)}]{ct}[/{_heat_color(count)}]"))

        heat_tbl.add_row(*name_row)
        heat_tbl.add_row(*block_row)
        heat_tbl.add_row(*count_row)
        parts.append(heat_tbl)

        wt = d["week_total"]
        wq = d["week_quests_done"]
        wk_quality = d["quality_cur"]
        qstr = f"{wk_quality:.0f}%" if wk_quality is not None else "—"
        parts.append(Text.from_markup(
            f"\n[dim]{wt} 🍅  ·  {wq} 🏆 conquered  ·  {qstr} clean[/dim]\n"
        ))

        # Focus / Rest bars
        bar_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        bar_tbl.add_column(min_width=6)   # label
        bar_tbl.add_column(min_width=30)  # bar
        bar_tbl.add_column(min_width=5)   # pct
        bar_tbl.add_column()              # note

        total_secs = d["week_work_secs"] + d["week_break_secs"]
        if total_secs > 0:
            focus_pct = d["week_work_secs"] / total_secs * 100
            rest_pct = 100 - focus_pct
            focus_w = int(focus_pct / 100 * 30)
            rest_w = int(rest_pct / 100 * 30)

            focus_bar = f"[green]{'█' * focus_w}[/green][dim]{'░' * (30 - focus_w)}[/dim]"
            rest_bar = f"[cyan]{'█' * rest_w}[/cyan][dim]{'░' * (30 - rest_w)}[/dim]"
            balanced = "[dim]✓ balanced[/dim]" if 15 <= rest_pct <= 35 else ""

            bar_tbl.add_row(
                Text("Focus"),
                Text.from_markup(focus_bar),
                Text.from_markup(f"[dim]{focus_pct:.0f}%[/dim]"),
                Text(""),
            )
            bar_tbl.add_row(
                Text("Rest"),
                Text.from_markup(rest_bar),
                Text.from_markup(f"[cyan]{rest_pct:.0f}%[/cyan]"),
                Text.from_markup(balanced),
            )
        else:
            bar_tbl.add_row(
                Text.from_markup("[dim]No focus time recorded this week[/dim]"),
                Text(""), Text(""), Text(""),
            )
        parts.append(bar_tbl)
        parts.append(Text(""))

    # ── Today's deeds ─────────────────────────────────────────────────────

    def _render_deeds(self, parts: list, d: dict) -> None:
        deeds = d["today_deeds"]
        if not deeds:
            return

        parts.append(Text.from_markup(
            "[dim]── TODAY'S DEEDS ─────────────────────────────[/dim]\n"
        ))

        deed_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        deed_tbl.add_column(min_width=6)   # time
        deed_tbl.add_column(min_width=12)  # label / quest+badge
        deed_tbl.add_column()              # content

        for entry in deeds[:8]:
            time_str = entry["time"]
            quest = escape(entry["quest"])

            if entry["clean"] and entry["completed"]:
                badge = "[green]🔥[/green]"
            elif entry["completed"] and entry["took_break"]:
                badge = "[cyan]☕[/cyan]"
            elif entry["completed"]:
                badge = "[dim]✅[/dim]"
            else:
                reason = entry.get("reason", "")
                badge = {
                    "distracted": "[yellow]🌀[/yellow]",
                    "blocked":    "[red]🧱[/red]",
                    "emergency":  "[red]🚨[/red]",
                    "personal":   "[cyan]🏠[/cyan]",
                }.get(reason, "[yellow]⚠[/yellow]")

            # Header row: time + quest+badge inline
            deed_tbl.add_row(
                Text.from_markup(f"[dim]{time_str}[/dim]"),
                Text.from_markup(f"🍅 [bold]{quest}[/bold]  {badge}"),
                Text(""),
            )

            # Charge (intent) row
            if entry["charge"]:
                deed_tbl.add_row(
                    Text(""),
                    Text.from_markup("[yellow]Charged  ›[/yellow]"),
                    Text.from_markup(f"[yellow]{escape(entry['charge'])}[/yellow]"),
                )
            # Deed (result) row
            if entry["deed"]:
                deed_tbl.add_row(
                    Text(""),
                    Text.from_markup("[green]Forged   ›[/green]"),
                    Text.from_markup(f"[green]{escape(entry['deed'])}[/green]"),
                )
            elif entry["charge"]:
                deed_tbl.add_row(
                    Text(""),
                    Text.from_markup("[dim]Forged   ›[/dim]"),
                    Text.from_markup("[dim italic]awaiting tale…[/dim italic]"),
                )
            # Spacer row between deeds
            deed_tbl.add_row(Text(""), Text(""), Text(""))

        parts.append(deed_tbl)

    # ── Hall of Records ───────────────────────────────────────────────────

    def _render_berserker_log(self, parts: list, d: dict) -> None:
        today_b = d.get("today_berserker", 0)
        today_h = d.get("today_hollow", 0)
        if today_b == 0 and today_h == 0:
            return

        parts.append(Text.from_markup(
            "[dim]── ⚡ FORGE LOG ──────────────────────────────[/dim]\n"
        ))

        log_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        log_tbl.add_column(min_width=3)
        log_tbl.add_column(min_width=16)
        log_tbl.add_column(min_width=12)

        if today_b > 0:
            log_tbl.add_row(
                Text("⚡"),
                Text.from_markup("[bold yellow]Berserker[/bold yellow]"),
                Text.from_markup(f"[bold yellow]{today_b} today[/bold yellow]"),
            )
        if today_h > 0:
            log_tbl.add_row(
                Text("💀"),
                Text.from_markup("[dim]Hollow[/dim]"),
                Text.from_markup(f"[dim]{today_h} today[/dim]"),
            )

        parts.append(log_tbl)
        parts.append(Text(""))

    def _render_records(self, parts: list, d: dict) -> None:
        has_any = d["streak_best"] > 0 or d["fastest_quest"] or d["best_week_days"] > 0
        if not has_any:
            return

        parts.append(Text.from_markup(
            "[dim]── 🏆 HALL OF RECORDS ───────────────────────[/dim]\n"
        ))

        rec_tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        rec_tbl.add_column(min_width=3)   # icon
        rec_tbl.add_column(min_width=16)  # label
        rec_tbl.add_column(min_width=12)  # value
        rec_tbl.add_column()              # detail

        if d["streak_best"] > 0:
            rec_tbl.add_row(
                Text("🔥"),
                Text.from_markup("[bold]Longest Streak[/bold]"),
                Text.from_markup(f"[bold white]{d['streak_best']} clean[/bold white]"),
                Text(""),
            )

        if d["fastest_quest"]:
            dur = fmt_compact(d["fastest_secs"])
            title = escape(d["fastest_quest"])
            rec_tbl.add_row(
                Text("⚡"),
                Text.from_markup("[bold]Fastest Quest[/bold]"),
                Text.from_markup(f"[bold white]{dur}[/bold white]"),
                Text.from_markup(f"[dim]\"{title}\"[/dim]"),
            )

        if d["best_week_days"] > 0:
            rec_tbl.add_row(
                Text("📅"),
                Text.from_markup("[bold]Most Consistent[/bold]"),
                Text.from_markup(f"[bold white]{d['best_week_days']}/7 days[/bold white]"),
                Text.from_markup(f"[dim]{d['best_week_label']}[/dim]"),
            )

        if d["recovery_cur"] is not None and d["recovery_cur"] > 0:
            rec_tbl.add_row(
                Text("☕"),
                Text.from_markup("[bold]Best Recovery[/bold]"),
                Text.from_markup(f"[bold white]{d['recovery_cur']}%[/bold white]"),
                Text(""),
            )

        parts.append(rec_tbl)
        parts.append(Text(""))
