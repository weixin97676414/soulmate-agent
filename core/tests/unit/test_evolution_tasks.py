














from __future__ import annotations

from datetime import datetime
from typing import Literal

from my_agent.agent.evolution_tasks import (
    BUILTIN_TASK_ID_PREFIX,
    MANAGER_REVIEW_TASK_ID,
    MONTH_MINUTES,
    STAGGER_MINUTES,
    WEEK_MINUTES,
    builtin_specs,
    ensure_builtin_tasks,
    first_run_at,
    task_id,
    upgrade_builtin_prompts,
)
from my_agent.agent.task_store import locked_for_user
from my_agent.assistants import evolution
from my_agent.config.schemas import AssistantProfile, ScheduledTaskSpec


TUESDAY = datetime(2026, 9, 29, 10, 0).timestamp()


def make_profile(assistant_id: str, name: str = "", **overrides) -> AssistantProfile:
    payload = {"id": assistant_id, "name": name or assistant_id, "sort_order": 100}
    payload.update(overrides)
    return AssistantProfile(**payload)


class TestFirstRunAt:


    def test_next_sunday_after_a_weekday_install(self):
        assert first_run_at(TUESDAY, 0) == "2026-10-04T03:07"

    def test_sunday_before_the_anchor_runs_the_same_day(self):

        assert first_run_at(datetime(2026, 10, 4, 1, 0).timestamp(), 0) == "2026-10-04T03:07"

    def test_sunday_after_the_anchor_waits_a_week(self):
        assert first_run_at(datetime(2026, 10, 4, 5, 0).timestamp(), 0) == "2026-10-11T03:07"

    def test_stagger_is_added_after_the_anchor(self):





        assert first_run_at(TUESDAY, STAGGER_MINUTES) == "2026-10-04T03:22"
        assert first_run_at(TUESDAY, 4 * STAGGER_MINUTES) == "2026-10-04T04:07"
        
        assert first_run_at(TUESDAY, 5 * STAGGER_MINUTES) == "2026-10-04T04:22"


class TestBuiltinSpecs:
    def _profiles(self) -> list[AssistantProfile]:
        
        return [
            make_profile("soulmate", "Soulmate", sort_order=10),
            make_profile("LoveBuddy", "Love Buddy", sort_order=20),
            make_profile("RelationBuddy", "Relation Buddy", sort_order=30),
            make_profile("BuddyManager", "Buddy Manager", sort_order=40),
            
            make_profile("my-own", "我的搭子", sort_order=50),
        ]

    def test_only_builtin_buddies_get_a_task(self):
        specs = builtin_specs(self._profiles(), now=TUESDAY)
        weekly = [item for item in specs if item.id != MANAGER_REVIEW_TASK_ID]

        assert [item.assistant_id for item in weekly] == [
            "soulmate",
            "LoveBuddy",
            "RelationBuddy",
            "BuddyManager",
        ]
        assert all(item.id.startswith(BUILTIN_TASK_ID_PREFIX) for item in specs)
        assert task_id("soulmate") in [item.id for item in specs]
        
        assert "my-own" not in [item.assistant_id for item in specs]

    def test_fields_are_the_agreed_ones(self):
        first = builtin_specs(self._profiles(), now=TUESDAY)[0]

        assert first.name == "全员进化中 Soulmate"
        assert first.trigger == "interval"
        assert first.interval_minutes == WEEK_MINUTES == 10080
        assert first.enabled is True, "用户口径是「内置搭子我们创建好自动进化」"
        assert first.silent is True, "每周自己跑一次，没必要次次弹窗"
        assert first.origin == "builtin", "预置任务用户不能改/关/删"
        assert first.start_at == "2026-10-04T03:07"
        
        assert "Soulmate" in first.prompt

    def test_start_times_are_staggered(self):
        specs = builtin_specs(self._profiles(), now=TUESDAY)
        stamps = [item.start_at for item in specs]

        assert len(set(stamps)) == 5, "五条不能落在同一分钟"
        moments = [datetime.strptime(item, "%Y-%m-%dT%H:%M") for item in stamps]
        gaps = [
            (later - earlier).total_seconds() / 60
            for earlier, later in zip(moments, moments[1:], strict=False)
        ]
        
        assert gaps == [STAGGER_MINUTES] * 4
        assert stamps[-1] == "2026-10-04T04:07"

    def test_monthly_review_is_the_fifth_and_does_not_shift_weekly_slots(self):





        specs = builtin_specs(self._profiles(), now=TUESDAY)
        monthly = next(item for item in specs if item.id == MANAGER_REVIEW_TASK_ID)

        assert monthly.assistant_id == "BuddyManager"
        assert monthly.name == "全员进化月度复盘"
        assert monthly.trigger == "interval"
        assert monthly.interval_minutes == MONTH_MINUTES == 43200
        assert monthly.enabled is True
        assert monthly.origin == "builtin"
        assert monthly.silent is False, "月度复盘要在跑完后通知用户看结果"
        
        assert specs[0].start_at == "2026-10-04T03:07"

    def test_monthly_review_needs_the_manager_in_the_list(self):

        specs = builtin_specs([make_profile("soulmate", "Soulmate", sort_order=10)], now=TUESDAY)

        assert [item.id for item in specs] == [task_id("soulmate")]

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
        
        assert result[0] is existing[0]

    def test_nothing_missing_returns_the_same_list(self):
        existing = [
            ScheduledTaskSpec(id=task_id("soulmate"), name="全员进化中 Soulmate", prompt="x")
        ]

        assert ensure_builtin_tasks(existing, [make_profile("soulmate")], now=TUESDAY) is existing

    def test_user_tweaked_start_time_is_never_rolled_back(self):




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


