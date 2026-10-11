"""电脑操作技能：注册、参数校验、权限级别。

## 为什么这些用例**不真的操作电脑**

它们跑在开发机上 —— 也就是用户正在用的那台。真的移动鼠标、点击、敲字，
会打断用户手头的事，甚至点到不该点的地方。测试绝不该有这种副作用。
所以这里只验证三件**不需要真动手**的事：

1. 技能被正确加载，且名字 / 权限级别 / 标签符合约定；
2. 参数模型拦得住越界与非法的输入（这些在碰到底座之前就报错）；
3. 底座在参数非法时**如实报错**，而不是静默失败或悄悄纠正。
"""

from __future__ import annotations

import sys

import pytest
from pydantic import ValidationError

from my_agent.skill.builtin.computer import (
    MouseClickParams,
    MouseScrollParams,
    PressKeysParams,
    ReadScreenParams,
    TypeTextParams,
)
from my_agent.utils import windows_api

WINDOWS = sys.platform == "win32"

#: 本模块负责的技能清单（少一个就说明它没被登记进 _MODULES）
_EXPECTED = (
    "computer_mouse_move",
    "computer_mouse_click",
    "computer_mouse_scroll",
    "computer_mouse_drag",
    "computer_type_text",
    "computer_press_keys",
    "computer_list_windows",
    "computer_activate_window",
    "computer_launch",
    "computer_read_screen",
)


def _computer_skills() -> list:
    from my_agent.skill.builtin import discover_builtin_skills

    return [
        item
        for item in discover_builtin_skills()
        if item.meta.name.startswith("computer_")
    ]


class TestRegistration:
    def test_十个技能都被加载(self):
        names = {item.meta.name for item in _computer_skills()}
        assert names == set(_EXPECTED), f"缺少或多出：{names ^ set(_EXPECTED)}"

    def test_每一个都是confirm级(self):
        """产品约定是「每一步都先问」—— 这条钉住它。

        ⚠️ 连只读的（列出窗口 / 读界面元素）也必须是 confirm：用户明确选了
        比"按风险分级"更严的那一侧，把它们降成 safe 等于替他改了主意。
        """
        for item in _computer_skills():
            assert item.meta.permission_level == "confirm", item.meta.name

    def test_每一个都带了识别标签与描述(self):
        """标签是前端识别用的（虽然现在靠名字前缀，留着以防以后改口径）；
        描述是模型决定要不要调它的**唯一**依据，缺了等于这个技能不存在。
        """
        for item in _computer_skills():
            assert "电脑操作" in (item.meta.tags or []), item.meta.name
            assert item.meta.description.strip(), item.meta.name
            assert item.meta.display_name.strip(), item.meta.name


class TestParams:
    def test_滚轮格数有上限(self):
        with pytest.raises(ValidationError):
            MouseScrollParams(amount=999)

    def test_按键数量有上限(self):
        with pytest.raises(ValidationError):
            PressKeysParams(keys=["a", "b", "c", "d", "e"])

    def test_输入文字不能为空(self):
        with pytest.raises(ValidationError):
            TypeTextParams(text="")

    def test_点击次数只能是123(self):
        with pytest.raises(ValidationError):
            MouseClickParams(x=1, y=1, clicks=9)

    def test_读屏条数有上限(self):
        with pytest.raises(ValidationError):
            ReadScreenParams(max_items=9999)


class TestVkMapping:
    def test_认得出常见键(self):
        assert windows_api._vk_for("enter") == 0x0D
        assert windows_api._vk_for("Ctrl") == 0x11  # 大小写不敏感
        assert windows_api._vk_for("f12") == 0x7B
        assert windows_api._vk_for("a") == ord("A")

    def test_认不出的键如实报错(self):
        with pytest.raises(windows_api.WindowsApiError) as info:
            windows_api._vk_for("这个键不存在")
        assert "认不出" in info.value.message


class TestCoordinates:
    def test_越界的坐标如实报错(self, monkeypatch):
        """越界必须报错，**不能**悄悄夹到边缘：夹过去等于点了另一个地方，
        而模型会以为它点的正是自己说的那个坐标。"""
        monkeypatch.setattr(windows_api, "virtual_screen", lambda: (0, 0, 1920, 1080))
        with pytest.raises(windows_api.WindowsApiError) as info:
            windows_api._absolute(5000, 100)
        assert "不在屏幕范围内" in info.value.message

    def test_四个角换算到_0_与_65535(self, monkeypatch):
        monkeypatch.setattr(windows_api, "virtual_screen", lambda: (0, 0, 1920, 1080))
        assert windows_api._absolute(0, 0) == (0, 0)
        assert windows_api._absolute(1919, 1079) == (65535, 65535)

    def test_越往右下数值越大(self, monkeypatch):
        monkeypatch.setattr(windows_api, "virtual_screen", lambda: (0, 0, 1920, 1080))
        near = windows_api._absolute(100, 100)
        far = windows_api._absolute(1800, 1000)
        assert near[0] < far[0]
        assert near[1] < far[1]

    def test_副屏上的负坐标也算得出来(self, monkeypatch):
        """多显示器时虚拟桌面原点可能是负数（副屏在主屏左侧/上方）。"""
        monkeypatch.setattr(windows_api, "virtual_screen", lambda: (-1920, 0, 3840, 1080))
        assert windows_api._absolute(-1920, 0) == (0, 0)
        assert windows_api._absolute(1919, 1079) == (65535, 65535)
