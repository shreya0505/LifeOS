from rich.text import Text

# 7-row × 8-col pixel art digit bitmaps (scoreboard style)
_PIXEL_DIGITS: dict[str, list[str]] = {
    "0": [
        " ██████ ",
        "██    ██",
        "██    ██",
        "██    ██",
        "██    ██",
        "██    ██",
        " ██████ ",
    ],
    "1": [
        "   ██   ",
        "  ███   ",
        "   ██   ",
        "   ██   ",
        "   ██   ",
        "   ██   ",
        " ██████ ",
    ],
    "2": [
        " ██████ ",
        "      ██",
        "      ██",
        " ██████ ",
        "██      ",
        "██      ",
        "████████",
    ],
    "3": [
        " ██████ ",
        "      ██",
        "      ██",
        "  █████ ",
        "      ██",
        "      ██",
        " ██████ ",
    ],
    "4": [
        "██    ██",
        "██    ██",
        "██    ██",
        "████████",
        "      ██",
        "      ██",
        "      ██",
    ],
    "5": [
        "████████",
        "██      ",
        "██      ",
        " ██████ ",
        "      ██",
        "      ██",
        " ██████ ",
    ],
    "6": [
        " ██████ ",
        "██      ",
        "██      ",
        "███████ ",
        "██    ██",
        "██    ██",
        " ██████ ",
    ],
    "7": [
        "████████",
        "      ██",
        "     ██ ",
        "    ██  ",
        "   ██   ",
        "   ██   ",
        "   ██   ",
    ],
    "8": [
        " ██████ ",
        "██    ██",
        "██    ██",
        " ██████ ",
        "██    ██",
        "██    ██",
        " ██████ ",
    ],
    "9": [
        " ██████ ",
        "██    ██",
        "██    ██",
        " ███████",
        "      ██",
        "      ██",
        " ██████ ",
    ],
}

# Double-row dots for visual weight at 7-row scale; blank for pulse-off
_COLON_ON  = ["   ", " ▪ ", " ▪ ", "   ", " ▪ ", " ▪ ", "   "]
_COLON_OFF = ["   ", "   ", "   ", "   ", "   ", "   ", "   "]

POMO_RPG_HEADLINERS: list[str] = [
    "⚔  Into the Fray",
    "🔥  The Forge Burns",
    "🛡  Hold the Line",
    "⚡  Storm the Gates",
    "🌑  Dark Work Ahead",
    "💀  No Retreat",
    "🗡  Blade in Hand",
    "🏰  Defend the Realm",
    "🌊  Ride the Wave",
    "🦅  Eyes on the Prize",
    "🌙  Shadow Run",
    "🔮  Channeling Focus",
    "🧱  Laying Stone by Stone",
    "⛏  Deep in the Mine",
    "🎯  Lock On Target",
    "🌪  Into the Storm",
    "🗺  Charting the Path",
    "🕯  One Candle Burns",
    "🐉  Slay the Dragon",
    "🌅  Dawn Offensive",
]

POMO_WAR_CRIES: list[str] = [
    "The realm does not wait. Charge forth.",
    "One pomo at a time. Make it count.",
    "No charge is too small. Begin.",
    "Forge something real. The ledger is watching.",
    "Name the one thing. Then do only that.",
    "Clarity before motion. What will you claim?",
    "The work does not do itself. Ride out.",
    "Twenty-five minutes. One truth. Start.",
    "What will exist at the end of this pomo that does not exist now?",
    "Focus is the rarest resource. Spend it well.",
    "The next pomo is the most important one.",
    "Scope tight. Deed earned. Receipt written.",
    "Distraction is the enemy. Name your charge.",
    "Small deeds, faithfully recorded, build empires.",
    "Charge, focus, deed. The loop is complete.",
]


def render_block_clock(
    mins: int,
    secs: int,
    color: str,
    urgent: bool = False,
    pulse: bool = True,
) -> Text:
    """Render MM:SS as a 7-row × 8-col pixel art scoreboard clock.

    Args:
        mins: Minutes to display (0-99)
        secs: Seconds to display (0-59)
        color: Rich color name for digit fill
        urgent: If True, renders reverse video (burning effect)
        pulse: If True, colon dots visible; if False, colon is blank
    """
    m1, m2 = divmod(mins, 10)
    s1, s2 = divmod(secs, 10)
    colon = _COLON_ON if pulse else _COLON_OFF

    rows: list[str] = []
    for r in range(7):
        row = (
            _PIXEL_DIGITS[str(m1)][r] + "  "
            + _PIXEL_DIGITS[str(m2)][r] + "  "
            + colon[r] + "  "
            + _PIXEL_DIGITS[str(s1)][r] + "  "
            + _PIXEL_DIGITS[str(s2)][r]
        )
        rows.append(row)

    style = color + " bold" + (" reverse" if urgent else "")
    result = Text()
    for i, row in enumerate(rows):
        result.append(row, style)
        if i < 6:
            result.append("\n")
    return result


def render_health_bar(remaining: float, total: float, is_break: bool,
                      width: int = 52) -> Text:
    """Render a █▓▒░ gradient progress bar."""
    pct = remaining / total if total > 0 else 0.0
    if is_break:
        filled = int((1.0 - pct) * width)
        color = "cyan"
    else:
        filled = int(pct * width)
        color = "green" if pct > 0.4 else ("yellow" if pct > 0.15 else "red")
    empty = width - filled
    result = Text()
    result.append("█" * filled, color + " bold")
    result.append("░" * empty, "dim")
    pct_label = int((1.0 - pct if is_break else pct) * 100) if is_break else int(pct * 100)
    result.append(f"  {pct_label}%", color + " dim")
    return result


def render_momentum_bar(momentum: int, max_blocks: int = 10) -> Text:
    """Render a filling momentum bar using ▰▱ chars (one block per clean pomo)."""
    filled = min(momentum, max_blocks)
    empty  = max_blocks - filled
    pct    = int(filled / max_blocks * 100)
    result = Text()
    result.append("Momentum  ", "dim")
    result.append("▰" * filled, "green bold")
    result.append("▱" * empty,  "dim")
    extra = f" +{momentum - max_blocks}" if momentum > max_blocks else ""
    result.append(f"  {momentum} clean{extra} · {pct}%", "green dim")
    return result
