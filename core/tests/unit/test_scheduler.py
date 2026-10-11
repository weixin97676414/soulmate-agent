"""定时任务调度。

这里要锁住的都不是"功能有没有"，而是几个**顺序上的不变量** ——
它们出错时的表现都是"偶尔多跑一次"，而多跑一次意味着多花一份 token，
事后从日志里几乎看不出发生过。

"启动补跑"（产品要求）是这块里最容易做错的一件事：
补漏了用户不满意，补多了（跑重、或者翻出一周前的旧账）就是白花钱，
所以下面 ``TestCatchUp`` 把"该补 / 不该补"的每个分叉都钉住了。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from my_agent.agent.scheduler import STATE_FILENAME, STATE_VERSION, TaskScheduler
from my_agent.agent.task_store import describe_schedule
from my_agent.config.schemas import ScheduledTaskSpec


class FakeRuntime:
    """只提供调度器需要的那几个属性。

    ``data_dir`` 给了才有"运行状态落盘"，也才有启动补跑；不给就是纯内存的
    （大多数用例关心的是别的规则，不需要掺进磁盘状态）。
    """

    def __init__(self, tasks: list[ScheduledTaskSpec], data_dir: str | None = None) -> None:
        agent = SimpleNamespace(scheduled_tasks=tasks, scheduler_tick_seconds=60)
        self.config = SimpleNamespace(settings=SimpleNamespace(agent=agent))
        self.paths = SimpleNamespace(data_dir=data_dir)
        self.published: list[tuple[str, dict]] = []
        self.events = SimpleNamespace(publish=self._publish)
        # 操作留痕（"哪个搭子在什么时候做了什么"）：调度器每次执行都会记一条
        self.ops: list[dict] = []
        # ⚠️ 调度器现在**直接调服务**（第 102 批 L-01 收口，不再是 `runtime.record_op`）
        # —— 所以替身长成"有个 audit 门面"，不是"有个 record_op 方法"。
        # 这条替换本身就是那个改动的护栏：将来谁把调用点挪回 runtime，这些用例会立刻
        # 以 AttributeError 炸掉，而不是悄悄少记一条留痕。
        self.audit = SimpleNamespace(op=self._record_op)

    def _publish(self, event_type: str, **data) -> None:
        self.published.append((event_type, data))

    async def _record_op(self, **payload) -> None:
        self.ops.append(payload)


def make_task(**overrides) -> ScheduledTaskSpec:
    payload = {
        "id": "daily",
        "name": "每日汇总",
        "prompt": "汇总一下",
        "interval_minutes": 60,
        "enabled": True,
    }
    payload.update(overrides)
    return ScheduledTaskSpec(**payload)


def make_scheduler(tasks, monkeypatch, data_dir: str | None = None) -> tuple[TaskScheduler, FakeRuntime]:
    runtime = FakeRuntime(tasks, data_dir=data_dir)
    scheduler = TaskScheduler(runtime)

    async def fake_execute(spec, *, resume=None):
        return f"session-{spec.id}"

    monkeypatch.setattr(scheduler, "_execute", fake_execute)
    return scheduler, runtime


class TestStartup:
    @pytest.mark.asyncio
    async def test_no_tasks_means_no_loop(self, monkeypatch):
        """没配置就完全不建常驻协程，也让"到底在不在跑"在日志里一眼可辨。"""
        scheduler, _ = make_scheduler([], monkeypatch)

        await scheduler.start()

        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_no_history_means_seed_only(self, monkeypatch):
        """**没有历史记录**的任务在启动时只播种，不补跑。

        "补跑"的前提是知道它上次什么时候跑的（见 ``TestCatchUp``）。完全没有记录
        就说不清错过了什么 —— 比如刚从旧版本升上来的第一个客户，所有任务都没有记录，
        那时宁可等下一个周期，也不该在用户刚打开客户端时凭空跑一轮。
        """
        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        await scheduler.start()
        await scheduler._tick()

        assert scheduler._catch_up == {}
        assert scheduler.describe()[0]["running"] is False
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_disabled_task_never_fires(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(enabled=False)], monkeypatch)
        await scheduler.start()
        # 把它手工改成"早就该跑了"，仍然不该触发
        scheduler._last_run["daily"] = time.time() - 99999

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        assert runtime.published == []
        await scheduler.stop()


class TestTick:
    @pytest.mark.asyncio
    async def test_due_task_runs(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 3601  # 超过一小时

        await scheduler._tick()
        await _drain()

        assert any(item["running"] is False for item in scheduler.describe())
        assert scheduler.describe()[0]["last_run_at"] is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_reentry_does_not_double_fire(self, monkeypatch):
        """连跑两次 ``_tick`` 不能把同一个任务排进两个并发执行。

        靠的是"**先把 last_run 推到当下，再起任务**"这个顺序。
        反过来的话，任务体里的第一个 await 就会让下一次 tick 看到
        "还没跑过"而再起一个。
        """
        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 3601

        await scheduler._tick()
        await scheduler._tick()

        # 第二次 tick 时 last_run 已经是"刚刚"，不再满足间隔条件
        assert scheduler.describe()[0]["next_run_in_seconds"] > 3000
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_not_yet_due_is_skipped(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task(interval_minutes=60)], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 60  # 才过一分钟

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        await scheduler.stop()


class TestRunNow:
    @pytest.mark.asyncio
    async def test_unknown_task_returns_false(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        assert await scheduler.run_now("nope") is False

    @pytest.mark.asyncio
    async def test_second_click_is_refused_while_running(self, monkeypatch):
        """正在跑时再点"立即执行"要**拒绝**而不是排队。

        排队的语义是"跑完再跑一遍"，而用户点这个按钮是想**现在**看结果；
        而且定时任务会真的花钱，悄悄多跑一次比明确拒绝糟糕得多。
        """
        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        scheduler._running.add("daily")

        assert await scheduler.run_now("daily") is False

    @pytest.mark.asyncio
    async def test_success_publishes_event(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        assert await scheduler.run_now("daily") is True
        await _drain()

        events = [name for name, _ in runtime.published]
        assert "scheduled_task_done" in events
        payload = runtime.published[0][1]
        assert payload["session_id"] == "session-daily"
        # 无人值守的执行**必须留痕**：出问题时没有人在旁边看着，
        # 只能事后按"哪个任务、什么时候、成功还是失败"回查
        assert runtime.ops and runtime.ops[-1]["action"] == "run"
        assert runtime.ops[-1]["target"] == "daily"
        assert runtime.ops[-1]["kind"] == "task"

    @pytest.mark.asyncio
    async def test_failure_publishes_failure_event(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        async def boom(spec):
            raise RuntimeError("模型挂了")

        monkeypatch.setattr(scheduler, "_execute", boom)

        await scheduler.run_now("daily")
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_failed"
        # 失败后必须**释放占位**，否则这个任务此后再也不会被执行
        assert scheduler.describe()[0]["running"] is False


class TestSilent:
    """静默任务（四条「全员进化」）：跑完**不弹窗**，但审计**照写**。

    两半必须一起守：只断言"没弹窗"的话，把通知与留痕一起删掉也能过 ——
    而留痕正是"无人值守的执行要能事后回查"的唯一依靠。用户会看到的差别是
    "上周它到底跑没跑"这件事查不出来。
    """

    @pytest.mark.asyncio
    async def test_done_is_quiet_but_still_recorded(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(silent=True)], monkeypatch)

        assert await scheduler.run_now("daily") is True
        await _drain()

        assert runtime.published == []
        assert runtime.ops[-1]["action"] == "run"
        assert runtime.ops[-1]["target"] == "daily"

    @pytest.mark.asyncio
    async def test_failure_is_quiet_but_still_recorded(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(silent=True)], monkeypatch)

        async def boom(spec):
            raise RuntimeError("模型挂了")

        monkeypatch.setattr(scheduler, "_execute", boom)
        await scheduler.run_now("daily")
        await _drain()

        assert runtime.published == []
        assert runtime.ops[-1]["action"] == "fail"

    @pytest.mark.asyncio
    async def test_loud_task_still_publishes(self, monkeypatch):
        """反向断言：不加这个，"静默"很容易被实现成"所有任务都不弹窗"。"""
        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        await scheduler.run_now("daily")
        await _drain()

        assert [name for name, _ in runtime.published] == ["scheduled_task_done"]


async def _drain() -> None:
    """把 tick 里 create_task 出来的任务跑完。

    多让出几次控制权：任务里可能还有嵌套的 await。
    """
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


def _ts(text: str) -> float:
    """把 ``2026-09-23 09:30`` 变成时间戳，用来做**确定性**的时刻断言。"""
    from datetime import datetime

    return datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()


# --------------------------------------------------------------------------- #
# 时间轴：每天 / 每周
# --------------------------------------------------------------------------- #
class TestTimeTriggers:
    """``daily`` / ``weekly`` 的"到点"判定。

    全部用**固定时刻**而不是 ``time.time()``：跨午夜、跨周边界这些条件只在
    特定时刻才成立，拿真实时间测等于把测试变成"偶尔才跑到的东西"。
    """

    def _pair(self, monkeypatch, **overrides):
        spec = make_task(**overrides)
        scheduler, _ = make_scheduler([spec], monkeypatch)
        return scheduler, spec

    def test_daily_not_due_before_its_time(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-22 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 08:00")) is False

    def test_daily_due_after_its_time(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-22 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 09:30")) is True

    def test_daily_does_not_backfill_today(self, monkeypatch):
        """计时游标落在时间点之后 → 今天那一轮不再触发。

        ⚠️ 这条只管**计时游标**：补跑走的是另一条判定（``_catch_up``，
        见 ``TestCatchUp``）—— 补跑处理的正是"时间点早于游标"的那种情况。
        """
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        # 启动时刻（播种值）落在时间点之后：09:30
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")

        assert scheduler._is_due(spec, _ts("2026-09-23 18:00")) is False

    def test_weekly_only_on_its_weekday(self, monkeypatch):
        # 是周三（weekday=2）
        scheduler, spec = self._pair(monkeypatch, trigger="weekly", at_time="09:00", weekday=2)
        scheduler._last_run[spec.id] = _ts("2026-09-16 09:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 09:30")) is True
        # 刚跑过：同一个时间点不会重复触发
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")
        assert scheduler._is_due(spec, _ts("2026-09-23 20:00")) is False

    def test_weekly_waits_a_week(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="weekly", at_time="09:00", weekday=2)
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")

        # 周四、周五都不是它的日子
        assert scheduler._is_due(spec, _ts("2026-09-24 09:30")) is False
        assert scheduler._is_due(spec, _ts("2026-09-25 09:30")) is False

    def test_next_run_countdown_skips_finished_occurrence(self, monkeypatch):
        """界面上的倒计时必须指向**下一个**时间点，而不是刚过去的那个。"""
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:10")

        remaining = scheduler._next_run_in_seconds(spec, _ts("2026-09-23 10:00"))

        assert 22 * 3600 < remaining < 23.5 * 3600, "应当指向明天 09:00"


# --------------------------------------------------------------------------- #
# 间隔型的起始时间
# --------------------------------------------------------------------------- #
class TestStartAt:
    """``interval`` 的起始时间（产品要求）。

    语义：到 ``start_at`` 之前**一次都不跑**；到点就是第一次执行，之后按间隔重复。
    全部用固定时刻，理由与 ``TestTimeTriggers`` 一样。
    """

    def _pair(self, monkeypatch, **overrides):
        spec = make_task(**overrides)
        scheduler, _ = make_scheduler([spec], monkeypatch)
        return scheduler, spec

    def test_not_due_before_start(self, monkeypatch):
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 09:59")) is False

    def test_first_run_is_exactly_at_start(self, monkeypatch):
        """起始时间一到就**立刻**跑，不许被"播种时刻 + 一个间隔"推迟。

        真实场景：用户 09:55 建了"10:00 起每 30 分钟"的任务，启动时游标被播种成
        09:55 —— 若只看 `now - last >= 间隔`，第一次执行会滑到 10:25，
        用户看到的是"起始时间过了却没动静"。
        """
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:55")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:00")) is True

    def test_waits_a_full_interval_after_start(self, monkeypatch):
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:29")) is False
        assert scheduler._is_due(spec, _ts("2026-09-30 10:30")) is True

    def test_empty_start_keeps_old_behaviour(self, monkeypatch):
        """没设起始时间 = 从现在起算，与加这个字段之前完全一样（老配置兼容）。"""
        scheduler, spec = self._pair(monkeypatch, trigger="interval", interval_minutes=60)
        assert spec.start_at == ""
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:30")) is False
        assert scheduler._is_due(spec, _ts("2026-09-30 11:00")) is True

    def test_countdown_points_at_start(self, monkeypatch):
        """起始时间还没到时，界面上的倒计时指着**起始时间**。"""
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:00")

        assert scheduler._next_run_in_seconds(spec, _ts("2026-09-30 09:40")) == 20 * 60

    def test_future_start_is_never_treated_as_missed(self, monkeypatch):
        """起始时间还没到 → 不算"错过了"，否则刚建的任务一启动就会被补跑一次。"""
        spec = make_task(
            id="hourly", trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler, _ = make_scheduler([spec], monkeypatch)
        scheduler._first_seen[spec.id] = _ts("2026-09-30 08:00")

        assert scheduler._overdue_point(spec, _ts("2026-09-30 09:00")) is None

    def test_bad_start_at_is_ignored(self, monkeypatch):
        """配置是用户手也改得动的文件：一行写坏的时间只能被忽略，不能让任务彻底不跑。"""
        scheduler, spec = self._pair(monkeypatch, trigger="interval", interval_minutes=60)
        spec.start_at = "2026-09-30 10:00"  # 少了 T：手改 settings.json 写坏的样子
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._start_point(spec) is None
        assert scheduler._is_due(spec, _ts("2026-09-30 11:00")) is True

    def test_schema_rejects_bad_format(self):
        """格式不对由 schema 当场拦下 —— 别等到调度器里才发现它永远算不出"下次"。"""
        with pytest.raises(ValueError):
            make_task(start_at="2026/09/30 10:00")

    def test_describe_mentions_start(self):
        """人话里必须写出起始时间，否则界面上完全没有"为什么还不跑"的线索。"""
        spec = make_task(trigger="interval", interval_minutes=120, start_at="2026-09-30T10:03")

        assert describe_schedule(spec) == "自 2026年9月30日 10:03 起，每 2 小时"


# --------------------------------------------------------------------------- #
# 启动补跑：关着的时候错过的那一次
# --------------------------------------------------------------------------- #
def _hhmm(ts: float) -> str:
    """把时间戳变成 ``HH:MM``。

    用它构造"今天已经过去、又落在 24 小时窗口里"的时间点，这样测试
    不会因为"跑在几点"而时灵时不灵（固定写 09:00 的话，凌晨跑就是另一种情形）。
    """
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class TestCatchUp:
    """启动补跑（产品要求）。

    口径：**只补最近一次**、错过超过 24 小时不补、已经跑过的不重复。
    这一组里每一条都对应一次真实的"多花钱"或"该跑没跑"。
    """

    def _state(self, tmp_path, task_id: str = "daily", **entries: float) -> None:
        """造一份运行状态文件，等价于"上一次运行留下的记录"。"""
        (tmp_path / STATE_FILENAME).write_text(
            json.dumps({"version": STATE_VERSION, "tasks": {task_id: entries}}),
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_missed_daily_is_caught_up_once(self, monkeypatch, tmp_path):
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()

        assert spec.id in scheduler._catch_up, "两小时前那一次没跑过，应当补"

        await scheduler._tick()
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_done"
        # 补跑必须**说清楚**：用户刚打开客户端就冒出一条"任务已完成"，
        # 不写"这是补上次错过的那一轮"，看起来就像任务自己在乱跑
        assert "补跑" in runtime.published[0][1]["message"]
        assert "补跑" in runtime.ops[-1]["detail"]
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_missed_silent_task_is_caught_up_quietly(self, monkeypatch, tmp_path):
        """静默任务补跑：活儿照干，连"补跑"这件事也不弹窗。

        「全员进化」四条正是这个组合 —— 用户打开客户端时最不希望看到的
        就是四条"补跑完成"的弹窗。
        """
        now = time.time()
        spec = make_task(silent=True, interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 3 * 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up, "关着的时候错过的那一轮应当补"
        await scheduler._tick()
        await _drain()

        assert runtime.published == []
        # 但事后要能查出来这一轮是补跑（和上面那条有通知的用例同一个判据）
        assert "补跑" in runtime.ops[-1]["detail"]
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_already_ran_before_restart_is_not_caught_up(self, monkeypatch, tmp_path):
        """今天那一次在**重启之前**已经跑过了 → 不能因为重启再跑一遍。

        这是补跑最容易出的错，用户看到的症状是"为什么刚开机又跑一遍"。
        """
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_overdue_is_caught_up_and_recounted(self, monkeypatch, tmp_path):
        """间隔型也算过期：关了 5 小时、间隔 1 小时 → 补一次，然后重新计时。"""
        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 3 * 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up

        await scheduler._tick()
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_done"
        # 补跑完要**重新计时**（下一个检查点是完整的一小时之后），
        # 否则下一次 tick 会立刻又跑一遍
        assert 3500 < scheduler.describe()[0]["next_run_in_seconds"] <= 3600
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_just_ran_is_not_caught_up(self, monkeypatch, tmp_path):
        """刚跑完十分钟就重启（崩溃重启、装完补丁重启）不该再补一轮。"""
        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_missed_too_long_ago_is_not_caught_up(self, monkeypatch, tmp_path):
        """错过太久（超过 24 小时）就不补 —— 一周前的那一轮现在跑没有意义，白花钱。"""
        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 9 * 86400, last_run_at=now - 5 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_weekly_missed_two_days_ago_is_not_caught_up(self, monkeypatch, tmp_path):
        """每周型的**已知代价**：错过超过 24 小时就不补，于是要等下周。

        24 小时窗口是用户选的口径（"更久远的直接跳过、等下一个周期"）。
        这条测试的作用是把代价写明白：以后若要把窗口放宽成"每周型按周算"，
        改这里，而不是让它悄悄变。
        """
        now = time.time()
        spec = make_task(
            trigger="weekly",
            at_time=_hhmm(now - 2 * 3600),
            weekday=(datetime.fromtimestamp(now).weekday() - 2) % 7,
        )
        self._state(tmp_path, first_seen_at=now - 30 * 86400, last_run_at=now - 20 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_new_task_is_not_caught_up(self, monkeypatch, tmp_path):
        """状态文件里没有的任务（刚建的、或刚升级上来的）→ 只播种，不补跑。"""
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_condition_task_only_rebuilds_baseline(self, monkeypatch, tmp_path):
        """带条件的任务补跑时只重建基线，**不执行**。

        重启后条件的第一眼永远只是"记住现在长什么样"；把它当成"内容变了"，
        等于每次开客户端都白跑一轮。
        """
        import my_agent.utils.http as http_module

        holder = {"body": b"<html>v1</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        now = time.time()
        spec = make_task(
            trigger="daily",
            at_time=_hhmm(now - 2 * 3600),
            condition="url_changed",
            condition_target="https://example.com/feed",
        )
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up

        await scheduler._tick()
        await _drain()
        assert runtime.published == []

        # 补跑机会只有一次：第二轮回它不该再试
        assert scheduler._catch_up == {}
        await scheduler._tick()
        await _drain()
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_manual_run_also_marks_handled(self, monkeypatch, tmp_path):
        """用户手动点过"立即执行"也算这一刻接管了：重启不能再补一遍。"""
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))

        first, _ = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await first.start()
        assert await first.run_now(spec.id) is True
        await _drain()
        await first.stop()
        handled_at = first._last_exec[spec.id]

        second, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await second.start()
        await second._tick()
        await _drain()

        assert second._catch_up == {}
        assert runtime.published == []
        # "上次执行"来自落盘记录，不是重启时被重新播种的"刚刚" ——
        # 否则界面上每个任务都会显示成刚跑过
        assert second.describe()[0]["last_run_at"] == handled_at
        await second.stop()

    @pytest.mark.asyncio
    async def test_catch_up_is_not_repeated_across_restarts(self, monkeypatch, tmp_path):
        """补跑过的那一轮会被写进状态文件，所以"再重启一次"不会又补一遍。"""
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)

        first, _ = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await first.start()
        await first._tick()
        await _drain()
        await first.stop()

        second, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await second.start()
        await second._tick()
        await _drain()

        assert second._catch_up == {}
        assert runtime.published == []
        await second.stop()

    @pytest.mark.asyncio
    async def test_corrupt_state_file_does_not_break_startup(self, monkeypatch, tmp_path):
        """状态文件坏掉顶多让这次不补跑，绝不能让调度器（乃至整个应用）起不来。"""
        (tmp_path / STATE_FILENAME).write_text("{ 这不是 JSON", encoding="utf-8")
        scheduler, _ = make_scheduler([make_task()], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()

        assert scheduler.running is True
        assert scheduler._catch_up == {}
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_unknown_state_version_is_discarded(self, monkeypatch, tmp_path):
        """版本不认识 → 整份丢掉（猜错字段形状会让该跑的任务永远不跑）。"""
        now = time.time()
        (tmp_path / STATE_FILENAME).write_text(
            json.dumps({"version": 999, "tasks": {"daily": {"last_run_at": now - 86400}}}),
            encoding="utf-8",
        )
        scheduler, _ = make_scheduler(
            [make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))],
            monkeypatch,
            data_dir=str(tmp_path),
        )

        await scheduler.start()

        assert scheduler._catch_up == {}
        await scheduler.stop()


# --------------------------------------------------------------------------- #
# 条件触发：网页有变化 / 文件有更新
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.content = body

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int | None = None):
        """按片吐字节。

        ⚠️ 第 91 批（L-10）之后 `_url_changed` 走的是 `client.stream(...)` +
        `aiter_bytes()`（**边读边算、读到上限就停**，避免把整个响应体读进内存），
        所以替身也得按流式接口来 —— 只实现 `get` 的话，这里会以 AttributeError
        被条件检查的兜底吞掉，表现成"条件一律不满足"（两条用例就是这么红的）。
        """
        # 特意切成两片：一次吐完的话，"超过上限就停下"那条路径永远走不到
        half = max(1, len(self.content) // 2)
        yield self.content[:half]
        if self.content[half:]:
            yield self.content[half:]


class _FakeStream:
    """`client.stream(...)` 的返回值（异步上下文管理器）。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aenter__(self) -> _FakeResponse:
        return _FakeResponse(self._body)

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeClient:
    """最小可用的 httpx.AsyncClient 替身。"""

    def __init__(self, holder: dict[str, bytes]) -> None:
        self._holder = holder

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self._holder["body"])

    def stream(self, method: str, url: str) -> _FakeStream:
        # httpx 的 `client.stream(...)` **不是**协程，是直接返回上下文管理器
        return _FakeStream(self._holder["body"])


