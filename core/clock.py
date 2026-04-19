"""Central clock. Test-mode day offset isolates dev-time fakery from core.

Production: behaves identically to datetime.now().
Test mode (TEST_MODE=1): reads integer day offset from TEST_CLOCK_FILE
(default ./.test_clock) and adds it to every now() call.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from core.config import USER_TZ

_OFFSET_FILE = Path(os.environ.get("TEST_CLOCK_FILE", "./.test_clock"))


def is_test_mode() -> bool:
    return os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes", "on")


def _load_offset_days() -> int:
    if not is_test_mode():
        return 0
    try:
        return int(_OFFSET_FILE.read_text().strip() or "0")
    except Exception:
        return 0


def _save_offset_days(n: int) -> None:
    _OFFSET_FILE.write_text(str(int(n)))


def offset_days() -> int:
    return _load_offset_days()


def advance_day(n: int = 1) -> int:
    new = _load_offset_days() + int(n)
    _save_offset_days(new)
    return new


def set_offset_days(n: int) -> int:
    _save_offset_days(int(n))
    return int(n)


def reset() -> None:
    _save_offset_days(0)


def _delta() -> timedelta:
    return timedelta(days=_load_offset_days())


def utcnow() -> datetime:
    return datetime.now(timezone.utc) + _delta()


def local_now() -> datetime:
    return datetime.now(USER_TZ) + _delta()


def today_local() -> date:
    return local_now().date()
