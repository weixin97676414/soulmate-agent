

from __future__ import annotations

import pytest

from my_agent.errors import SkillNotFoundError, SkillValidationError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.system import CalculatorSkill, CurrentTimeSkill
from my_agent.skill.manager import SkillManager


@pytest.fixture
def manager() -> SkillManager:
    m = SkillManager()
    m.register(CalculatorSkill)
    m.register(CurrentTimeSkill)
    return m


@pytest.fixture
def ctx() -> SkillContext:
    return SkillContext()


async def test_calc_basic(manager, ctx):
    result = await manager.execute("calc", {"expression": "(1200-350)*0.13"}, ctx)
    assert "110.5" in result


async def test_calc_functions(manager, ctx):
    result = await manager.execute("calc", {"expression": "round(sqrt(2), 4)"}, ctx)
    assert "1.4142" in result


async def test_calc_rejects_code_execution(manager, ctx):

    for evil in [
        "__import__('os').system('echo hi')",
        "open('x.txt','w')",
        "(1).__class__.__bases__",
        "exec('1+1')",
    ]:
        with pytest.raises(Exception) as exc:  
            await manager.execute("calc", {"expression": evil}, ctx)
        assert "无法计算" in str(exc.value) or "不支持" in str(exc.value)


async def test_calc_division_by_zero_is_friendly(manager, ctx):
    with pytest.raises(Exception) as exc:  
        await manager.execute("calc", {"expression": "1/0"}, ctx)
    assert "无法计算" in str(exc.value)


async def test_current_time(manager, ctx):
    import json

    result = await manager.execute("system_time", {}, ctx)
    payload = json.loads(result)
    assert len(payload["date"]) == 10
    assert payload["weekday"].startswith("星期")


async def test_missing_required_param_raises_validation_error(manager, ctx):
    with pytest.raises(SkillValidationError) as exc:
        await manager.execute("calc", {}, ctx)
    assert "参数不合法" in str(exc.value)
    assert "expression" in str(exc.value)


async def test_unknown_skill_lists_available(manager, ctx):
    with pytest.raises(SkillNotFoundError) as exc:
        await manager.execute("not_exist", {}, ctx)
    assert "calc" in str(exc.value)


async def test_disabled_skill_is_not_exposed(manager):






    from my_agent.skill.base import BaseSkill, SkillMeta

    assert len(manager.to_tool_specs()) == 2

    class _Extra(BaseSkill):
        meta = SkillMeta(name="probe_skill", description="测试用：临时技能")

        async def run(self, ctx, **params):  
            return None

    manager.register(_Extra())
    assert "probe_skill" in [s.name for s in manager.to_tool_specs()]

    manager.set_enabled("probe_skill", False)
    names = [s.name for s in manager.to_tool_specs()]
    assert "probe_skill" not in names
    assert "system_time" in names


def test_tool_spec_schema_shape(manager):
    spec = next(s for s in manager.to_tool_specs() if s.name == "calc")
    assert spec.parameters["type"] == "object"
    assert "expression" in spec.parameters["properties"]
    assert "title" not in spec.parameters
    
    assert len(spec.description) > 40
