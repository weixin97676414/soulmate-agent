









from __future__ import annotations

import sys
import uuid

import pytest

from my_agent.config.paths import AppPaths
from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.clipboard import (
    ClipboardReadImageSkill,
    ClipboardReadTextSkill,
    ClipboardWriteSkill,
)
from my_agent.skill.builtin.system_control import (
    BrightnessGetSkill,
    BrightnessSetSkill,
    LockScreenSkill,
    ScreenshotParams,
    ScreenshotSkill,
    VolumeGetSkill,
    VolumeSkill,
)
from my_agent.utils import windows_api

WINDOWS = sys.platform == "win32"
on_windows = pytest.mark.skipif(not WINDOWS, reason="这些能力只在 Windows 上存在")


def make_ctx(tmp_path) -> SkillContext:
    paths = AppPaths(tmp_path / "AgentDesktop").ensure()
    return SkillContext(paths=paths, session_id="test-session")


class TestPermissionLevels:
    def test_read_only_is_safe_mutating_needs_confirm(self):
        assert ClipboardReadTextSkill.meta.permission_level == "safe"
        assert BrightnessGetSkill.meta.permission_level == "safe"
        
        assert VolumeGetSkill.meta.permission_level == "safe"

        assert ClipboardReadImageSkill.meta.permission_level == "confirm"
        assert ClipboardWriteSkill.meta.permission_level == "confirm"
        assert VolumeSkill.meta.permission_level == "confirm"
        assert BrightnessSetSkill.meta.permission_level == "confirm"
        assert LockScreenSkill.meta.permission_level == "confirm"
        assert ScreenshotSkill.meta.permission_level == "confirm"


class TestClipboardSkills:
    @on_windows
    @pytest.mark.asyncio
    async def test_read_text_returns_content(self, tmp_path):
        original = windows_api.read_clipboard_text()
        marker = f"技能读取测试-{uuid.uuid4().hex[:6]}"
        try:
            windows_api.write_clipboard_text(marker)
            result = await ClipboardReadTextSkill().run(make_ctx(tmp_path))
            assert result["text"] == marker
            assert result["length"] == len(marker)
        finally:
            windows_api.write_clipboard_text(original)

    @on_windows
    @pytest.mark.asyncio
    async def test_write_requires_exactly_one_payload(self, tmp_path):
        ctx = make_ctx(tmp_path)

        with pytest.raises(SkillExecutionError) as info:
            await ClipboardWriteSkill().run(ctx, text="x", image_path="y")
        assert "一个" in str(info.value)

        with pytest.raises(SkillExecutionError):
            await ClipboardWriteSkill().run(ctx)

    @on_windows
    @pytest.mark.asyncio
    async def test_write_text_then_read_back(self, tmp_path):
        ctx = make_ctx(tmp_path)
        original = windows_api.read_clipboard_text()
        try:
            marker = f"写入测试-{uuid.uuid4().hex[:6]}"
            result = await ClipboardWriteSkill().run(ctx, text=marker)
            assert result["ok"] is True and result["kind"] == "text"
            assert windows_api.read_clipboard_text() == marker
        finally:
            windows_api.write_clipboard_text(original)

    @on_windows
    @pytest.mark.asyncio
    async def test_read_image_saves_artifact(self, tmp_path):

        ctx = make_ctx(tmp_path)
        shot = tmp_path / "probe.png"
        original = windows_api.read_clipboard_text()
        try:
            await windows_api.capture_screen(shot)
            await windows_api.set_clipboard_image(shot)

            result = await ClipboardReadImageSkill().run(ctx)

            assert result["saved"] is True
            assert result["artifact"]["id"].endswith(".png")
        finally:
            windows_api.write_clipboard_text(original)


