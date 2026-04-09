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
        remaining = engine.remaining()

        if remaining <= 0:
            # Timer expired — end the segment
            event = engine.end_segment(completed=True)
            yield {
                "event": "segment-complete",
                "data": json.dumps({
                    "next_gate": event.next_gate,
                    "seg_type": event.seg_type,
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
