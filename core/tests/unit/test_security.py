"""安全机制测试：脱敏与权限守卫。"""

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
    """普通数字不应被误伤，否则日志会失去可读性。"""
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
    """auto_approve 直接放行 confirm 级（出厂默认就是这个模式）。"""
    guard = PermissionGuard(confirm_mode="auto_approve")
    await guard.check(_meta("write", "confirm"), {}, SkillContext())


@pytest.mark.asyncio
async def test_admin_level_requires_explicit_enable():
    """没放开 admin 时，连 auto_approve 也过不去 —— 这是高危操作的总闸。"""
    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=False)
    with pytest.raises(SkillPermissionError) as exc:
        await guard.check(_meta("rm", "admin"), {}, SkillContext())
    assert "未开启" in str(exc.value)


@pytest.mark.asyncio
async def test_guard_level_allow_admin_also_auto_approves_admin():
    """守卫自身的 ``allow_admin`` 是**进程级**的"本环境允许高危操作"。

    它一旦打开，auto_approve 就一并覆盖 admin 级。生产里这个开关写死 False
    （见 ``server/runtime.py``），所以前台永远不会静默执行高危操作。
    """
    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=True)
    await guard.check(_meta("rm", "admin"), {}, SkillContext())


@pytest.mark.asyncio
async def test_ctx_allow_admin_lets_a_single_call_run_admin():
    """**按次**放开 admin：定时任务靠它做到"不管什么技能都自动批准"。

    守卫上的开关是进程级的，改它会连前台一起放开，所以只给"这一次调用"开绿灯
    （见 ``SkillContext.allow_admin`` 与 ``agent/scheduler.py``）。
    """
    guard = PermissionGuard(confirm_mode="auto_approve", allow_admin=False)

    # 没传 allow_admin 的 ctx（单聊 / 群聊）依旧被拦
    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("rm", "admin"), {}, SkillContext())

    # 定时任务那个 ctx 传了 True → 放行
    await guard.check(_meta("rm", "admin"), {}, SkillContext(allow_admin=True))


@pytest.mark.asyncio
async def test_ctx_allow_admin_does_not_bypass_interactive_confirmation():
    """放开 admin ≠ 绕开确认：交互模式下仍然要走确认通道，没通道照样拒绝。"""
    guard = PermissionGuard(confirm_mode="interactive")
    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("rm", "admin"), {}, SkillContext(allow_admin=True))


def test_新装默认是每次确认():
    """出厂默认的确认模式是「每次确认」。

    ⚠️ 这条断言与上一版**正好相反** —— 它以前叫
    ``test_fresh_install_defaults_to_auto_approve``，守的是"新装即可直接干活"。
    方向反过来是因为取舍变了（产品要求"所有搭子出厂设置为
    每次确认"）：宁可多问一次，也不要让它悄悄动了文件。

    钉住的是**默认值**本身，不是判定逻辑：用户改过之后以 ``settings.json``
    里的值为准，这里只保证新装时是那个更保守的档。
    """
    assert SecuritySettings().confirm_mode == "interactive"


@pytest.mark.asyncio
async def test_override_takes_precedence_over_metadata():
    guard = PermissionGuard(confirm_mode="interactive", overrides={"write": "safe"})
    # 元数据是 confirm，但配置覆盖为 safe -> 直接放行，不触发确认
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
    """会话级权限模式允许是**惰性提供者**：配置改了，下一次工具调用立刻生效。

    用户反馈的原话是"任务进行中更换权限确认后要即时生效，而不是等下一次任务"。
    根因是模式在任务开始时被快照进 ``SkillContext``；传闭包后每次 check 都现场
    重读当前配置 —— 同一个 ctx、同一个任务，策略变了就按新的走。
    """
    guard = PermissionGuard(confirm_mode="interactive")
    state = {"mode": "deny"}
    ctx = SkillContext(confirm_mode=lambda: state["mode"])

    with pytest.raises(SkillPermissionError, match="一律拒绝"):
        await guard.check(_meta("write", "confirm"), {}, ctx)

    # 任务还在跑，用户把搭子的策略改成了「自动批准」
    state["mode"] = "auto_approve"
    await guard.check(_meta("write", "confirm"), {}, ctx)  # 不抛异常 = 按新策略放行


@pytest.mark.asyncio
async def test_live_confirm_mode_failure_falls_back_to_global():
    """读配置失败时按全局策略处理 —— **不能让工具调用直接崩**。"""
    guard = PermissionGuard(confirm_mode="auto_approve")

    def boom() -> str | None:
        raise RuntimeError("配置读挂了")

    assert guard.effective_mode(SkillContext(confirm_mode=boom)) == "auto_approve"


def test_live_confirm_mode_invalid_value_falls_back_to_global():
    """闭包给出不合法值时按全局处理：校验只在这一处收敛。"""
    guard = PermissionGuard(confirm_mode="interactive")
    assert guard.effective_mode(SkillContext(confirm_mode=lambda: "什么鬼")) == "interactive"


def test_confirm_level_skills_still_exposed_to_model():
    """confirm 级 Skill 必须出现在工具列表里，否则模型无法提出该操作。"""
    guard = PermissionGuard()
    specs = guard.filter_specs([_meta("a", "safe"), _meta("b", "confirm"), _meta("c", "admin")])
    assert {s.name for s in specs} == {"a", "b", "c"}
