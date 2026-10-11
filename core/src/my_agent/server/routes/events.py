"""全局事件流（SSE）。

与 ``/v1/chat`` 的区别：那条流是「一次任务的响应」，这里的流是**连接级**的，
客户端打开一次就一直挂着，用来接收服务端主动推送（目前主要是提醒到点）。

前端用 fetch + ReadableStream 消费（需要带鉴权头，所以不能用原生 EventSource）。
"""

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
    """帧格式只有 `server/sse.py` 一份实现（由 `Event.to_sse` 转发）。

    这里以前自己拼字符串，是三处手写里的一处（另两处在 `routes/chat.py` /
    `routes/groups.py`），其中 `groups` 那份已经漏掉 `default=str` 与其它漂移。
    """
    return event.to_sse()


@router.get("/v1/events")
async def event_stream(request: Request) -> StreamingResponse:
    runtime: AppRuntime = get_runtime(request)
    queue = runtime.events.subscribe()

    async def generator() -> AsyncIterator[str]:
        # 首帧告知客户端推送通道已建立，并带上当前订阅数便于排查
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
                    # 心跳注释帧：保持连接活性，同时让客户端能确认服务端还活着
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
    """手动发一条事件，用于验证通知链路是否打通。"""
    runtime: AppRuntime = get_runtime(request)
    delivered = runtime.events.publish(
        "notice", level="info", title="测试通知", message="如果你看到这条消息，说明通知链路正常。"
    )
    return {"ok": True, "delivered": delivered, "subscribers": runtime.events.subscriber_count}
