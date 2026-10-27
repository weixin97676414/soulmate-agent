





from __future__ import annotations

import pytest

from my_agent.assistants import persona
from my_agent.assistants.persona import CONFIRM_FILE
from my_agent.config.paths import AppPaths
from my_agent.server.runtime import AppRuntime
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.orchestrate import TeamAddConfirmationSkill


@pytest.fixture
def runtime(tmp_path):
    return AppRuntime(paths=AppPaths(tmp_path / "data").ensure())


def _ctx(runtime) -> SkillContext:
    return SkillContext(
        settings=runtime.config.settings,
        paths=runtime.paths,
        session_id="s1",
        assistant_id="BuddyManager",
        extra=runtime.skill_services_for("BuddyManager"),
    )


def test_confirm_file_is_a_persona_file() -> None:
    assert CONFIRM_FILE in persona.ALLOWED_FILES


@pytest.mark.asyncio
async def test_add_confirmation_writes_structured_items(runtime) -> None:
    result = await TeamAddConfirmationSkill().run(
        _ctx(runtime),
        assistant_id="soulmate",
        items=[
            {"check": "按钮有没有错位", "expect": "左对齐", "pass_if": "没有偏离"},
            {"check": "文案有没有被截断", "expect": "完整显示", "pass_if": "没有省略号"},
        ],
    )
    assert result["added"] == 2

    content = persona.read_file(runtime.paths, "soulmate", CONFIRM_FILE)
    assert "## 1" in content
    assert "## 2" in content
    assert "核对项：按钮有没有错位" in content
    assert "期望：左对齐" in content
    assert "判据：没有偏离" in content
    
    assert content.count("结论：待定") == 2


@pytest.mark.asyncio
async def test_add_confirmation_appends_with_increasing_index(runtime) -> None:

    ctx = _ctx(runtime)
    await TeamAddConfirmationSkill().run(
        ctx, assistant_id="soulmate", items=[{"check": "第一件"}, {"check": "第二件"}]
    )
    await TeamAddConfirmationSkill().run(
        ctx, assistant_id="soulmate", items=[{"check": "第三件"}]
    )

    content = persona.read_file(runtime.paths, "soulmate", CONFIRM_FILE)
    assert content.count("\n## ") + (1 if content.startswith("## ") else 0) == 3
    assert "## 3" in content
    assert "核对项：第三件" in content