class TestUpgradeBuiltinPrompts:






    def _legacy(self, name: str = "Soulmate") -> ScheduledTaskSpec:
        return ScheduledTaskSpec(
            id=task_id("soulmate"),
            name=f"全员进化中 {name}",
            prompt=evolution._legacy_builtin_prompt(name),
            assistant_id="soulmate",
            trigger="interval",
            interval_minutes=WEEK_MINUTES,
            start_at="2026-10-04T03:07",
            origin="builtin",
            silent=True,
            enabled=True,
        )

    def _profiles(self) -> list[AssistantProfile]:
        return [make_profile("soulmate", "Soulmate", sort_order=10)]

    def test_factory_prompt_is_upgraded(self):
        upgraded, ids = upgrade_builtin_prompts([self._legacy()], self._profiles())

        assert ids == [task_id("soulmate")]
        assert "进化日志" in upgraded[0].prompt, "新版必须有日志那一节"
        assert upgraded[0].prompt != self._legacy().prompt
        
        old = self._legacy()
        assert upgraded[0].interval_minutes == old.interval_minutes
        assert upgraded[0].start_at == old.start_at
        assert upgraded[0].silent is True
        assert upgraded[0].origin == "builtin"
        assert upgraded[0].enabled is True

    def test_user_edited_prompt_is_kept_verbatim(self):
        edited = self._legacy().model_copy(
            update={"prompt": self._legacy().prompt + "\n我加的一条：每周顺手看一下待办。"}
        )

        result, ids = upgrade_builtin_prompts([edited], self._profiles())

        assert ids == []
        assert result[0].prompt == edited.prompt

    def test_nothing_to_do_returns_the_same_list(self):

        specs = [self._legacy()]

        result, ids = upgrade_builtin_prompts(specs, self._profiles())
        assert ids == [task_id("soulmate")]

        again, ids2 = upgrade_builtin_prompts(result, self._profiles())
        assert ids2 == [] and again is result

    def test_monthly_review_and_user_tasks_are_untouched(self):
        monthly = self._legacy().model_copy(
            update={
                "id": MANAGER_REVIEW_TASK_ID,
                "assistant_id": "BuddyManager",
                "prompt": evolution.manager_review_prompt(),
            }
        )
        user_task = self._legacy().model_copy(update={"id": "my-task", "origin": "user"})

        result, ids = upgrade_builtin_prompts([monthly, user_task], self._profiles())

        assert ids == []
        assert result[0] is monthly and result[1] is user_task

    def test_renamed_nickname_is_carried_into_the_new_prompt(self):

        specs = [self._legacy("小灵")]

        result, ids = upgrade_builtin_prompts(
            specs, [make_profile("soulmate", "Soulmate", nickname="阿灵", sort_order=10)]
        )
        assert ids == [task_id("soulmate")]
        assert result[0].prompt.startswith("你是「阿灵」。")

        
        orphan = self._legacy("小灵").model_copy(update={"assistant_id": ""})
        result2, ids2 = upgrade_builtin_prompts([orphan], [])
        assert ids2 == [task_id("soulmate")]
        assert result2[0].prompt.startswith("你是「小灵」。")


class TestLockedForUser:


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

        assert locked_for_user(self._spec("user", "soulmate")) is False

    def test_tasks_of_other_buddies_are_never_locked(self):
        assert locked_for_user(self._spec("agent", "my-own")) is False
        
        assert locked_for_user(self._spec("builtin", "my-own")) is False

    def test_task_without_a_buddy_is_not_locked(self):
        assert locked_for_user(self._spec("agent", "")) is False
