









from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..storage.life import ReminderRepository
from .sse import format_sse

logger = logging.getLogger(__name__)


QUEUE_SIZE = 64

HEARTBEAT_SECONDS = 25.0

SCHEDULE_INTERVAL = 20.0


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_sse(self) -> str:






        return format_sse(self.type, {"ts": self.ts, **self.data})


class EventBus:






    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event_type: str, **data: Any) -> int:





        event = Event(type=event_type, data=data)
        delivered = 0
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)
                    delivered += 1
            except Exception:  
                logger.exception("向订阅者投递事件失败，已跳过该订阅者")
        return delivered


class ReminderScheduler:


    def __init__(
        self,
        repository: ReminderRepository | None,
        bus: EventBus,
        *,
        interval: float = SCHEDULE_INTERVAL,
    ) -> None:
        self._repo = repository
        self._bus = bus
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._repo is None or self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="reminder-scheduler")
        logger.info("提醒调度已启动（轮询间隔 %.0fs）", self._interval)

    async def stop(self) -> None:
        self._stopping = True
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(self._interval)
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:  
                logger.exception("提醒检查失败，将在下个周期重试")

    async def check_once(self) -> int:

        if self._repo is None:
            return 0

        due = await self._repo.due()
        fired = 0
        for record in due:
            
            if not await self._repo.mark_fired(record.id):
                continue
            fired += 1
            self._bus.publish(
                "reminder",
                id=record.id,
                content=record.content,
                remind_at_text=record.to_dict()["remind_at_text"],
                advance_min=record.advance_min,
            )
            
            
            
            logger.info("提醒已触发 id=%s（正文见事件流，不落日志）", record.id)
        return fired
