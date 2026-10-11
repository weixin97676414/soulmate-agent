"""服务端主动推送：事件总线 + 提醒调度。

有两类消息不是「请求-响应」模式产生的，需要服务端主动推给客户端：

- 提醒到点（后台定时器触发，与任何对话请求无关）；
- 未来可能的其他后台事件（MCP 服务掉线、任务完成通知等）。

因此建一条独立于 ``/v1/chat`` 的全局事件流 ``/v1/events``。
"""

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

# 单个订阅者的队列上限。慢客户端只保留最近的事件，不许把内存吃光。
QUEUE_SIZE = 64
# SSE 心跳间隔：既保持连接，也让客户端能及时发现断线
HEARTBEAT_SECONDS = 25.0
# 提醒轮询间隔
SCHEDULE_INTERVAL = 20.0


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """拼成 SSE 帧。

        ⚠️ 帧格式只有 `server/sse.py` 一份实现 —— 这里以前自己拼字符串，
        是第**四**处手写（另外三处在 `routes/chat.py` / `routes/groups.py` /
        `routes/events.py`，且 `groups` 那份已经与其它漂移）。三处一起收敛掉了。
        """
        return format_sse(self.type, {"ts": self.ts, **self.data})


class EventBus:
    """极简发布订阅。

    每个订阅者一个独立队列；队列满时丢弃**最旧**的事件——宁可丢历史通知，
    也不能让一个卡住的客户端把服务端内存拖垮。
    """

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
        """发布事件。同步方法，方便在任意位置调用。

        **单个订阅者故障必须被隔离**：一个客户端连接异常，不能让其他客户端
        一起收不到通知。所以每个订阅者的投递都单独兜底。
        """
        event = Event(type=event_type, data=data)
        delivered = 0
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                # 丢最旧的一条再塞新的，保证订阅者拿到的是"最新的世界状态"
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)
                    delivered += 1
            except Exception:  # noqa: BLE001 - 隔离故障订阅者
                logger.exception("向订阅者投递事件失败，已跳过该订阅者")
        return delivered


class ReminderScheduler:
    """后台轮询提醒表，到点就通过事件总线推送。"""

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
            except Exception:  # noqa: BLE001 - 后台任务绝不能因单次异常而退出
                logger.exception("提醒检查失败，将在下个周期重试")

    async def check_once(self) -> int:
        """检查并触发到点的提醒，返回触发条数（测试直接调用它，不用等定时器）。"""
        if self._repo is None:
            return 0

        due = await self._repo.due()
        fired = 0
        for record in due:
            # 先标记再推送：即使推送失败也不会重复提醒
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
            # ⚠️ **正文不进日志**（第 88 批，M-23）：用户设的提醒常含"吃药""见客户"
            # 这类私事，而 core.log 有 14 天轮转、还可能被用户整包带出去。
            # 正文已经通过上面那条 `reminder` 事件推给界面了，日志只需要能对上号。
            logger.info("提醒已触发 id=%s（正文见事件流，不落日志）", record.id)
        return fired
