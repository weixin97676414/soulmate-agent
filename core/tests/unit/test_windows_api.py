"""Windows 桌面能力底座：剪贴板、PowerShell 调用、亮度、截图。

测试策略：

- **能安全真跑的**就真跑（剪贴板文本往返、截图落文件、PowerShell 超时与退出码）；
- **会打扰用户的**（改音量、改亮度、锁屏）一律不真跑 —— 替换掉 PowerShell
  调用，只验证"命令构造对不对、结果解析对不对、不支持时会不会如实报错"。

剪贴板用例**必须把用户原来的内容还回去**：测试把人家正复制着的东西弄丢，
是很讨厌的一件事。
"""

from __future__ import annotations

import ctypes
import sys
import uuid

import pytest

from my_agent.utils import windows_api

WINDOWS = sys.platform == "win32"
on_windows = pytest.mark.skipif(not WINDOWS, reason="这些能力只在 Windows 上存在")
off_windows = pytest.mark.skipif(WINDOWS, reason="仅用于验证非 Windows 上的提示文案")


class TestPlatformGuard:
    @off_windows
    def test_other_platforms_get_a_clear_hint(self, monkeypatch):
        monkeypatch.setattr(windows_api, "is_supported", lambda: False)

        with pytest.raises(windows_api.WindowsApiError) as info:
            windows_api.read_clipboard_text()

        # 提示里必须点明"这是系统限制"，否则用户会以为是应用坏了
        assert "Windows" in info.value.message


class TestPowershell:
    @on_windows
    @pytest.mark.asyncio
    async def test_timeout_is_reported_not_hung(self):
        """超时必须**很快**抛错并杀掉进程 —— 挂在那里等人点是最糟的表现。"""
        with pytest.raises(windows_api.WindowsApiError) as info:
            await windows_api.run_powershell("Start-Sleep -Seconds 10", timeout=0.3)

        assert "超时" in info.value.message

    @on_windows
    @pytest.mark.asyncio
    async def test_nonzero_exit_keeps_the_output(self):
        with pytest.raises(windows_api.WindowsApiError) as info:
            await windows_api.run_powershell("Write-Output 'boom'; exit 3")

        assert "失败" in info.value.message
        assert "boom" in info.value.detail

    def test_quote_escapes_single_quotes(self):
        """路径里有单引号（用户目录 `l'y` 这种）不能把脚本拼坏。"""
        assert windows_api._ps_quote("a'b") == "'a''b'"
        assert windows_api._ps_quote(r"C:\tmp\x.png") == r"'C:\tmp\x.png'"


class TestClipboard:
    @on_windows
    def test_text_round_trip_and_restore(self):
        original = windows_api.read_clipboard_text()
        marker = f"剪贴板往返测试-{uuid.uuid4().hex[:8]}"
        try:
            windows_api.write_clipboard_text(marker)
            assert windows_api.read_clipboard_text() == marker

            windows_api.write_clipboard_text("第一行\n第二行 中文")
            assert windows_api.read_clipboard_text() == "第一行\n第二行 中文"
        finally:
            # 把用户原来复制的东西还回去
            windows_api.write_clipboard_text(original)

    @on_windows
    @pytest.mark.asyncio
    async def test_image_write_and_read(self, tmp_path):
        """写图片 → 读回来落成文件：证明两个方向都能用。"""
        from my_agent.utils import windows_api as api

        source = tmp_path / "src.png"
        await api.capture_screen(source)
        assert source.exists()

        original_text = api.read_clipboard_text()
        try:
            await api.set_clipboard_image(source)
            target = tmp_path / "back.png"
            assert await api.save_clipboard_image(target) is True
            assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        finally:
            # 剪贴板里现在是一张图：清掉再恢复文本（SetImage 之后空文本会覆盖它）
            api.write_clipboard_text(original_text)


class TestBrightness:
    """亮度：**不支持时必须如实报错**，绝不返回成功。"""

    @on_windows
    @pytest.mark.asyncio
    async def test_unsupported_is_reported(self, monkeypatch):
        async def fake(_script: str, timeout: float = 20.0) -> str:
            return "UNSUPPORTED"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        with pytest.raises(windows_api.WindowsApiError) as info:
            await windows_api.get_brightness()

        assert "不支持" in info.value.message

    @on_windows
    @pytest.mark.asyncio
    async def test_set_brightness_clamps_to_range(self, monkeypatch):
        seen: dict[str, str] = {}

        async def fake(script: str, timeout: float = 20.0) -> str:
            seen["script"] = script
            return "OK"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        assert await windows_api.set_brightness(150) == 100
        assert "Brightness = 100" in seen["script"]
        assert await windows_api.set_brightness(-20) == 0
        assert "Brightness = 0" in seen["script"]


