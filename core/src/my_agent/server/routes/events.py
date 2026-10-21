







from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..deps import get_runtime
from ..events import HEARTBEAT_SECONDS, Event
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["events"])


def _sse(event: Event) -> str:





    return event.to_sse()


@router.get("/v1/events")
async def event_stream(request: Request) -> StreamingResponse:
    runtime: AppRuntime = get_runtime(request)
    queue = runtime.events.subscribe()

    async def generator() -> AsyncIterator[str]:
        
        yield _sse(
            Event(
                type="ready",
                data={"subscribers": runtime.events.subscriber_count},
            )
        )
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    
                    yield ": ping\n\n"
                    continue
                yield _sse(event)
        except asyncio.CancelledError:
            raise
        finally:
            runtime.events.unsubscribe(queue)
            logger.debug("事件流订阅者已断开，剩余 %s", runtime.events.subscriber_count)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/events/test")
async def publish_test_event(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    delivered = runtime.events.publish(
        "notice", level="info", title="测试通知", message="如果你看到这条消息，说明通知链路正常。"
    )
    return {"ok": True, "delivered": delivered, "subscribers": runtime.events.subscriber_count}
