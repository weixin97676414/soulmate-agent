"""永久开启（后端硬锁）的技能。

前九个承载搭子的**长期记忆、自我认知与基础信息获取**，
明确要求"AI 直接用、不要批准、设置里没有开关、无法手动关闭"；
另外两个是心鉴学专属技能的**配套工具**（地点核对 / 报告代取），
它们必须一起常开 —— 报告取到一半被确认卡片拦住，用户看到的是"专属技能坏了"。

这组用例守的是三件事，缺一件就等于这个约束名存实亡：

1. **名单对得上**：名单里的名字都真的存在，且都被盖上了 `locked`；
2. **真的关不掉**：`set_enabled(False)` 与 `set_permission` 必须抛错 ——
   只靠"前端不画开关"是挡不住 PATCH 接口与将来新入口的；
3. **不误伤别人**：没在名单里的技能照常可关、可改权限；MCP 工具即使撞名也不锁。

⚠️ 增删名单时必须同步 `my_agent/skill/locked.py` 的 `ALWAYS_ON_SKILLS`。
"""

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
    # 界面上叫「获取当前时间」，技能名是 system_time（别按显示名猜）
    "system_time",
    "self_growth",
    "history_search",
    "kb_add",
    "kb_search",
    "kb_stats",
    "anti_fraud",
    "http_request",
    # 心鉴学专属技能的配套工具（界面显示名是「地点核对」「报告代取」）
    "xjx_place_lookup",
    "xjx_fetch_report",
    # 向用户求助的两个通道。产品明确要求它们**关不掉**：
    # "要求的就是关不掉，要不然我怎么不放通用技能呢"。
    # 名字别按显示名猜 —— 显示名是「请你确认一下」「请你提供密钥」。
    "ask_choice",
    "request_secret",
}


def test_locked_names_are_exactly_the_expected_set() -> None:
    """关不掉名单必须与这里的期望集**完全一致**。

    ⚠️ 名字原先叫"...the_eleven_the_user_asked_for"，但"十一个"这种数字一进名字
    就会在下一次调整时变成谎话（改名比改数字更难被注意到）。所以改成中性说法，
    数量交给下面这两行自己去说明。

    多一个少一个都要在这里显式改，不能偷偷漂 —— 漏改的表现是
    "某个技能其实锁不住，但没有任何地方会报错"。
    """
    assert ALWAYS_ON_SKILLS == EXPECTED_ALWAYS_ON, (
        f"多出来的：{sorted(ALWAYS_ON_SKILLS - EXPECTED_ALWAYS_ON)}；"
        f"少掉的：{sorted(EXPECTED_ALWAYS_ON - ALWAYS_ON_SKILLS)}"
    )
    # 顺带把"至少不是空集"钉住：名单被整体清空时上面那条也会通过（两边都空）
    assert len(EXPECTED_ALWAYS_ON) >= 13


def test_all_locked_skills_exist_and_are_marked() -> None:
    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        assert manager.has(name), f"{name} 不在已注册的内置技能里"
        meta = manager.get(name).meta
        assert meta.locked is True, f"{name} 没有被标记成永久开启"
        # 顺带钉住"免批准"：这九个都必须能直接执行
        assert meta.permission_level == "safe", f"{name} 的权限不是免批准"
        # 界面的老版本依赖 enabled 字段判断是否置灰，锁定技能永远是 True
        assert meta.enabled is True
        assert meta.to_dict()["locked"] is True


def test_locked_skills_cannot_be_disabled() -> None:
    """**关不掉**：任何调用路径都不行（前端不画开关只是第一层）。"""
    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        with pytest.raises(SkillPermissionError) as exc:
            manager.set_enabled(name, False)
        # 报错要说人话：界面会把它原样展示给用户。两条理由不一样
        # （前九个是"承载记忆与人格"，心鉴学那两个是"专属技能按线路自动启用"），
        # 所以这里钉的是两句话共有的部分：
        #   (1) 点名是哪一项 —— 否则用户不知道到底哪个技能被拦了；
        #   (2) 说清"没有开关" —— 只说"不允许"会让人以为要找别的地方去关。
        display = manager.get(name).meta.display_name
        assert display in str(exc.value), f"{name} 的拒绝文案没有点名到具体技能"
        assert "不提供开关" in str(exc.value), f"{name} 的拒绝文案没说清「关不掉」"
        assert manager.get(name).meta.enabled is True


def test_locked_skills_cannot_change_permission() -> None:
    """**降不了级也升不了级**：权限固定为免批准。"""
    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        for level in ("confirm", "admin"):
            with pytest.raises(SkillPermissionError):
                manager.set_permission(name, level)
        assert manager.get(name).meta.permission_level == "safe"


def test_enabling_a_locked_skill_is_a_noop_not_an_error() -> None:
    """`set_enabled(True)` 必须放行。

    否则任何一次"把状态整体回放一遍"（界面重载、技能列表重建）都会在这里炸，
    而那个报错跟用户的操作毫无关系 —— 是最难查的一类。
    """
    manager = build_manager()
    for name in sorted(ALWAYS_ON_SKILLS):
        assert manager.set_enabled(name, True).enabled is True


def test_skills_outside_the_list_are_still_manageable() -> None:
    """名单之外的技能照常可关、可改权限 —— 别把整个技能系统都锁死。"""

    class _Other(BaseSkill):
        meta = SkillMeta(name="some_other_skill", description="x", permission_level="confirm")

        async def run(self, ctx, **params):  # pragma: no cover - 不执行
            return None

    manager = SkillManager()
    manager.register(_Other())
    assert manager.get("some_other_skill").meta.locked is False

    assert manager.set_enabled("some_other_skill", False).enabled is False
    assert manager.set_permission("some_other_skill", "safe").permission_level == "safe"


def test_mcp_tool_with_a_locked_name_is_not_locked() -> None:
    """MCP 工具的权限归 MCP 页管，撞名也不该被这份名单锁住。

    实际很难撞上（MCP 工具名带服务前缀），但这条边界必须写死：
    名单的语义是"内置的这九个"，不是"叫这个名字的一切"。
    """

    class _FakeMcpTool(BaseSkill):
        meta = SkillMeta(name="http_request", description="x", source="mcp")

        async def run(self, ctx, **params):  # pragma: no cover - 不执行
            return None

    manager = SkillManager()
    manager.register(_FakeMcpTool())
    assert manager.get("http_request").meta.locked is False
    assert manager.set_enabled("http_request", False).enabled is False


def test_kb_forget_stays_confirm() -> None:
    """免批准的口径**只覆盖用户列出的那九个**。

    「从长期记忆删除」是同一类能力里唯一不可逆的那个，它必须留在"需确认"，
    别顺手一起放开。

    ⚠️ 断言 2026-10-06 随四分类改过一次：`kb_forget` 现在划在「内置技能」里，
    所以它连"被关掉、被改权限"都不允许（`locked=True`）—— 这比"留在确认"更严格。
    原来的意图（不许被顺手放开成免批准）仍由 `permission_level` 那一行钉着。
    """
    manager = build_manager()
    if not manager.has("kb_forget"):  # pragma: no cover - 技能被移除时不该让用例失败
        pytest.skip("kb_forget 已不在内置技能里")
    meta = manager.get("kb_forget").meta
    assert meta.locked is True
    assert meta.permission_level == "confirm"