class TestVolume:
    """音量 / 静音：**读得到状态、set 会解除静音**（用户报的两个缺陷）。

    这里不真跑 PowerShell（改音量会打扰用户），只验证脚本构造与结果解析。
    """

    def test_parse_state_accepts_csharp_output(self):
        assert windows_api._parse_volume_state("30;0") == (30, False)
        assert windows_api._parse_volume_state("0;1") == (0, True)

    def test_parse_state_ignores_noise_and_clamps(self):
        # Add-Type 偶尔会吐出编译警告之类的噪音行，真正的值在最后一行
        assert windows_api._parse_volume_state("某个警告\n150;1\n") == (100, True)

    def test_parse_state_returns_none_for_garbage(self):
        assert windows_api._parse_volume_state("OK") is None
        assert windows_api._parse_volume_state("") is None

    @pytest.mark.asyncio
    async def test_set_percent_unmutes_and_reports_state(self, monkeypatch):
        seen: dict[str, str] = {}

        async def fake(script: str, timeout: float = 20.0) -> str:
            seen["script"] = script
            return "30;0"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        assert await windows_api.set_volume_percent(30) == (30, False)
        # 关键：同一次调用里既设了音量、又解除了静音（只设标量的话仍然没声音）
        assert "[Audio]::SetVolume(0.3, 1)" in seen["script"]

    @pytest.mark.asyncio
    async def test_get_state_changes_nothing(self, monkeypatch):
        seen: dict[str, str] = {}

        async def fake(script: str, timeout: float = 20.0) -> str:
            seen["script"] = script
            return "0;1"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        assert await windows_api.get_volume_state() == (0, True)
        # 只读：脚本里不能出现任何"写"的调用（`[Audio]::` 是调用，C# 里的定义不算）
        assert "[Audio]::SetVolume" not in seen["script"]
        assert "[Audio]::SetMute" not in seen["script"]

    @pytest.mark.asyncio
    async def test_muted_is_explicit_not_a_blind_toggle(self, monkeypatch):
        seen: dict[str, str] = {}

        async def fake(script: str, timeout: float = 20.0) -> str:
            seen["script"] = script
            return "50;0"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        assert await windows_api.set_muted(False) == (50, False)
        # 明确的 SetMute(0)，而不是敲一下媒体键让系统自己去翻
        assert "[Audio]::SetMute(0)" in seen["script"]

    @pytest.mark.asyncio
    async def test_unparseable_state_raises_instead_of_guessing(self, monkeypatch):
        async def fake(script: str, timeout: float = 20.0) -> str:
            return "OK"

        monkeypatch.setattr(windows_api, "run_powershell", fake)

        with pytest.raises(windows_api.WindowsApiError):
            await windows_api.get_volume_state()


class TestScreenshot:
    @on_windows
    @pytest.mark.asyncio
    async def test_capture_writes_a_real_png(self, tmp_path):
        target = tmp_path / "shot.png"

        await windows_api.capture_screen(target)

        assert target.exists()
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    @on_windows
    @pytest.mark.asyncio
    async def test_empty_region_is_rejected_before_calling_out(self, tmp_path):
        with pytest.raises(windows_api.WindowsApiError) as info:
            await windows_api.capture_screen(tmp_path / "x.png", region=(0, 0, 0, 100))

        assert "宽高" in info.value.message


class TestInputInjection:
    """键鼠注入 —— **只验证"不真动手"的那部分**。

    真的移动鼠标 / 敲键盘会打断用户手头的事（他可能正拖着文件），
    测试绝不该有这种副作用。真正发送的路径由人工验收：
    让搭子"把鼠标移到屏幕正中"，看光标动没动。
    """

    def test_input_结构体的尺寸正确(self):
        """⚠️ 尺寸错了 SendInput 会读到垃圾数据，而且**不报错** ——
        用户看到的只是"点了但没反应 / 点到了别的地方"，极难定位。所以钉死它。
        """
        if sys.maxsize > 2**32:
            assert ctypes.sizeof(windows_api._INPUT) == 40
            assert ctypes.sizeof(windows_api._MOUSEINPUT) == 32
            assert ctypes.sizeof(windows_api._KEYBDINPUT) == 24

    @off_windows
    def test_非_windows_上如实报错(self, monkeypatch):
        monkeypatch.setattr(windows_api, "is_supported", lambda: False)

        with pytest.raises(windows_api.WindowsApiError):
            windows_api.mouse_move(1, 1)

    def test_鼠标键名非法时报错(self):
        with pytest.raises(windows_api.WindowsApiError) as info:
            windows_api._require_button("滚轮")

        assert "不支持的鼠标键" in info.value.message

    def test_释放输入永不抛异常(self):
        """`release_all_inputs` 是"鼠标卡住时的自救入口"：在一个已经很糟的状态下
        再抛一个异常，只会把真正的问题盖掉。所以它必须**永不抛错**。
        """
        windows_api.release_all_inputs()

    @on_windows
    def test_虚拟屏幕尺寸是正数(self):
        _, _, width, height = windows_api.virtual_screen()

        assert width > 0 and height > 0

    @on_windows
    def test_窗口枚举的结构完整(self):
        """只读操作，可以真跑（不会碰用户的任何东西）。"""
        windows = windows_api.list_windows()

        assert isinstance(windows, list)
        for item in windows:
            assert set(item) >= {
                "handle",
                "title",
                "foreground",
                "left",
                "top",
                "width",
                "height",
            }
            # 无标题的窗口（输入法候选框、托盘宿主）被刻意过滤掉了
            assert item["title"]
