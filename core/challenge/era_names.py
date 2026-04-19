"""Era name picker with no-dupe policy."""

from __future__ import annotations

import random

from .config import ERA_NAMES, MID_WEEK_ADJECTIVES


async def pick_era_name(era_repo) -> str:
    """Pick unused era name. If all 30 used, reuse randomly."""
    used = await era_repo.used_names()
    pool = [n for n in ERA_NAMES if n not in used]
    if not pool:
        pool = list(ERA_NAMES)
    return random.choice(pool)


def pick_midweek_adjective() -> str:
    return random.choice(MID_WEEK_ADJECTIVES)