class TestConditions:
    @pytest.mark.asyncio
    async def test_no_condition_always_passes(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        assert await scheduler._condition_met(scheduler._specs()[0]) is True

    @pytest.mark.asyncio
    async def test_url_condition_needs_a_real_change(self, monkeypatch):
        import my_agent.utils.http as http_module

        holder = {"body": b"<html>v1</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        spec = make_task(condition="url_changed", condition_target="https://example.com/feed")
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        # 第一次只看一眼、记住现状：否则"新建监控任务"这个动作本身就会跑一轮
        assert await scheduler._condition_met(spec) is False
        assert await scheduler._condition_met(spec) is False

        holder["body"] = "<html>v2 有更新</html>".encode()

        assert await scheduler._condition_met(spec) is True
        assert runtime.published == [], "内容变了不是失败，不该推失败通知"

    @pytest.mark.asyncio
    async def test_url_condition_only_reads_up_to_the_cap(self, monkeypatch, caplog):
        """只读到上限为止，且日志要**如实说明"已截断"**（第 91 批，L-10）。

        为什么值得单独钉：
        * **内存上限**：目标地址是用户填的，以前是把整个响应体读进内存再哈希 ——
          一个几 GB 的地址就能把内存吃满，而这条路径是应用自己在后台跑的，
          用户不在场、看到的只是"客户端越来越卡"；
        * **日志如实**：截断之后"2MB 之后的内容改了"确实检测不到。不说清楚的话，
          下一个人会把它当成"抓取失败/条件坏了"去查一个根本不存在的问题。
        """
        import logging

        import my_agent.utils.http as http_module
        from my_agent.agent.scheduler import CONDITION_MAX_BYTES

        holder = {"body": b"<html>" + b"x" * CONDITION_MAX_BYTES + b"</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        spec = make_task(condition="url_changed", condition_target="https://example.com/big")
        scheduler, _ = make_scheduler([spec], monkeypatch)

        with caplog.at_level(logging.INFO):
            assert await scheduler._condition_met(spec) is False  # 第一眼只建基线
        assert "已截断" in caplog.text, "截断必须写进日志，否则事后会当成抓取失败去查"

        # 只改**上限之后**的内容 → 检测不到（这是刻意的代价，写在这里免得被当成 bug）
        holder["body"] = holder["body"] + b"<!-- changed far beyond the cap -->"
        assert await scheduler._condition_met(spec) is False

        # 改**上限之内**的内容 → 必须能检测到
        holder["body"] = b"<htmX>" + holder["body"][6:]
        assert await scheduler._condition_met(spec) is True

    @pytest.mark.asyncio
    async def test_url_condition_rejects_metadata_address(self, monkeypatch):
        """监控地址同样要过 SSRF 校验 —— 模型能自建任务，等于多了一条探测内网的路。"""
        spec = make_task(
            condition="url_changed",
            condition_target="http://169.254.169.254/latest/meta-data/",
        )
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        assert await scheduler._condition_met(spec) is False
        assert runtime.published[-1][0] == "scheduled_task_failed"

    @pytest.mark.asyncio
    async def test_condition_failure_is_reported_only_once(self, monkeypatch):
        """同一个原因只提示一次：否则每个检查点刷一条通知，用户就不看了。"""
        spec = make_task(condition="file_changed", condition_target="D:/根本不存在的目录/x.txt")
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        await scheduler._condition_met(spec)
        await scheduler._condition_met(spec)

        events = [name for name, _ in runtime.published]
        assert events.count("scheduled_task_failed") == 1

    @pytest.mark.asyncio
    async def test_file_condition_needs_an_update(self, monkeypatch, tmp_path):
        target = tmp_path / "report.txt"
        target.write_text("v1", encoding="utf-8")
        spec = make_task(condition="file_changed", condition_target=str(target))
        scheduler, _ = make_scheduler([spec], monkeypatch)

        assert await scheduler._condition_met(spec) is False
        assert await scheduler._condition_met(spec) is False

        target.write_text("v2 更长的内容", encoding="utf-8")

        assert await scheduler._condition_met(spec) is True


class TestTickWithCondition:
    @pytest.mark.asyncio
    async def test_gated_tick_advances_the_clock(self, monkeypatch):
        """条件未满足时也要推进时间点。

        不推进的话，用户配的"每 30 分钟看一眼"会退化成"每个 tick（60 秒）
        都去抓一次人家的站点"。
        """
        spec = make_task(condition="url_changed", condition_target="https://example.com/a")
        scheduler, _ = make_scheduler([spec], monkeypatch)
        await scheduler.start()
        scheduler._last_run[spec.id] = time.time() - 3601

        async def not_yet(_spec) -> bool:
            return False

        monkeypatch.setattr(scheduler, "_condition_met", not_yet)

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        assert scheduler.describe()[0]["next_run_in_seconds"] > 3000
        await scheduler.stop()


# --------------------------------------------------------------------------- #
# 配置变更后重起调度
# --------------------------------------------------------------------------- #
class TestSessionOwner:
    """任务跑出来的会话挂在哪个搭子下面。

    这条决定了**用户能不能找到结果**：左侧会话列表按当前搭子过滤
    （`SessionList.tsx`），而 `assistant_id` 为空串的会话在任何搭子被选中时
    都匹配不上 —— 通知说"结果在新会话里"，用户翻遍列表却什么都没有。
    """

    class _Assistant:
        def __init__(self, assistant_id: str, sort_order: int = 0) -> None:
            self.id = assistant_id
            self.name = assistant_id
            self.sort_order = sort_order

    class _Assistants:
        def __init__(self, items, default: str = "") -> None:
            self.assistants = items
            self.default_assistant = default

        def get(self, assistant_id: str):
            return next((item for item in self.assistants if item.id == assistant_id), None)

        def sorted(self):
            return sorted(self.assistants, key=lambda item: item.sort_order)

    def _runtime(self, items, default: str = ""):
        assistants = self._Assistants(items, default)
        return SimpleNamespace(
            assistants=assistants,
            resolve_assistant=lambda assistant_id: assistants.get(assistant_id)
            if assistant_id
            else None,
        )

    def _scheduler(self) -> TaskScheduler:
        return TaskScheduler(SimpleNamespace())

    def test_uses_the_task_assistant_when_it_exists(self):
        runtime = self._runtime([self._Assistant("a"), self._Assistant("b", 1)], default="a")

        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="b")).id == "b"

    def test_falls_back_to_default_when_assistant_is_missing(self):
        runtime = self._runtime([self._Assistant("a"), self._Assistant("b", 1)], default="b")

        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="被删掉的")).id == "b"
        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="")).id == "b"

    def test_falls_back_to_first_assistant_without_a_default(self):
        runtime = self._runtime([self._Assistant("later", 5), self._Assistant("first", 1)])

        assert self._scheduler()._resolve_runner(runtime, make_task()).id == "first"

    def test_no_assistant_at_all_keeps_it_empty(self):
        """一个搭子都没有时保持为空：此时列表**不过滤**，会话照样看得见。"""
        runtime = self._runtime([])

        assert self._scheduler()._resolve_runner(runtime, make_task()) is None