class TestSystemControlSkills:
    @pytest.mark.asyncio
    async def test_volume_set_requires_percent(self, tmp_path):
        with pytest.raises(SkillExecutionError) as info:
            await VolumeSkill().run(make_ctx(tmp_path), action="set")

        assert "percent" in str(info.value)

    @pytest.mark.asyncio
    async def test_volume_rejects_unknown_action(self, tmp_path):

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            await VolumeSkill().run(make_ctx(tmp_path), action="louder")

    @pytest.mark.asyncio
    async def test_volume_get_reports_percent_and_muted(self, tmp_path, monkeypatch):


        async def fake_state() -> tuple[int, bool]:
            return 42, True

        monkeypatch.setattr(windows_api, "get_volume_state", fake_state)

        result = await VolumeGetSkill().run(make_ctx(tmp_path))

        assert result["percent"] == 42
        assert result["muted"] is True
        assert "已静音" in result["message"]

    @pytest.mark.asyncio
    async def test_volume_set_unmutes_and_reports_state(self, tmp_path, monkeypatch):

        seen: dict[str, int] = {}

        async def fake_set(percent: int, *, unmute: bool = True) -> tuple[int, bool]:
            seen["percent"] = percent
            seen["unmute"] = int(unmute)
            return percent, False

        monkeypatch.setattr(windows_api, "set_volume_percent", fake_set)

        result = await VolumeSkill().run(make_ctx(tmp_path), action="set", percent=30)

        assert seen == {"percent": 30, "unmute": 1}
        assert result["percent"] == 30
        assert result["muted"] is False
        assert "解除静音" in result["message"]

    @pytest.mark.asyncio
    async def test_volume_mute_with_explicit_target(self, tmp_path, monkeypatch):

        seen: dict[str, bool] = {}

        async def fake_mute(muted: bool) -> tuple[int, bool]:
            seen["muted"] = muted
            return 50, muted

        monkeypatch.setattr(windows_api, "set_muted", fake_mute)

        result = await VolumeSkill().run(make_ctx(tmp_path), action="mute", muted=True)

        assert seen["muted"] is True
        assert result["muted"] is True
        assert result["message"] == "已静音。"

    @pytest.mark.asyncio
    async def test_volume_mute_without_target_flips_current_state(self, tmp_path, monkeypatch):


        async def fake_state() -> tuple[int, bool]:
            return 50, True

        async def fake_mute(muted: bool) -> tuple[int, bool]:
            return 50, muted

        monkeypatch.setattr(windows_api, "get_volume_state", fake_state)
        monkeypatch.setattr(windows_api, "set_muted", fake_mute)

        result = await VolumeSkill().run(make_ctx(tmp_path), action="mute")

        assert result["muted"] is False
        assert result["message"] == "已取消静音。"

    @pytest.mark.asyncio
    async def test_brightness_get_reports_unsupported_as_fact(self, tmp_path, monkeypatch):


        async def boom() -> int:
            raise windows_api.WindowsApiError(windows_api._BRIGHTNESS_UNSUPPORTED)

        monkeypatch.setattr(windows_api, "get_brightness", boom)

        result = await BrightnessGetSkill().run(make_ctx(tmp_path))

        assert result["supported"] is False
        assert "不支持" in result["message"]

    @pytest.mark.asyncio
    async def test_brightness_set_raises_when_unsupported(self, tmp_path, monkeypatch):


        async def boom(_percent: int) -> int:
            raise windows_api.WindowsApiError(windows_api._BRIGHTNESS_UNSUPPORTED)

        monkeypatch.setattr(windows_api, "set_brightness", boom)

        with pytest.raises(SkillExecutionError) as info:
            await BrightnessSetSkill().run(make_ctx(tmp_path), percent=50)

        assert "不支持" in str(info.value)

    @pytest.mark.asyncio
    async def test_brightness_delta_uses_current_value(self, tmp_path, monkeypatch):
        seen: dict[str, int] = {}

        async def fake_get() -> int:
            return 40

        async def fake_set(percent: int) -> int:
            seen["percent"] = percent
            return percent

        monkeypatch.setattr(windows_api, "get_brightness", fake_get)
        monkeypatch.setattr(windows_api, "set_brightness", fake_set)

        result = await BrightnessSetSkill().run(make_ctx(tmp_path), delta=10)

        assert seen["percent"] == 50
        assert result["percent"] == 50

    @on_windows
    @pytest.mark.asyncio
    async def test_screenshot_saves_artifact(self, tmp_path):
        ctx = make_ctx(tmp_path)

        result = await ScreenshotSkill().run(ctx, **ScreenshotParams().model_dump())

        assert result["artifact"]["id"].endswith(".png")
        assert "产物" in result["message"] or "预览" in result["message"]

    @pytest.mark.asyncio
    async def test_screenshot_partial_region_is_rejected(self, tmp_path):
        with pytest.raises(SkillExecutionError) as info:
            await ScreenshotSkill().run(make_ctx(tmp_path), x=10, y=10, width=100)

        assert "四个值" in str(info.value)

    @pytest.mark.asyncio
    async def test_screenshot_failure_is_translated(self, tmp_path, monkeypatch):


        async def boom(_target, *, region=None) -> None:
            raise windows_api.WindowsApiError("截图失败")

        monkeypatch.setattr(windows_api, "capture_screen", boom)

        with pytest.raises(SkillExecutionError):
            await ScreenshotSkill().run(make_ctx(tmp_path))
