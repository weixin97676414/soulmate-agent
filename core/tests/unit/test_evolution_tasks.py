"""「全员进化」四条预置任务的**播种**与**锁定判定**。

这两件事都"错了也不会报错"，所以单独守：

- **起始时间的时区**：用 UTC 拼字符串，东八区用户会看到"早 8 小时"的起始时间 ——
  任务照样建得出来、照样会跑，只是跑的时刻不是用户以为的那个。
- **错峰**：四条落在同一分钟也能跑，代价是四个搭子同时调模型（排队 + 费用堆在同一刻）。
- **幂等**：启动时再播一次，用户改过的时间、搭子改过的一切都不能被抹回去。
- **锁定只锁该锁的**：漏锁 = 闸门不存在；多锁 = 用户自己建的任务开关点不动，
  而那种症状查不出原因（界面正常、只是没反应）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from my_agent.agent.evolution_tasks import (
    BUILTIN_TASK_ID_PREFIX,
    STAGGER_MINUTES,
    WEEK_MINUTES,
    builtin_specs,
    ensure_builtin_tasks,
    first_run_at,
    task_id,
)
from my_agent.agent.task_store import locked_for_user
from my_agent.config.schemas import AssistantProfile, ScheduledTaskSpec

#: 是**周二** → 下一个周日是 
TUESDAY = datetime(2026, 9, 29, 10, 0).timestamp()


def make_profile(assistant_id: str, name: str = "", **overrides) -> AssistantProfile:
    payload = {"id": assistant_id, "name": name or assistant_id, "sort_order": 100}
    payload.update(overrides)
    return AssistantProfile(**payload)


class TestFirstRunAt:
    """起始时间锚点：安装后第一个**周日 03:07**（L0 时刻）。"""

    def test_next_sunday_after_a_weekday_install(self):
        assert first_run_at(TUESDAY, 0) == "2026-10-04T03:07"

    def test_sunday_before_the_anchor_runs_the_same_day(self):
        """周日凌晨装（还没到 03:07）→ 当天就能看到它跑一次，不用等一周。"""
        assert first_run_at(datetime(2026, 10, 4, 1, 0).timestamp(), 0) == "2026-10-04T03:07"

    def test_sunday_after_the_anchor_waits_a_week(self):
        assert first_run_at(datetime(2026, 10, 4, 5, 0).timestamp(), 0) == "2026-10-11T03:07"

    def test_stagger_is_added_after_the_anchor(self):
        """错峰必须在锚点**之后**加。

        反过来的写法（先加分钟、再 ``replace(hour=3, minute=7)``）会把错峰整个抹掉，
        四条任务全落在 03:07 —— 实测踩过，而症状只是"四个搭子同时开始跑"。
        """
        assert first_run_at(TUESDAY, STAGGER_MINUTES) == "2026-10-04T03:22"
        assert first_run_at(TUESDAY, 4 * STAGGER_MINUTES) == "2026-10-04T04:07"
        # 再往后一条：时刻要连续进位，不能被"锚点"吸回去
        assert first_run_at(TUESDAY, 5 * STAGGER_MINUTES) == "2026-10-04T04:22"


class TestBuiltinSpecs:
    def _profiles(self) -> list[AssistantProfile]:
        # sort_order 决定错峰顺序（也是搭子在界面上的固定顺序）
        return [
            make_profile("soulmate", "Soulmate", sort_order=10),
            make_profile("LoveBuddy", "Love Buddy", sort_order=20),
            make_profile("RelationBuddy", "Relation Buddy", sort_order=30),
            make_profile("BuddyManager", "Buddy Manager", sort_order=40),
            # 自建搭子：**不预置**（它走"自己问用户要不要建"那条路）
            make_profile("my-own", "我的搭子", sort_order=50),
        ]

    def test_only_builtin_buddies_get_a_task(self):
        specs = builtin_specs(self._profiles(), now=TUESDAY)

        assert [item.assistant_id for item in specs] == [
            "soulmate",
            "LoveBuddy",
            "RelationBuddy",
            "BuddyManager",
        ]
        assert all(item.id.startswith(BUILTIN_TASK_ID_PREFIX) for item in specs)
        assert task_id("soulmate") in [item.id for item in specs]

    def test_fields_are_the_agreed_ones(self):
        first = builtin_specs(self._profiles(), now=TUESDAY)[0]

        assert first.name == "全员进化中 Soulmate"
        assert first.trigger == "interval"
        assert first.interval_minutes == WEEK_MINUTES == 10080
        assert first.enabled is True, "用户口径是「内置搭子我们创建好自动进化」"
        assert first.silent is True, "每周自己跑一次，没必要次次弹窗"
        assert first.origin == "builtin", "预置任务用户不能改/关/删"
        assert first.start_at == "2026-10-04T03:07"
        # 四个搭子共用同一篇指令，所以必须指名道姓，否则拿到的是同一份"你是谁"
        assert "Soulmate" in first.prompt

    def test_start_times_are_staggered(self):
        specs = builtin_specs(self._profiles(), now=TUESDAY)
        stamps = [item.start_at for item in specs]

        assert len(set(stamps)) == 4, "四条不能落在同一分钟"
        moments = [datetime.strptime(item, "%Y-%m-%dT%H:%M") for item in stamps]
        gaps = [
            (later - earlier).total_seconds() / 60
            for earlier, later in zip(moments, moments[1:], strict=False)
        ]
        assert gaps == [STAGGER_MINUTES] * 3

    def test_nickname_wins_over_name(self):
        profiles = [make_profile("soulmate", "Soulmate", nickname="  小灵  ", sort_order=10)]

        assert builtin_specs(profiles, now=TUESDAY)[0].name == "全员进化中 小灵"

    def test_no_builtin_buddies_means_no_task(self):
        assert builtin_specs([make_profile("my-own", "我的搭子")], now=TUESDAY) == []


class TestEnsureBuiltinTasks:
    def test_only_missing_ones_are_added(self):
        existing = [ScheduledTaskSpec(id="task-1", name="用户的早报", prompt="汇总")]
        profiles = [make_profile("soulmate", "Soulmate", sort_order=10)]

        result = ensure_builtin_tasks(existing, profiles, now=TUESDAY)

        assert [item.id for item in result] == ["task-1", task_id("soulmate")]
        # 用户那条**原样保留**（顺序也不动）
        assert result[0] is existing[0]

    def test_nothing_missing_returns_the_same_list(self):
        existing = [
            ScheduledTaskSpec(id=task_id("soulmate"), name="全员进化中 Soulmate", prompt="x")
        ]

        assert ensure_builtin_tasks(existing, [make_profile("soulmate")], now=TUESDAY) is existing

    def test_user_tweaked_start_time_is_never_rolled_back(self):
        """用户把起始时间挪到凌晨 4 点半：再启动一次不能抹回 03:07。

        幂等只补"还没有的那几条"，不碰现存的那一条（用户/搭子的调整一律算数）。
        """
        tweaked = ScheduledTaskSpec(
            id=task_id("soulmate"),
            name="全员进化中 Soulmate",
            prompt="x",
            assistant_id="soulmate",
            start_at="2026-10-04T04:30",
            origin="builtin",
            silent=True,
        )

        result = ensure_builtin_tasks([tweaked], [make_profile("soulmate")], now=TUESDAY)

        assert result[0].start_at == "2026-10-04T04:30"


class TestLockedForUser:
    """产品约定：只有"内置搭子相关"的才锁。"""

    def _spec(
        self, origin: Literal["user", "agent", "builtin"], assistant_id: str
    ) -> ScheduledTaskSpec:
        return ScheduledTaskSpec(
            id="t",
            name="任务",
            prompt="做事",
            origin=origin,
            assistant_id=assistant_id,
        )

    def test_builtin_seeded_task_is_locked(self):
        assert locked_for_user(self._spec("builtin", "soulmate")) is True

    def test_task_created_by_a_builtin_buddy_is_locked(self):
        assert locked_for_user(self._spec("agent", "LoveBuddy")) is True

    def test_task_the_user_created_is_never_locked(self):
        """哪怕指定内置搭子跑 —— 它是用户自己配的，用户当然能改。"""
        assert locked_for_user(self._spec("user", "soulmate")) is False

    def test_tasks_of_other_buddies_are_never_locked(self):
        assert locked_for_user(self._spec("agent", "my-own")) is False
        # 来源是 builtin 但执行者不是那四位（手改配置造的怪状态）：也不锁
        assert locked_for_user(self._spec("builtin", "my-own")) is False

    def test_task_without_a_buddy_is_not_locked(self):
        assert locked_for_user(self._spec("agent", "")) is False
