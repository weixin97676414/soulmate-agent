"""事件总线与提醒调度测试。"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from my_agent.server.events import QUEUE_SIZE, EventBus, ReminderScheduler
from my_agent.storage.db import Database
from my_agent.storage.life import ReminderRepository


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "events.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def reminders(db) -> ReminderRepository:
    return ReminderRepository(db)


# --------------------------------------------------------------------------- #
# 事件总线
# --------------------------------------------------------------------------- #
async def test_publish_reaches_subscribers():
    bus = EventBus()
    first = bus.subscribe()
    second = bus.subscribe()

    delivered = bus.publish("notice", title="你好", message="内容")
    assert delivered == 2
    assert bus.subscriber_count == 2

    for queue in (first, second):
        event = queue.get_nowait()
        assert event.type == "notice"
        assert event.data == {"title": "你好", "message": "内容"}


async def test_publish_without_subscribers_is_noop():
    bus = EventBus()
    assert bus.publish("notice", title="没人听") == 0


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)
    assert bus.subscriber_count == 0
    assert bus.publish("notice") == 0
    assert queue.empty()


async def test_slow_subscriber_drops_oldest_not_newest():
    """队列满时丢最旧的，保证慢客户端拿到的是最新状态而不是一堆陈旧事件。"""
    bus = EventBus()
    queue = bus.subscribe()

    for index in range(QUEUE_SIZE + 10):
        bus.publish("notice", seq=index)

    assert queue.qsize() == QUEUE_SIZE
    first = queue.get_nowait()
    # 最早的 10 条应该已经被挤掉
    assert first.data["seq"] == 10


async def test_publish_isolates_broken_subscriber():
    """一个订阅者故障不能影响其他订阅者，也不能让 publish 整体失败。"""
    bus = EventBus()
    good = bus.subscribe()

    class ExplodingQueue(asyncio.Queue):
        def put_nowait(self, item):  # type: ignore[override]
            raise RuntimeError("模拟订阅者故障")

    # 注册两个故障订阅者，确保无论 set 的迭代顺序如何都会先撞上故障
    bus._subscribers.add(ExplodingQueue())  # noqa: SLF001 - 故意注入故障订阅者
    bus._subscribers.add(ExplodingQueue())  # noqa: SLF001

    # 不应抛错，且正常订阅者仍然收得到
    delivered = bus.publish("notice", seq=1)
    assert delivered == 1
    assert not good.empty()
    assert good.get_nowait().data["seq"] == 1


# --------------------------------------------------------------------------- #
# 提醒调度
# --------------------------------------------------------------------------- #
async def test_scheduler_fires_due_reminder(reminders):
    bus = EventBus()
    queue = bus.subscribe()
    scheduler = ReminderScheduler(reminders, bus)

    await reminders.create(content="交周报", remind_at=time.time() - 10, base_at=time.time())
    future = await reminders.create(
        content="还没到", remind_at=time.time() + 3600, base_at=time.time() + 3600
    )

    assert await scheduler.check_once() == 1

    event = queue.get_nowait()
    assert event.type == "reminder"
    assert event.data["content"] == "交周报"

    # 未到点的不应触发
    listed = await reminders.list(status="pending")
    assert [item.id for item in listed] == [future.id]


async def test_reminder_content_is_not_written_to_the_log(reminders, caplog):
    """提醒的**正文不许进日志**（第 88 批，M-23）。

    用户设的提醒常含"吃药""见客户"这类私事，而 `core.log` 有 14 天轮转、
    还可能被用户整包带出去排查问题 —— 那等于把个人事务泄露出去。
    正文已经通过上面那条 `reminder` 事件推给界面了，日志只需要能对上号。

    ⚠️ 这条是**隐私回归钉**：日志里出现正文不算"功能坏了"，没有任何报错，
    所以只能靠用例守住。
    """
    bus = EventBus()
    scheduler = ReminderScheduler(reminders, bus)
    secret = "晚上八点吃降压药，顺便去接孩子"
    record = await reminders.create(
        content=secret, remind_at=time.time() - 10, base_at=time.time()
    )

    with caplog.at_level(logging.INFO):
        assert await scheduler.check_once() == 1

    assert secret not in caplog.text, "提醒正文被写进了日志"
    # 但 id 必须留着：真出问题时得能对上"是哪一条提醒"
    # （`record.id` 是数据库自增主键，int —— 比字符串得先转）
    assert str(record.id) in caplog.text


async def test_fired_reminder_is_not_repeated(reminders):
    bus = EventBus()
    scheduler = ReminderScheduler(reminders, bus)
    await reminders.create(content="只提醒一次", remind_at=time.time() - 1, base_at=time.time())

    assert await scheduler.check_once() == 1
    assert await scheduler.check_once() == 0


async def test_scheduler_without_repository_is_noop():
    scheduler = ReminderScheduler(None, EventBus())
    assert await scheduler.check_once() == 0
    # 没有仓储时 start/stop 也不应抛错
    await scheduler.start()
    await scheduler.stop()


async def test_scheduler_start_and_stop(reminders):
    scheduler = ReminderScheduler(reminders, EventBus(), interval=0.05)
    await scheduler.start()
    await scheduler.start()  # 重复 start 不应起两个任务
    await scheduler.stop()
    await scheduler.stop()  # 重复 stop 也不应抛错


async def test_scheduler_survives_repository_error(reminders, monkeypatch):
    """后台轮询绝不能因为单次查询异常就整体退出。"""
    bus = EventBus()
    scheduler = ReminderScheduler(reminders, bus, interval=0.02)

    calls = {"n": 0}
    original = reminders.due

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("模拟数据库抖动")
        return await original(*args, **kwargs)

    monkeypatch.setattr(reminders, "due", flaky)
    await reminders.create(content="恢复后仍应触发", remind_at=time.time() - 1, base_at=time.time())

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert calls["n"] >= 2, "第一次异常后应继续轮询"
    assert (await reminders.list(status="fired")), "恢复后应成功触发提醒"


async def test_cancelled_reminder_does_not_fire(reminders):
    bus = EventBus()
    scheduler = ReminderScheduler(reminders, bus)
    record = await reminders.create(
        content="已取消", remind_at=time.time() - 1, base_at=time.time()
    )
    await reminders.cancel(record.id)

    assert await scheduler.check_once() == 0
    assert bus.subscriber_count == 0