class TestRestart:
    @pytest.mark.asyncio
    async def test_keeps_existing_timers_and_drops_removed(self, monkeypatch):
        """改一个任务不能让**所有**任务重新计时 —— 那等于集体补跑一次（真花钱）。"""
        first = make_task(id="a", name="甲")
        second = make_task(id="b", name="乙")
        scheduler, runtime = make_scheduler([first, second], monkeypatch)
        await scheduler.start()
        stamp = time.time() - 1000
        scheduler._last_run["a"] = stamp
        scheduler._last_run["b"] = stamp

        runtime.config.settings.agent.scheduled_tasks = [first]
        await scheduler.restart()

        assert scheduler._last_run["a"] == stamp
        assert "b" not in scheduler._last_run
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_new_task_starts_from_now(self, monkeypatch):
        """刚建好的任务不该马上开跑：用户的预期是"到下一个时间点再说"。"""
        first = make_task(id="a")
        scheduler, runtime = make_scheduler([first], monkeypatch)
        await scheduler.start()
        fresh = make_task(id="c", name="新的")
        runtime.config.settings.agent.scheduled_tasks = [first, fresh]

        await scheduler.restart()

        assert "c" in scheduler._last_run
        assert scheduler._next_run_in_seconds(fresh, time.time()) > 3000
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_restart_starts_the_loop_when_first_task_appears(self, monkeypatch):
        """空配置时调度器根本不建协程；加了第一个任务后必须**真的**跑起来。"""
        scheduler, runtime = make_scheduler([], monkeypatch)
        await scheduler.start()
        assert scheduler.running is False

        runtime.config.settings.agent.scheduled_tasks = [make_task()]
        await scheduler.restart()

        assert scheduler.running is True
        await scheduler.stop()
