

from __future__ import annotations

import pytest

from my_agent.config.schemas import SecuritySettings
from my_agent.errors import SkillPermissionError
from my_agent.security.permission import PermissionGuard
from my_agent.security.redact import redact, redact_obj
from my_agent.skill.base import SkillContext, SkillMeta


def test_redact_phone_and_id_card():
    text = "客户手机 13812345678，身份证 11010119900307123X"
    out = redact(text)
    assert "13812345678" not in out
    assert "11010119900307123X" not in out
    assert "<手机号>" in out
    assert "<身份证>" in out


def test_redact_api_key_variants():
    assert "sk-abc" not in redact("key=sk-abcdefghijklmn")
    assert "abc123token" not in redact("Authorization: Bearer abc123token")
    assert "secret123" not in redact('{"api_key": "secret123"}')


def test_redact_keeps_normal_numbers():

    text = "订单号 20240915，金额 1380 元，数量 120"
    assert redact(text) == text


def test_redact_obj_walks_nested_structures():
    payload = {"user": {"phone": "13812345678"}, "ids": ["11010119900307123X"]}
    out = redact_obj(payload)
    assert out["user"]["phone"] == "<手机号>"
    assert out["ids"] == ["<身份证>"]


def test_redact_can_be_disabled():
    assert redact("13812345678", enabled=False) == "13812345678"


def _meta(name: str, level: str) -> SkillMeta:
    return SkillMeta(name=name, description="测试用", permission_level=level)


@pytest.mark.asyncio
async def test_safe_skill_executes_without_confirm():
    guard = PermissionGuard(confirm_mode="interactive")
    await guard.check(_meta("read", "safe"), {}, SkillContext())


@pytest.mark.asyncio
async def test_confirm_skill_denied_without_channel():
    guard = PermissionGuard(confirm_mode="interactive")
    with pytest.raises(SkillPermissionError) as exc:
        await guard.check(_meta("write", "confirm"), {}, SkillContext())
    assert "无确认通道" in str(exc.value) or "确认" in str(exc.value)


@pytest.mark.asyncio
async def test_confirm_skill_denied_in_deny_mode():
    guard = PermissionGuard(confirm_mode="deny")
    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("write", "confirm"), {}, SkillContext())


@pytest.mark.asyncio
async def test_auto_approve_covers_confirm_level():

    guard = PermissionGuard(confirm_mode="auto_approve")
    await guard.check(_meta("write", "confirm"), {}, SkillContext())


@pytest.mark.asyncio
async def test_admin_level_requires_explicit_enable():

    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=False)
    with pytest.raises(SkillPermissionError) as exc:
        await guard.check(_meta("rm", "admin"), {}, SkillContext())
    assert "未开启" in str(exc.value)


@pytest.mark.asyncio
async def test_guard_level_allow_admin_also_auto_approves_admin():





    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=True)
    await guard.check(_meta("rm", "admin"), {}, SkillContext())


@pytest.mark.asyncio
async def test_ctx_allow_admin_lets_a_single_call_run_admin():





    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=False)

    
    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("rm", "admin"), {}, SkillContext())

    
    await guard.check(_meta("rm", "admin"), {}, SkillContext(allow_admin=True))


@pytest.mark.asyncio
async def test_ctx_allow_admin_does_not_bypass_interactive_confirmation():

    guard = PermissionGuard(confirm_mode="interactive")
    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("rm", "admin"), {}, SkillContext(allow_admin=True))


def test_新装默认是每次确认():










    assert SecuritySettings().confirm_mode == "interactive"


@pytest.mark.asyncio
async def test_override_takes_precedence_over_metadata():
    guard = PermissionGuard(confirm_mode="interactive", overrides={"write": "safe"})
    
    await guard.check(_meta("write", "confirm"), {}, SkillContext())


@pytest.mark.asyncio
async def test_user_rejection_raises():
    async def deny(_request):
        return False

    guard = PermissionGuard(confirm_mode="interactive")
    with pytest.raises(SkillPermissionError) as exc:
        await guard.check(_meta("write", "confirm"), {}, SkillContext(confirm=deny))
    assert "拒绝" in str(exc.value)


@pytest.mark.asyncio
async def test_live_confirm_mode_follows_config_change():






    guard = PermissionGuard(confirm_mode="interactive")
    state = {"mode": "deny"}
    ctx = SkillContext(confirm_mode=lambda: state["mode"])

    with pytest.raises(SkillPermissionError, match="一律拒绝"):
        await guard.check(_meta("write", "confirm"), {}, ctx)

    
    state["mode"] = "auto_approve"
    await guard.check(_meta("write", "confirm"), {}, ctx)  


@pytest.mark.asyncio
async def test_live_confirm_mode_failure_falls_back_to_global():

    guard = PermissionGuard(confirm_mode="auto_approve")

    def boom() -> str | None:
        raise RuntimeError("配置读挂了")

    assert guard.effective_mode(SkillContext(confirm_mode=boom)) == "auto_approve"


def test_live_confirm_mode_invalid_value_falls_back_to_global():

    guard = PermissionGuard(confirm_mode="interactive")
    assert guard.effective_mode(SkillContext(confirm_mode=lambda: "什么鬼")) == "interactive"


def test_confirm_level_skills_still_exposed_to_model():

    guard = PermissionGuard()
    specs = guard.filter_specs([_meta("a", "safe"), _meta("b", "confirm"), _meta("c", "admin")])
    assert {s.name for s in specs} == {"a", "b", "c"}
