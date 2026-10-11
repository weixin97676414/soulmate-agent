"""定时任务技能（搭子自己建 / 查 / 改 / 删 / 立刻跑）。

用户要求里的"搭子自建技能"就是这组用例守的东西。它们比普通技能更需要测试，
因为**错了不会报错**：任务建出来但字段没落上、修改时把没提的字段清空、
删掉的是另一个任务 —— 这些在界面上看起来都"正常"，只有到点不跑才会暴露。

这里用的是真实 ``ScheduledTaskStore`` + 假 runtime：门面那一层的字段合并逻辑
（"只改传进来的字段"）正是最容易写错的地方，拿假 store 测等于没测。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from my_agent.agent.task_store import ScheduledTaskStore, describe_schedule
from my_agent.config.schemas import ScheduledTaskSpec
from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.task_tools import (
    ScheduledTaskCreateSkill,
    ScheduledTaskDeleteSkill,
    ScheduledTaskListSkill,
    ScheduledTaskRunSkill,
    ScheduledTaskUpdateSkill,
)


class FakeRuntime:
    """只提供任务门面需要的那几样。"""

    def __init__(self) -> None:
        self.agent_settings = SimpleNamespace(scheduled_tasks=[])
        self.config = SimpleNamespace(settings=SimpleNamespace(agent=self.agent_settings))
        self.saved: list[list[ScheduledTaskSpec]] = []
        self.run_now_calls: list[str] = []
        self.run_now_result = True
        self.task_scheduler = SimpleNamespace(run_now=self._run_now)

    async def _run_now(self, task_id: str) -> bool:
        self.run_now_calls.append(task_id)
        return self.run_now_result

    async def save_scheduled_tasks(self, specs: list[ScheduledTaskSpec]) -> list[ScheduledTaskSpec]:
        self.agent_settings.scheduled_tasks = list(specs)
        self.saved.append(list(specs))
        return list(specs)


def make_ctx(runtime: FakeRuntime) -> SkillContext:
    return SkillContext(
        session_id="s1",
        assistant_id="buddy-1",
        extra={"tasks": ScheduledTaskStore(runtime)},
    )


# --------------------------------------------------------------------------- #
# 时间描述
# --------------------------------------------------------------------------- #
class TestDescribeSchedule:
    def _spec(self, **overrides) -> ScheduledTaskSpec:
        payload = {"id": "t1", "name": "任务", "prompt": "做事"}
        payload.update(overrides)
        return ScheduledTaskSpec(**payload)

    def test_weekly_and_daily(self):
        assert describe_schedule(self._spec(trigger="daily", at_time="09:00")) == "每天 09:00"
        assert (
            describe_schedule(self._spec(trigger="weekly", at_time="08:30", weekday=2))
            == "每周三 08:30"
        )

    def test_interval_renders_hours_when_it_divides(self):
        assert describe_schedule(self._spec(interval_minutes=90)) == "每 90 分钟"
        assert describe_schedule(self._spec(interval_minutes=120)) == "每 2 小时"
        assert describe_schedule(self._spec(interval_minutes=30)) == "每 30 分钟"

    def test_condition_is_spelled_out(self):
        text = describe_schedule(
            self._spec(condition="url_changed", condition_target="https://example.com/a")
        )
        assert "https://example.com/a" in text and "变化" in text

        text = describe_schedule(
            self._spec(condition="file_changed", condition_target="D:/a/report.xlsx")
        )
        assert "D:/a/report.xlsx" in text and "更新" in text


# --------------------------------------------------------------------------- #
# 建 / 改 / 删 / 跑
# --------------------------------------------------------------------------- #
class TestTaskCreateSkill:
    @pytest.mark.asyncio
    async def test_creates_enabled_task_and_uses_current_buddy(self):
        runtime = FakeRuntime()

        result = await ScheduledTaskCreateSkill().run(
            make_ctx(runtime),
            name="早报",
            prompt="汇总今天的行业新闻",
            trigger="daily",
            at_time="08:30",
        )

        assert result["schedule"] == "每天 08:30"
        assert result["enabled"] is True
        stored = runtime.agent_settings.scheduled_tasks
        assert len(stored) == 1
        assert stored[0].id == result["id"]
        # 没指定搭子时应当落到"当前这个搭子"，而不是留空
        assert stored[0].assistant_id == "buddy-1"

    @pytest.mark.asyncio
    async def test_created_task_is_marked_as_created_by_the_buddy(self):
        """技能建的任务要标成 ``origin="agent"``。

        少了这一句，给**内置搭子**建的任务会被当成"用户建的"—— 用户随手就能
        关掉或删掉它在用的那条，而这道锁的整个意义就是"这几条不能手动改"。
        """
        runtime = FakeRuntime()

        await ScheduledTaskCreateSkill().run(
            make_ctx(runtime), name="全员进化中 Soulmate", prompt="整理记忆"
        )

        stored = runtime.agent_settings.scheduled_tasks[0]
        assert stored.origin == "agent"
        assert stored.assistant_id == "buddy-1"

    @pytest.mark.asyncio
    async def test_condition_without_target_is_rejected(self):
        runtime = FakeRuntime()

        with pytest.raises(SkillExecutionError) as excinfo:
            await ScheduledTaskCreateSkill().run(
                make_ctx(runtime),
                name="盯网页",
                prompt="看看有没有新公告",
                condition="url_changed",
                condition_target="",
            )

        assert "网页地址" in str(excinfo.value)
        assert runtime.agent_settings.scheduled_tasks == []

    @pytest.mark.asyncio
    async def test_bad_time_is_reported_as_task_error(self):
        """25:00 这种时刻必须当场被拒，而不是建好之后永远不触发。"""
        runtime = FakeRuntime()

        with pytest.raises(SkillExecutionError):
            await ScheduledTaskCreateSkill().run(
                make_ctx(runtime), name="错的", prompt="做事", trigger="daily", at_time="25:00"
            )


class TestTaskUpdateSkill:
    def _seed(self, runtime: FakeRuntime) -> None:
        runtime.agent_settings.scheduled_tasks = [
            ScheduledTaskSpec(
                id="t1",
                name="早报",
                prompt="汇总新闻",
                trigger="daily",
                at_time="08:30",
                assistant_id="buddy-1",
                enabled=True,
            )
        ]

    @pytest.mark.asyncio
    async def test_only_given_fields_change(self):
        runtime = FakeRuntime()
        self._seed(runtime)

        result = await ScheduledTaskUpdateSkill().run(make_ctx(runtime), task_id="t1", at_time="07:00")

        stored = runtime.agent_settings.scheduled_tasks[0]
        assert stored.at_time == "07:00"
        # 没提的字段必须原样保留 —— 覆盖式更新会把用户的指令悄悄清空
        assert stored.prompt == "汇总新闻"
        assert stored.name == "早报"
        assert result["changed"] == ["at_time"]

    @pytest.mark.asyncio
    async def test_can_disable_without_touching_other_fields(self):
        runtime = FakeRuntime()
        self._seed(runtime)

        await ScheduledTaskUpdateSkill().run(make_ctx(runtime), task_id="t1", enabled=False)

        stored = runtime.agent_settings.scheduled_tasks[0]
        assert stored.enabled is False
        assert stored.at_time == "08:30"

    @pytest.mark.asyncio
    async def test_unknown_task_is_reported(self):
        runtime = FakeRuntime()

        with pytest.raises(SkillExecutionError) as excinfo:
            await ScheduledTaskUpdateSkill().run(make_ctx(runtime), task_id="nope", name="新的")

        assert "没有找到" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_empty_change_set_is_rejected(self):
        runtime = FakeRuntime()
        self._seed(runtime)

        with pytest.raises(SkillExecutionError):
            await ScheduledTaskUpdateSkill().run(make_ctx(runtime), task_id="t1")


class TestTaskDeleteSkill:
    @pytest.mark.asyncio
    async def test_deletes_only_target(self):
        runtime = FakeRuntime()
        runtime.agent_settings.scheduled_tasks = [
            ScheduledTaskSpec(id="t1", name="甲", prompt="a"),
            ScheduledTaskSpec(id="t2", name="乙", prompt="b"),
        ]

        await ScheduledTaskDeleteSkill().run(make_ctx(runtime), task_id="t1")

        remaining = [item.id for item in runtime.agent_settings.scheduled_tasks]
        assert remaining == ["t2"]

    @pytest.mark.asyncio
    async def test_unknown_task_is_reported(self):
        runtime = FakeRuntime()

        with pytest.raises(SkillExecutionError):
            await ScheduledTaskDeleteSkill().run(make_ctx(runtime), task_id="nope")


class TestTaskRunSkill:
    @pytest.mark.asyncio
    async def test_runs_now(self):
        runtime = FakeRuntime()
        runtime.agent_settings.scheduled_tasks = [
            ScheduledTaskSpec(id="t1", name="早报", prompt="汇总")
        ]

        result = await ScheduledTaskRunSkill().run(make_ctx(runtime), task_id="t1")

        assert runtime.run_now_calls == ["t1"]
        assert "早报" in result["message"]

    @pytest.mark.asyncio
    async def test_refuses_while_already_running(self):
        runtime = FakeRuntime()
        runtime.run_now_result = False
        runtime.agent_settings.scheduled_tasks = [
            ScheduledTaskSpec(id="t1", name="早报", prompt="汇总")
        ]

        with pytest.raises(SkillExecutionError) as excinfo:
            await ScheduledTaskRunSkill().run(make_ctx(runtime), task_id="t1")

        assert "正在执行" in str(excinfo.value)


class TestTaskListSkill:
    @pytest.mark.asyncio
    async def test_lists_with_schedule_and_full_prompt(self):
        runtime = FakeRuntime()
        long_prompt = "很长的指令" * 80
        runtime.agent_settings.scheduled_tasks = [
            ScheduledTaskSpec(id="t1", name="早报", prompt=long_prompt, trigger="daily")
        ]

        result = await ScheduledTaskListSkill().run(make_ctx(runtime), include_disabled=True)

        assert result["count"] == 1
        item = result["tasks"][0]
        assert item["schedule"] == "每天 09:00"
        # 给模型的必须是**完整**指令（零省略原则），preview 只是顺手给的摘要
        assert item["prompt"] == long_prompt
