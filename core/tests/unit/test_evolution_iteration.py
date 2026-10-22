














from __future__ import annotations

import pytest

from my_agent.assistants import evolution, persona
from my_agent.assistants.persona import EVOLUTION_LOG_FILE, MEMORY_FILE
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import ScheduledTaskSpec
from my_agent.errors import SkillExecutionError
from my_agent.server.runtime import AppRuntime
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.orchestrate import (
    TeamReadAssistantFileSkill,
    TeamUpdateAssistantSkill,
)



BUILTIN_ID = "soulmate"
MANAGER_ID = "BuddyManager"


@pytest.fixture
def runtime(tmp_path):
    return AppRuntime(paths=AppPaths(tmp_path / "data").ensure())


def _ctx(runtime, assistant_id: str = MANAGER_ID) -> SkillContext:
    return SkillContext(
        settings=runtime.config.settings,
        paths=runtime.paths,
        session_id="s1",
        assistant_id=assistant_id,
        extra=runtime.skill_services_for(assistant_id),
    )





def test_evolution_log_roundtrip_on_a_builtin_buddy(runtime):

    assert persona.read_file(runtime.paths, BUILTIN_ID, EVOLUTION_LOG_FILE) == ""

    persona.write_file(
        runtime.paths, BUILTIN_ID, EVOLUTION_LOG_FILE, "### 2026-10-17\n\n指标：新增 1\n"
    )

    assert "指标：新增 1" in persona.read_file(runtime.paths, BUILTIN_ID, EVOLUTION_LOG_FILE)





@pytest.mark.asyncio
async def test_manager_can_append_the_monthly_focus_into_a_buddys_memory(runtime):





    persona.write_file(runtime.paths, BUILTIN_ID, MEMORY_FILE, "用户喜欢喝美式。\n")

    await runtime.orchestrator.append_assistant_setup(
        assistant_id=BUILTIN_ID,
        memory_append="[月度复盘 · 本月重点] 用户说'随便'时先给两个选项，别反问。",
        actor_id=MANAGER_ID,
    )

    memory = persona.read_file(runtime.paths, BUILTIN_ID, MEMORY_FILE)
    assert "用户喜欢喝美式。" in memory, "原有记忆一个字都不能动"
    assert "[月度复盘 · 本月重点]" in memory
    assert "别反问" in memory


@pytest.mark.asyncio
async def test_manager_reads_another_buddys_evolution_log(runtime):




    persona.write_file(
        runtime.paths,
        BUILTIN_ID,
        EVOLUTION_LOG_FILE,
        "### 2026-10-17\n\n指标：新增 2 · 合并 1 · 冲突消解 0 · 待验证完成率 1/2\n",
    )

    result = await TeamReadAssistantFileSkill().run(
        _ctx(runtime), assistant_id=BUILTIN_ID, file=EVOLUTION_LOG_FILE
    )

    assert result["ok"] is True
    assert "待验证完成率 1/2" in result["content"]


@pytest.mark.asyncio
async def test_reading_a_missing_buddy_is_not_the_same_as_an_empty_file(runtime):

    with pytest.raises(SkillExecutionError) as exc:
        await TeamReadAssistantFileSkill().run(
            _ctx(runtime), assistant_id="no-such-buddy", file=EVOLUTION_LOG_FILE
        )
    assert "no-such-buddy" in str(exc.value)


@pytest.mark.asyncio
async def test_reading_outside_the_whitelist_is_rejected(runtime):

    with pytest.raises(SkillExecutionError):
        await TeamReadAssistantFileSkill().run(
            _ctx(runtime), assistant_id=BUILTIN_ID, file="../../settings.json"
        )


@pytest.mark.asyncio
async def test_update_skill_passes_memory_append_through(runtime):

    await TeamUpdateAssistantSkill().run(
        _ctx(runtime), assistant_id=BUILTIN_ID, memory_append="[月度复盘] 这周先练短回答。"
    )

    assert "[月度复盘] 这周先练短回答。" in persona.read_file(
        runtime.paths, BUILTIN_ID, MEMORY_FILE
    )





def _legacy_task(spec_id: str, assistant_id: str, prompt: str) -> ScheduledTaskSpec:
    return ScheduledTaskSpec(
        id=spec_id,
        name=f"全员进化中 {assistant_id}",
        prompt=prompt,
        assistant_id=assistant_id,
        trigger="interval",
        interval_minutes=10080,
        start_at="2026-10-04T03:07",
        origin="builtin",
        silent=True,
        enabled=True,
    )


def _reload(runtime, specs: list[ScheduledTaskSpec]) -> None:

    settings = runtime.config.settings.model_copy(
        update={
            "agent": runtime.config.settings.agent.model_copy(
                update={"scheduled_tasks": specs}
            )
        }
    )
    saved = runtime.config_store.save_settings(settings)
    runtime.config = runtime.config.model_copy(update={"settings": saved})


def test_startup_promotes_the_factory_prompt_of_old_machines(runtime):





    old = evolution._legacy_builtin_prompt("Soulmate")
    _reload(runtime, [_legacy_task("builtin-evolve-soulmate", "soulmate", old)])

    runtime.seed_evolution_tasks()

    saved = {item.id: item for item in runtime.config.settings.agent.scheduled_tasks}
    assert "进化日志" in saved["builtin-evolve-soulmate"].prompt
    
    on_disk = runtime.config_store.load(reload=True)
    stored = {item.id: item for item in on_disk.settings.agent.scheduled_tasks}
    assert "进化日志" in stored["builtin-evolve-soulmate"].prompt
    
    assert stored["builtin-evolve-soulmate"].start_at == "2026-10-04T03:07"
    assert stored["builtin-evolve-soulmate"].silent is True


def test_startup_keeps_a_prompt_the_user_edited(runtime):




    edited = evolution._legacy_builtin_prompt("Soulmate") + "\n我加的一条：每周顺手看一眼待办。"
    _reload(runtime, [_legacy_task("builtin-evolve-soulmate", "soulmate", edited)])

    runtime.seed_evolution_tasks()

    saved = {item.id: item for item in runtime.config.settings.agent.scheduled_tasks}
    assert saved["builtin-evolve-soulmate"].prompt == edited
