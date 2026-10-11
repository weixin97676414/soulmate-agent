"""上下文预算：模型窗口与用户设的硬上限，谁说了算。

## 这组用例是为了防一次真实的回归

``AgentSettings.max_context_tokens`` 原先是固定 32000，而 ``MemoryManager``
**直接拿它当裁剪预算**。后果是：用户把某个模型的上下文窗口改成 100 万，
记忆仍然在 3.2 万处被裁掉，界面上看不出任何异常 ——
"我配了但不生效"比"没这个功能"难查得多。

所以这里同时钉两件事：
1. 预算 = ``min(模型窗口, 硬上限)``，硬上限为 0 时就是模型窗口；
2. 那个字段的**默认值必须是 0**（跟随模型），不能悄悄变回一个固定数字。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from my_agent.config.schemas import AgentSettings
from my_agent.server.runtime import AppRuntime

# 取不到模型窗口时的兜底值，和 runtime 里的常量保持一致
FALLBACK_TOKENS = 32768


def budget(window: int | None, cap: int) -> int:
    """按给定条件算一次预算。

    ``window=None`` 表示 registry 取不到该模型（模型被删了、构建失败等）。
    这里直接调用未绑定方法，用一个最小假对象当 ``self`` —— 被测逻辑只用到
    ``registry`` 和 ``config`` 两处，为它拉起一整个 AppRuntime 得不偿失。
    """

    def get(_model_id: str | None):
        if window is None:
            raise KeyError("模型不存在")
        return SimpleNamespace(token_limit=window)

    fake = SimpleNamespace(
        registry=SimpleNamespace(get=get),
        config=SimpleNamespace(
            settings=SimpleNamespace(agent=SimpleNamespace(max_context_tokens=cap))
        ),
    )
    return AppRuntime.effective_context_tokens(fake, "m")


class TestEffectiveBudget:
    def test_zero_cap_follows_the_model_window(self):
        """默认（硬上限 0）就是跟随模型 —— 这正是要修的那个点。"""
        assert budget(1_000_000, 0) == 1_000_000
        assert budget(131_072, 0) == 131_072

    def test_positive_cap_limits_the_window(self):
        """用户想控成本时可以设一个更小的上限。"""
        assert budget(1_000_000, 65_536) == 65_536

    def test_cap_larger_than_window_is_ignored(self):
        """上限比模型窗口还大时，实际受限于**模型**，不是上限。

        不这样处理的话，用户填了 100 万上限、配了个 32K 的本地模型，
        系统会以为有 100 万可用 —— 直到厂商回一个和上下文无关的报错。
        """
        assert budget(32_768, 1_000_000) == 32_768

    def test_unknown_model_falls_back_to_cap(self):
        assert budget(None, 65_536) == 65_536

    def test_unknown_model_without_cap_uses_conservative_default(self):
        """两样都拿不到时要保守：宁可少用上下文，也别在请求阶段被厂商拒掉。"""
        assert budget(None, 0) == FALLBACK_TOKENS


class TestSettingsDefault:
    def test_default_is_follow_the_model_not_a_fixed_number(self):
        """把这条钉死，防止有人"顺手"把它改回 32000。

        改回固定值的表现是**功能静默退化**：模型窗口调到多大都只用到 3.2 万，
        而且没有任何报错。
        """
        assert AgentSettings().max_context_tokens == 0

    def test_negative_is_rejected(self):
        """负数不是一个"更小"的上限，它是无意义的输入，应当在配置校验期报错。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentSettings(max_context_tokens=-1)
