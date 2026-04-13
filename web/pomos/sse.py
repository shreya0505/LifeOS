"""SSE tick endpoint — server-authoritative timer."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from web.pomos.engine import get_engine

router = APIRouter()


@router.get("/pomos/tick")
async def tick_stream():
    """Push remaining seconds every 1s. Push segment-complete when done."""
    return EventSourceResponse(_generate_ticks())


async def _generate_ticks():
    engine = get_engine()

    while engine.is_active and engine.is_timing:
        # If an interrupt is pending (reason screen shown), stop the SSE
        # so we don't race with the interrupt route.
        if engine._interrupt_pending:
            yield {"event": "stopped", "data": "{}"}
            return

        remaining = engine.remaining()

        if remaining <= 0:
            # Re-check: interrupt may have been signalled between the
            # loop guard and here.
            if engine._interrupt_pending or not engine.is_timing:
                yield {"event": "stopped", "data": "{}"}
                return

            # Timer expired — signal the client; /timer-done handles segment completion
            # (keeping end_segment out of SSE avoids a race where /timer-done fires
            #  after SSE has already ended the segment and finds is_timing=False)
            seg_type = engine.seg_type or "work"
            next_gate = "deed" if seg_type == "work" else "charge"
            yield {
                "event": "segment-complete",
                "data": json.dumps({
                    "next_gate": next_gate,
                    "seg_type": seg_type,
                }),
            }
            return

        mins = int(remaining // 60)
        secs = int(remaining % 60)
        total = engine.seg_duration()
        pct = (remaining / total * 100) if total > 0 else 0

        yield {
            "event": "tick",
            "data": json.dumps({
                "remaining": round(remaining, 1),
                "display": f"{mins:02d}:{secs:02d}",
                "percent": round(pct, 1),
            }),
        }

        await asyncio.sleep(1)

    # Session ended or no active timer
    yield {"event": "stopped", "data": "{}"}
