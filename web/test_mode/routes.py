"""Dev-only routes. Mounted only when core.clock.is_test_mode() is true.

Never import this from production paths. Keep logic out of core/*.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from core import clock

router = APIRouter(prefix="/test", tags=["test-mode"])


_BAR_STYLE = (
    "position:fixed;bottom:56px;right:16px;z-index:99999;"
    "display:flex;align-items:center;gap:8px;padding:8px 12px;"
    "background:#ff5722;color:#fff;border-radius:8px;"
    "box-shadow:0 4px 12px rgba(0,0,0,.3);"
    "font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;"
    "letter-spacing:.5px;"
)
_BTN_STYLE = (
    "background:rgba(0,0,0,.25);color:#fff;"
    "border:1px solid rgba(255,255,255,.3);border-radius:4px;"
    "padding:3px 8px;cursor:pointer;font:inherit;"
)


def _badge_html() -> str:
    off = clock.offset_days()
    today = clock.today_local().isoformat()
    return (
        f'<div id="test-mode-bar" style="{_BAR_STYLE}">'
        f'  <span style="font-weight:700;text-transform:uppercase">TEST MODE</span>'
        f'  <span style="opacity:.9">{today} (+{off}d)</span>'
        f'  <button style="{_BTN_STYLE}"'
        f'    hx-post="/test/advance-day" hx-target="#test-mode-bar" hx-swap="outerHTML">'
        f'    +1 day</button>'
        f'  <button style="{_BTN_STYLE}opacity:.8;"'
        f'    hx-post="/test/reset" hx-target="#test-mode-bar" hx-swap="outerHTML">'
        f'    reset</button>'
        f'</div>'
    )


@router.get("/bar", response_class=HTMLResponse)
async def bar():
    return HTMLResponse(_badge_html())


@router.post("/advance-day", response_class=HTMLResponse)
async def advance_day():
    clock.advance_day(1)
    return HTMLResponse(_badge_html())


@router.post("/reset", response_class=HTMLResponse)
async def reset():
    clock.reset()
    return HTMLResponse(_badge_html())


@router.get("/status")
async def status():
    return JSONResponse({
        "enabled": clock.is_test_mode(),
        "offset_days": clock.offset_days(),
        "today_local": clock.today_local().isoformat(),
    })
