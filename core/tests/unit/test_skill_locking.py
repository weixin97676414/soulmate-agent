
















from __future__ import annotations

import pytest

from my_agent.errors import SkillPermissionError
from my_agent.skill.base import BaseSkill, SkillMeta
from my_agent.skill.builtin import discover_builtin_skills
from my_agent.skill.locked import ALWAYS_ON_SKILLS
from my_agent.skill.manager import SkillManager


def build_manager() -> SkillManager:
    manager = SkillManager()
    for skill_cls in discover_builtin_skills():
        manager.register(skill_cls)
    return manager


EXPECTED_ALWAYS_ON = {
    "ai_thinking_mode",
    
    "system_time",
    "self_growth",
    "history_search",
    "kb_add",
    "kb_search",
    "kb_stats",
    "anti_fraud",
    "http_request",
    
    "xjx_place_lookup",
    "xjx_fetch_report",
    
    
    "xjx_fetch_astro",
    "xjx_fetch_bazi",
    "xjx_fetch_meihua",
    "xjx_fetch_tarot",
    
    
    
    "ask_choice",
    "request_secret",
}


def test_locked_names_are_exactly_the_expected_set() -> None:









    assert ALWAYS_ON_SKILLS == EXPECTED_ALWAYS_ON, (
        f"多出来的：{sorted(ALWAYS_ON_SKILLS - EXPECTED_ALWAYS_ON)}；"
        f"少掉的：{sorted(EXPECTED_ALWAYS_ON - ALWAYS_ON_SKILLS)}"
    )
    
    assert len(EXPECTED_ALWAYS_ON) >= 17


def test_all_locked_skills_exist_and_are_marked() -> None:
    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        assert manager.has(name), f"{name} 不在已注册的内置技能里"
        meta = manager.get(name).meta
        assert meta.locked is True, f"{name} 没有被标记成永久开启"
        
        assert meta.permission_level == "safe", f"{name} 的权限不是免批准"
        
        assert meta.enabled is True
        assert meta.to_dict()["locked"] is True


def test_locked_skills_cannot_be_disabled() -> None:

    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        with pytest.raises(SkillPermissionError) as exc:
            manager.set_enabled(name, False)
        
        
        
        
        
        display = manager.get(name).meta.display_name
        assert display in str(exc.value), f"{name} 的拒绝文案没有点名到具体技能"
        assert "不提供开关" in str(exc.value), f"{name} 的拒绝文案没说清「关不掉」"
        assert manager.get(name).meta.enabled is True


def test_locked_skills_cannot_change_permission() -> None:

    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        for level in ("confirm", "admin"):
            with pytest.raises(SkillPermissionError):
                manager.set_permission(name, level)
        assert manager.get(name).meta.permission_level == "safe"


def test_enabling_a_locked_skill_is_a_noop_not_an_error() -> None:





    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        assert manager.set_enabled(name, True).enabled is True


def test_skills_outside_the_list_are_still_manageable() -> None:


    class _Other(BaseSkill):
        meta = SkillMeta(name="some_other_skill", description="x", permission_level="confirm")

        async def run(self, ctx, **params):  
            return None

    manager = SkillManager()
    manager.register(_Other())
    assert manager.get("some_other_skill").meta.locked is False

    assert manager.set_enabled("some_other_skill", False).enabled is False
    assert manager.set_permission("some_other_skill", "safe").permission_level == "safe"


def test_mcp_tool_with_a_locked_name_is_not_locked() -> None:






    class _FakeMcpTool(BaseSkill):
        meta = SkillMeta(name="http_request", description="x", source="mcp")

        async def run(self, ctx, **params):  
            return None

    manager = SkillManager()
    manager.register(_FakeMcpTool())
    assert manager.get("http_request").meta.locked is False
    assert manager.set_enabled("http_request", False).enabled is False


def test_kb_forget_stays_confirm() -> None:









    manager = build_manager()
    if not manager.has("kb_forget"):  
        pytest.skip("kb_forget 已不在内置技能里")
    meta = manager.get("kb_forget").meta
    assert meta.locked is True
    assert meta.permission_level == "confirm"
