












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





        for item in _computer_skills():
            assert item.meta.permission_level == "confirm", item.meta.name

    def test_每一个都带了识别标签与描述(self):



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
        assert windows_api._vk_for("Ctrl") == 0x11  
        assert windows_api._vk_for("f12") == 0x7B
        assert windows_api._vk_for("a") == ord("A")

    def test_认不出的键如实报错(self):
        with pytest.raises(windows_api.WindowsApiError) as info:
            windows_api._vk_for("这个键不存在")
        assert "认不出" in info.value.message


class TestCoordinates:
    def test_越界的坐标如实报错(self, monkeypatch):


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

        monkeypatch.setattr(windows_api, "virtual_screen", lambda: (-1920, 0, 3840, 1080))
        assert windows_api._absolute(-1920, 0) == (0, 0)
        assert windows_api._absolute(1919, 1079) == (65535, 65535)
