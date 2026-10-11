"""Windows 桌面能力底座：剪贴板、音量、亮度、锁屏、截图。

## 为什么是「标准库 + 系统自带命令」

这三类能力在 Windows 上要么走 Win32 API（`ctypes` 就能调），要么走系统自带的
PowerShell（.NET 的 `System.Drawing` / `System.Windows.Forms` 与 WMI）。
两条路都**不需要新增任何依赖**，而冻结产物已经 918 MB —— 每加一个第三方包
都要同时改 `build/agent-core.spec` 并承担 onedir 下原生 DLL 的风险。

（`pywin32` 虽然躺在开发虚拟环境里，但它不在 `pyproject.toml` 中、也没被收进
冻结产物 —— 用它就会出现"开发机上好好的、打包后 ImportError"这种最难查的故障。）

## 调用约定

- 所有系统调用**只在这个模块里**：技能层不自己拼命令、不写 ctypes。
- 失败一律抛 ``WindowsApiError``，由技能层转成 ``SkillExecutionError``。
- **能力不支持时必须明确报错，绝不返回成功**：亮度在台式机/外接显示器上根本
  调不了，假装成功只会让用户以为"这个功能坏了"。
- 日志里不记剪贴板内容（可能含密码或私密文字），只记操作类型与长度。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 非 Windows 平台上的统一提示（技能会原样转述给用户）。
WINDOWS_ONLY_HINT = "该功能依赖 Windows 系统能力，当前系统不支持。"

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_GMEM_ZEROINIT = 0x0040

# 媒体键的虚拟键码：音量**增减**用它们最稳 —— 不需要 COM、不需要第三方库，
# 而且效果与用户按键盘上的音量键完全一致（系统会弹出音量提示）。
# （没有 `_VK_VOLUME_MUTE`：静音不走媒体键，见 `volume_step` 的说明。）
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF

_KEYEVENTF_KEYUP = 0x0002


class WindowsApiError(Exception):
    """调用系统能力失败，或当前机器/系统不支持该能力。"""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


def is_supported() -> bool:
    """当前环境是否具备这些 Windows 能力。"""
    return sys.platform == "win32"


if is_supported():  # pragma: no cover - 非 Windows 下不加载 DLL
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # ⚠️ 句柄是**指针**：64 位下不声明 restype/argtypes，ctypes 会把返回值截成
    # 32 位整数，于是拿到一个永远无效的句柄 —— 表现是"读剪贴板偶尔读出乱码"，
    # 极难定位。下面这几行不是样板代码，是必需的。
    _user32.GetClipboardData.restype = ctypes.c_void_p
    _user32.GetClipboardData.argtypes = [ctypes.c_uint]
    _user32.SetClipboardData.restype = ctypes.c_void_p
    _user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    _user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    _user32.EmptyClipboard.restype = ctypes.c_bool
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
else:  # pragma: no cover - 非 Windows
    _user32 = None
    _kernel32 = None


# --------------------------------------------------------------------------- #
# PowerShell：统一的调用、超时与报错
# --------------------------------------------------------------------------- #
async def run_powershell(script: str, *, timeout: float = 20.0) -> str:
    """跑一段内联 PowerShell，返回标准输出（已按 UTF-8 尽力解码）。

    ``-NoProfile`` 是必须的：用户机器上的 profile 可能改输出编码、甚至弹窗要人点。
    ``-NonInteractive`` 则保证它永远不等人输入（一等人就挂到超时）。
    """
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)

    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        # 先钉住输出编码，否则中文（例如截图路径、错误信息）会按 GBK 出来变乱码
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;\n" + script,
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        # **必须回收**：不 wait 的话，进程对象会在事件循环关闭后才被 GC，
        # 析构里那句 `pipe.close()` 会抛 "Event loop is closed" 到 stderr ——
        # 用户看到的是日志里一堆莫名其妙的报错，而排查方向完全被带偏。
        with contextlib.suppress(Exception):
            await asyncio.wait_for(process.wait(), timeout=5.0)
        raise WindowsApiError(f"系统命令执行超时（{timeout:.0f} 秒）") from None

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise WindowsApiError("系统命令执行失败", detail=text[-500:] or f"退出码{process.returncode}")
    return text


def _ps_quote(value: str) -> str:
    """把字符串安全地放进 PowerShell 的单引号里。

    只做一件事：把单引号翻倍（PowerShell 的转义规则）。
    绝不把用户输入直接拼进脚本腔里 —— 那等于在本机开了一个命令注入的口子。
    """
    return "'" + value.replace("'", "''") + "'"


# --------------------------------------------------------------------------- #
# 剪贴板
# --------------------------------------------------------------------------- #
def _open_clipboard(retries: int = 5) -> None:
    """占用剪贴板。

    剪贴板是**全局独占**资源：别的程序正拿着它时 `OpenClipboard` 会直接失败。
    这种情况很常见（输入法、剪贴板管理器），所以短暂重试几次，
    而不是让用户看到"读剪贴板失败"这种没法自救的报错。
    """
    assert _user32 is not None
    import time

    for attempt in range(retries):
        if _user32.OpenClipboard(None):
            return
        time.sleep(0.05 * (attempt + 1))
    raise WindowsApiError("剪贴板被其它程序占用，稍后再试。")


def read_clipboard_text() -> str:
    """取剪贴板里的文本；没有文本时返回空串。"""
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None and _kernel32 is not None

    _open_clipboard()
    try:
        handle = _user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.c_wchar_p(pointer).value or ""
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def write_clipboard_text(text: str) -> None:
    """把文本放进剪贴板（会覆盖原有内容）。"""
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None and _kernel32 is not None

    buffer = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(buffer)
    handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE | _GMEM_ZEROINIT, size)
    if not handle:
        raise WindowsApiError("申请剪贴板内存失败。")

    pointer = _kernel32.GlobalLock(handle)
    if not pointer:
        _kernel32.GlobalFree(handle)
        raise WindowsApiError("锁定剪贴板内存失败。")
    ctypes.memmove(pointer, buffer, size)
    _kernel32.GlobalUnlock(handle)

    _open_clipboard()
    try:
        if not _user32.EmptyClipboard():
            _kernel32.GlobalFree(handle)
            raise WindowsApiError("清空剪贴板失败。")
        if not _user32.SetClipboardData(_CF_UNICODETEXT, handle):
            _kernel32.GlobalFree(handle)
            raise WindowsApiError("写入剪贴板失败。")
        # 所有权已交给系统：这里**不能**再 GlobalFree，否则剪贴板里是指向已释放内存的指针，
        # 用户一粘贴就是一段乱码甚至让目标程序崩掉。
    finally:
        _user32.CloseClipboard()


async def save_clipboard_image(target: Path) -> bool:
    """把剪贴板里的图片存成 PNG；剪贴板里没有图片时返回 False。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$img = [Windows.Forms.Clipboard]::GetImage();"
        "if ($img -eq $null) { Write-Output 'EMPTY'; exit 0 };"
        f"$img.Save({_ps_quote(str(target))}, [System.Drawing.Imaging.ImageFormat]::Png);"
        "$img.Dispose();"
        "Write-Output 'OK'"
    )
    output = await run_powershell(script)
    return output.strip().endswith("OK")


async def set_clipboard_image(source: Path) -> None:
    """把一张图片放进剪贴板（可直接粘贴进其它程序）。"""
    if not source.exists():
        raise WindowsApiError(f"图片不存在：{source}")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        f"$img = [System.Drawing.Image]::FromFile({_ps_quote(str(source))});"
        # SetImage 之后文件句柄仍被占用会挡住后续删除，所以先复制一份再交出去
        "$copy = New-Object System.Drawing.Bitmap($img);"
        "[Windows.Forms.Clipboard]::SetImage($copy);"
        "$copy.Dispose(); $img.Dispose();"
        "Write-Output 'OK'"
    )
    await run_powershell(script)


# --------------------------------------------------------------------------- #
# 音量与亮度
# --------------------------------------------------------------------------- #
def _tap_media_key(key_code: int, times: int = 1) -> None:
    """模拟按一下媒体键。"""
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    for _ in range(max(1, min(times, 50))):
        _user32.keybd_event(key_code, 0, 0, 0)
        _user32.keybd_event(key_code, 0, _KEYEVENTF_KEYUP, 0)


def volume_step(action: str, *, times: int = 2) -> None:
    """调高 / 调低 —— 走媒体键，改动立即可见（系统会弹音量提示）。

    ⚠️ **静音不走这里**：媒体键的 ``VK_VOLUME_MUTE`` 是"切换"，落到哪一边取决于
    执行前的状态，而媒体键路径**读不到状态** —— 工具就没法告诉模型"现在到底静音没有"。
    静音请用 ``set_muted()``（走 CoreAudio，能读能写）。
    """
    if action == "up":
        _tap_media_key(_VK_VOLUME_UP, times)
    elif action == "down":
        _tap_media_key(_VK_VOLUME_DOWN, times)
    else:
        raise WindowsApiError(f"不支持的音量操作：{action}")


# CoreAudio 的 IAudioEndpointVolume 互操作：内联 C# + Add-Type，不需要任何第三方依赖。
#
# ⚠️ **槽位必须与真实 vtable 严格对齐**。C# 用 `InterfaceIsIUnknown` 声明 COM 接口时，
# IUnknown 的三个方法由运行时自动占位，所以下面第 i 个方法对应真实 vtable 的第 3+i 槽。
# 真实顺序是：RegisterControlChangeNotify / UnregisterControlChangeNotify / GetChannelCount /
# SetMasterVolumeLevel / SetMasterVolumeLevelScalar / **GetMasterVolumeLevel** /
# GetMasterVolumeLevelScalar / SetChannelVolumeLevel / SetChannelVolumeLevelScalar /
# GetChannelVolumeLevel / GetChannelVolumeLevelScalar / SetMute / GetMute / …
#
# 也就是说 **GetMasterVolumeLevel 一个占位都不能少**：漏了它，GetMasterVolumeLevelScalar
# 会落到它的槽上，读回来的是 dB 值（负数）而不是 0~1 的标量 —— 而且**不会报错**。
# `SetMute` / `GetMute` 的 BOOL 一律用 int 声明（COM 的 BOOL 就是 4 字节 int），
# 避开 C# bool 默认封送宽度的歧义。
_VOLUME_INTEROP = (
    "Add-Type -TypeDefinition @'\n"
    "using System.Runtime.InteropServices;\n"
    "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
    "interface IAudioEndpointVolume {\n"
    "  int _0(); int _1(); int _2(); int _3();\n"
    "  int SetMasterVolumeLevelScalar(float level, ref System.Guid ctx);\n"
    "  int _4();\n"
    "  int GetMasterVolumeLevelScalar(out float level);\n"
    "  int _5(); int _6(); int _7(); int _8();\n"
    "  int SetMute(int mute, ref System.Guid ctx);\n"
    "  int GetMute(out int muted);\n"
    "}\n"
    "[Guid(\"D666063F-1587-4E43-81F1-B948E807363F\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
    "interface IMMDevice { int Activate(ref System.Guid id, int clsCtx, System.IntPtr activationParams, out IAudioEndpointVolume volume); }\n"
    "[Guid(\"A95664D2-9614-4F35-A746-DE8DB63617E6\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
    "interface IMMDeviceEnumerator { int f(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); }\n"
    "[ComImport, Guid(\"BCDE0395-E52F-467C-8E3D-C4579291692E\")] class MMDeviceEnumeratorComObject { }\n"
    "public class Audio {\n"
    "  static IAudioEndpointVolume Open() {\n"
    "    var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());\n"
    "    IMMDevice device; enumerator.GetDefaultAudioEndpoint(0, 1, out device);\n"
    "    var iid = typeof(IAudioEndpointVolume).GUID;\n"
    "    IAudioEndpointVolume volume;\n"
    "    device.Activate(ref iid, 23, System.IntPtr.Zero, out volume);\n"
    "    return volume;\n"
    "  }\n"
    "  public static void SetVolume(float level, int unmute) {\n"
    "    var volume = Open();\n"
    "    System.Guid ctx = System.Guid.Empty;\n"
    "    volume.SetMasterVolumeLevelScalar(level, ref ctx);\n"
    "    if (unmute != 0) volume.SetMute(0, ref ctx);\n"
    "  }\n"
    "  public static void SetMute(int mute) {\n"
    "    var volume = Open();\n"
    "    System.Guid ctx = System.Guid.Empty;\n"
    "    volume.SetMute(mute, ref ctx);\n"
    "  }\n"
    "  public static string GetState() {\n"
    "    var volume = Open();\n"
    "    float level; int muted;\n"
    "    volume.GetMasterVolumeLevelScalar(out level);\n"
    "    volume.GetMute(out muted);\n"
    "    return ((int)System.Math.Round(level * 100)) + \";\" + (muted != 0 ? \"1\" : \"0\");\n"
    "  }\n"
    "}\n"
    "'@;"
)

#: 回读音量状态的那半句：C# 侧输出 ``"30;0"``（百分比 ; 是否静音）。
_VOLUME_STATE_COMMAND = "Write-Output ([Audio]::GetState())"


def _parse_volume_state(output: str) -> tuple[int, bool] | None:
    """把 C# 吐出的 ``"30;0"`` 解析成 ``(30, False)``；认不出来时返回 ``None``。

    从后往前找：前面可能混着 Add-Type 的编译警告之类的噪音行。
    """
    for line in reversed(output.strip().splitlines()):
        left, sep, right = line.strip().partition(";")
        if not sep:
            continue
        try:
            return max(0, min(int(left), 100)), right.strip() == "1"
        except ValueError:
            continue
    return None


async def _run_volume_script(script: str, action: str) -> tuple[int, bool]:
    """跑一段"改完就回报状态"的音量脚本；读不回状态时报错而不是猜。"""
    output = await run_powershell(_VOLUME_INTEROP + script, timeout=30.0)
    state = _parse_volume_state(output)
    if state is None:
        # 宁可报错也不猜：这一路存在的意义就是"让模型拿到真实状态"
        raise WindowsApiError(f"{action}后读回的音量状态无法解析。", detail=output[-200:])
    return state


async def get_volume_state() -> tuple[int, bool]:
    """读当前音量百分比与是否静音，返回 ``(percent, muted)``。"""
    return await _run_volume_script(_VOLUME_STATE_COMMAND, "读取音量")


async def set_volume_percent(percent: int, *, unmute: bool = True) -> tuple[int, bool]:
    """把音量设成指定百分比，并（默认）**解除静音**；返回 ``(实际百分比, 是否静音)``。

    为什么顺带解除静音：``SetMasterVolumeLevelScalar`` 只改音量标量、**不动静音位**，
    所以系统正静音时"把音量调到 30%"的结果是"数字变了、还是没声音"，而工具回报的
    却是"音量已设为 30%" —— 用户和模型都以为设好了。这类"看起来成功、其实没生效"
    最难排查，所以设置音量时就顺手取消静音。

    媒体键只能"一格格调"、做不到"设成 30%"，所以这一步走系统的 CoreAudio
    （脚本内联 C# + ``Add-Type``，不需要任何第三方依赖）。
    """
    value = max(0, min(int(percent), 100))
    script = f"[Audio]::SetVolume({value / 100}, {1 if unmute else 0});" + _VOLUME_STATE_COMMAND
    return await _run_volume_script(script, "设置音量")


async def set_muted(muted: bool) -> tuple[int, bool]:
    """明确静音 / 取消静音（**不用媒体键**），返回 ``(实际百分比, 是否静音)``。

    媒体键的 ``VK_VOLUME_MUTE`` 是**切换**：落到哪一边取决于执行前的状态，而且读不到
    状态 —— 工具只能告诉模型"已切换静音状态"，模型只能猜。这里改成明确的
    "设成静音 / 取消静音"，并把操作后的真实状态一并回给模型。
    """
    script = f"[Audio]::SetMute({1 if muted else 0});" + _VOLUME_STATE_COMMAND
    return await _run_volume_script(script, "设置静音")


async def get_brightness() -> int:
    """读当前亮度百分比；**不支持时抛错**（台式机与多数外接显示器都没有这条 WMI）。"""
    script = (
        "$b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
        "-ErrorAction SilentlyContinue | Select-Object -First 1;"
        "if ($b -eq $null) { Write-Output 'UNSUPPORTED'; exit 0 };"
        "Write-Output $b.CurrentBrightness"
    )
    output = await run_powershell(script, timeout=30.0)
    if output.strip() == "UNSUPPORTED":
        raise WindowsApiError(_BRIGHTNESS_UNSUPPORTED)
    try:
        return int(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise WindowsApiError("读取屏幕亮度失败。", detail=output[:200]) from None


_BRIGHTNESS_UNSUPPORTED = (
    "这台机器不支持调节屏幕亮度（通常是台式机或外接显示器）。"
    "亮度由显示器自己控制，系统接口读不到也改不了。"
)


async def set_brightness(percent: int) -> int:
    """设置亮度，返回设置后的百分比。不支持时抛错。"""
    value = max(0, min(int(percent), 100))
    script = (
        "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
        "-ErrorAction SilentlyContinue | Select-Object -First 1;"
        "if ($m -eq $null) { Write-Output 'UNSUPPORTED'; exit 0 };"
        f"$m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{ Timeout = 1; Brightness = {value} }} "
        "| Out-Null;"
        "Write-Output 'OK'"
    )
    output = await run_powershell(script, timeout=30.0)
    if "UNSUPPORTED" in output:
        raise WindowsApiError(_BRIGHTNESS_UNSUPPORTED)
    return value


# --------------------------------------------------------------------------- #
# 锁屏与截图
# --------------------------------------------------------------------------- #
def lock_workstation() -> None:
    """锁定当前 Windows 会话。"""
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    if not _user32.LockWorkStation():
        raise WindowsApiError("锁定屏幕失败。")


async def capture_screen(
    target: Path,
    *,
    region: tuple[int, int, int, int] | None = None,
) -> None:
    """截屏并存成 PNG。

    ``region`` 给 ``(x, y, 宽, 高)`` 时只截这一块，否则截**所有显示器拼起来的
    整个虚拟桌面** —— 只截主屏会让"第二块屏幕上那个窗口"永远截不到。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if region is not None:
        x, y, width, height = (int(item) for item in region)
        if width <= 0 or height <= 0:
            raise WindowsApiError("截图区域的宽高必须大于 0。")
        bounds = f"$x = {x}; $y = {y}; $w = {width}; $h = {height}"
    else:
        # VirtualScreen 是"所有显示器合并后的矩形"，多屏时它的原点可能是负数
        bounds = (
            "$vs = [Windows.Forms.SystemInformation]::VirtualScreen;"
            "$x = $vs.X; $y = $vs.Y; $w = $vs.Width; $h = $vs.Height"
        )

    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        f"{bounds};"
        "if ($w -le 0 -or $h -le 0) { Write-Output 'EMPTY'; exit 0 };"
        "$bmp = New-Object System.Drawing.Bitmap($w, $h);"
        "$g = [System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size);"
        f"$bmp.Save({_ps_quote(str(target))}, [System.Drawing.Imaging.ImageFormat]::Png);"
        "$g.Dispose(); $bmp.Dispose();"
        "Write-Output 'OK'"
    )
    output = await run_powershell(script, timeout=30.0)
    if "OK" not in output or not target.exists():
        raise WindowsApiError("截图失败。", detail=output[:200])


# --------------------------------------------------------------------------- #
# 键盘与鼠标（SendInput）
# --------------------------------------------------------------------------- #
# 为什么用 ``SendInput`` 而不是更省事的 ``SetCursorPos`` / ``mouse_event`` /
# ``keybd_event``：
#   - ``mouse_event`` / ``keybd_event`` 已被微软标记为 superseded，多显示器与
#     高 DPI 下的行为不一致；
#   - ``SetCursorPos`` 只挪光标、**不产生输入事件**，一部分程序（自绘控件、
#     远程桌面、游戏）根本不响应；
#   - ``SendInput`` 是当前唯一被推荐的通用注入方式，而且能在**一个批次**里
#     完成"移动到 (x,y) + 按下 + 抬起"，中间不会插进别的鼠标移动。
#
# ⚠️ ``INPUT`` 结构体一个字节都不能错。64 位下它是 **40 字节**
#   （type 4 + 对齐 4 + union 最大成员 MOUSEINPUT 32）。用 ctypes 的默认对齐
#   就对了，但**必须显式声明 argtypes** —— 不声明时 ctypes 会按 32 位处理，
#   SendInput 读到的是垃圾（表现为"点了但没反应 / 点错地方"，且不报错）。
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1

_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000

#: 走 Unicode 码元而不是虚拟键码（中文 / 非美式布局只有这条路）
_KEYEVENTF_UNICODE = 0x0004

#: 滚轮一格
_WHEEL_DELTA = 120

#: ``GetSystemMetrics`` 的索引：整个虚拟桌面（所有显示器合并）的矩形
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_SW_RESTORE = 9

#: 一次 ``SendInput`` 批次的条数上限。太长的一批会被系统截断，而且中途
#: 不给事件循环让出的机会（"急停"就按不下去）。
_INPUT_BATCH = 200

#: ``EnumWindows`` 的回调类型。
#: ⚠️ ``ctypes.WINFUNCTYPE`` **只在 Windows 上存在**，非 Windows 直接取属性会
#: AttributeError，所以用 hasattr 兜一下。
#: ⚠️ 而且 ``WINFUNCTYPE`` 是**工厂函数**、不是类型 —— 必须先调用它构造出回调
#: 类型；把工厂本身塞进 ``argtypes`` 会报 "item 1 in _argtypes_ has no from_param
#: method"（模块**导入即崩**，不是运行到才崩）。
_WNDCALLBACK = (
    ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    if hasattr(ctypes, "WINFUNCTYPE")
    else None
)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTUNION)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


if is_supported():  # pragma: no cover - 非 Windows 下不加载 DLL
    _user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_uint
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    _user32.SetForegroundWindow.restype = ctypes.c_bool
    _user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.ShowWindow.restype = ctypes.c_bool
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.IsWindowVisible.restype = ctypes.c_bool
    _user32.IsIconic.argtypes = [ctypes.c_void_p]
    _user32.IsIconic.restype = ctypes.c_bool
    _user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
    _user32.GetWindowRect.restype = ctypes.c_bool
    assert _WNDCALLBACK is not None  # is_supported() 为真时它一定存在
    _user32.EnumWindows.argtypes = [_WNDCALLBACK, ctypes.c_void_p]
    _user32.EnumWindows.restype = ctypes.c_bool


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> _INPUT:
    item = _INPUT()
    item.type = _INPUT_MOUSE
    item.union.mi = _MOUSEINPUT(
        dx=dx,
        dy=dy,
        # 滚轮是**有符号**的：向下是负数，而 c_ulong 是无符号 —— 直接塞进去
        # ctypes 会抛 OverflowError（不是静默截断），所以先按 32 位补码转换。
        mouseData=data & 0xFFFFFFFF,
        dwFlags=flags,
        time=0,
        dwExtraInfo=None,
    )
    return item


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    item = _INPUT()
    item.type = _INPUT_KEYBOARD
    item.union.ki = _KEYBDINPUT(
        wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None
    )
    return item


def _send(inputs: list[_INPUT]) -> None:
    """发一批输入。失败**必须抛错** —— 静默失败会让模型以为点过了。"""
    if not inputs:
        return
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    array = (_INPUT * len(inputs))(*inputs)
    sent = _user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))
    if sent != len(inputs):
        raise WindowsApiError(
            "系统拒绝了这次键鼠操作。",
            detail=f"SendInput 返回 {sent}/{len(inputs)}，错误码 {ctypes.get_last_error()}",
        )


def virtual_screen() -> tuple[int, int, int, int]:
    """所有显示器合并后的矩形 ``(left, top, width, height)``。

    ⚠️ 多显示器时 ``left`` / ``top`` **可能是负数**（副屏在主屏左侧/上方）。
    本模块的一切坐标都按这个矩形解释，与 ``capture_screen`` 用的是同一套 ——
    否则"看到的位置"与"点到的位置"会整整差一块屏。
    """
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    return (
        _user32.GetSystemMetrics(_SM_XVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_YVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN),
    )


def _absolute(x: int, y: int) -> tuple[int, int]:
    """把屏幕像素坐标换算成 SendInput 绝对模式的 ``0..65535`` 归一化坐标。

    ⚠️ **这是最容易点偏的一处**：SendInput 的绝对坐标不是像素，而是相对虚拟
    桌面矩形的 1/65535。少这一步，在 1080p 单屏上也许只是"偏一点点"，
    在多屏 + 高 DPI 上会直接点到另一块屏去，而且**不报任何错**。
    """
    left, top, width, height = virtual_screen()
    if width <= 0 or height <= 0:
        raise WindowsApiError("读不到屏幕尺寸，无法换算坐标。")
    if not (left <= x < left + width and top <= y < top + height):
        # 越界时**如实报错**而不是悄悄夹到边缘：夹过去等于点了另一个地方，
        # 而模型会以为它点的是自己说的那个坐标。
        raise WindowsApiError(
            f"坐标 ({x}, {y}) 不在屏幕范围内。",
            detail=(
                f"当前虚拟桌面：x {left}..{left + width - 1}、"
                f"y {top}..{top + height - 1}"
            ),
        )
    nx = round((x - left) * 65535 / max(1, width - 1))
    ny = round((y - top) * 65535 / max(1, height - 1))
    return max(0, min(int(nx), 65535)), max(0, min(int(ny), 65535))


def _move_flags() -> int:
    return _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK


#: 按键名 → 鼠标键标志
_MOUSE_BUTTONS: dict[str, tuple[int, int]] = {
    "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
    "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
    "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
}


def _require_button(button: str) -> tuple[int, int]:
    pair = _MOUSE_BUTTONS.get(button)
    if pair is None:
        raise WindowsApiError(
            f"不支持的鼠标键：{button}",
            detail="可用：left / right / middle",
        )
    return pair


def mouse_move(x: int, y: int) -> None:
    """把鼠标移到屏幕像素坐标 ``(x, y)``。"""
    nx, ny = _absolute(int(x), int(y))
    _send([_mouse_input(_move_flags(), nx, ny)])


def mouse_click(x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
    """在 ``(x, y)`` 单击 / 双击 / 连点。

    移动与点击放在**同一批**里发：先单独移动再点击的话，中间若被别的程序
    （或用户自己的手）挪走光标，点到的就不是模型说的那个位置了。
    """
    down, up = _require_button(button)
    count = max(1, min(int(clicks), 3))
    nx, ny = _absolute(int(x), int(y))
    batch = [_mouse_input(_move_flags(), nx, ny)]
    for _ in range(count):
        batch.append(_mouse_input(down, nx, ny))
        batch.append(_mouse_input(up, nx, ny))
    _send(batch)


def mouse_scroll(amount: int) -> None:
    """滚轮：正数向上、负数向下（一格 = 120）。"""
    value = int(amount)
    if value == 0:
        return
    if abs(value) > 20:
        raise WindowsApiError("一次最多滚动 20 格。")
    _send([_mouse_input(_MOUSEEVENTF_WHEEL, 0, 0, value * _WHEEL_DELTA)])


async def mouse_drag(
    x1: int, y1: int, x2: int, y2: int, *, button: str = "left", steps: int = 12
) -> None:
    """从 ``(x1, y1)`` 拖到 ``(x2, y2)``。

    ⚠️ **必须在一次调用里完成"按下 → 移动 → 松开"**：中途失败或被取消还留着
    按下的鼠标键，用户的电脑会进入"一直在拖东西"的状态 —— 那比操作失败本身
    糟得多（所以下面用 ``try/finally`` 保证松开）。

    ⚠️ 每步之间 ``await asyncio.sleep`` 不是装饰：SendInput 是同步调用，
    不让出事件循环的话，"急停"就永远按不下去（取消只能在 await 点生效）。
    """
    down, up = _require_button(button)
    count = max(2, min(int(steps), 40))
    nx1, ny1 = _absolute(int(x1), int(y1))
    nx2, ny2 = _absolute(int(x2), int(y2))
    flags = _move_flags()
    _send([_mouse_input(flags, nx1, ny1)])
    await asyncio.sleep(0.02)
    _send([_mouse_input(down, nx1, ny1)])
    try:
        for step in range(1, count + 1):
            nx = round(nx1 + (nx2 - nx1) * step / count)
            ny = round(ny1 + (ny2 - ny1) * step / count)
            _send([_mouse_input(flags, nx, ny)])
            await asyncio.sleep(0.01)
    finally:
        _send([_mouse_input(up, nx2, ny2)])


#: 按键名 → 虚拟键码。只收"听得懂"的常见键；认不出来就报错，
#: 而不是猜一个键发出去（猜错等于在用户机器上乱按）。
_VK_NAMES: dict[str, int] = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "capslock": 0x14,
    "printscreen": 0x2C,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "cmd": 0x5B,
}
for _index in range(1, 13):
    _VK_NAMES[f"f{_index}"] = 0x6F + _index  # F1 = 0x70


def _vk_for(key: str) -> int:
    name = key.strip().lower()
    if not name:
        raise WindowsApiError("按键名不能为空。")
    if name in _VK_NAMES:
        return _VK_NAMES[name]
    if len(name) == 1 and ("a" <= name <= "z" or "0" <= name <= "9"):
        return ord(name.upper())
    raise WindowsApiError(
        f"认不出这个按键：{key}",
        detail=(
            "可用：字母数字、enter / tab / esc / space / backspace / delete / "
            "方向键 / home / end / pageup / pagedown / f1-f12 / ctrl / alt / shift / win"
        ),
    )


def press_keys(keys: list[str]) -> None:
    """按下并松开一组键（组合键），例如 ``["ctrl", "s"]``。"""
    if not keys:
        raise WindowsApiError("至少要给一个按键。")
    if len(keys) > 4:
        raise WindowsApiError("一次最多按 4 个键。")
    codes = [_vk_for(item) for item in keys]
    batch = [_key_input(vk=code) for code in codes]
    # 松开顺序与按下相反：先松修饰键再松主键，与真人按键的时序一致
    for code in reversed(codes):
        batch.append(_key_input(vk=code, flags=_KEYEVENTF_KEYUP))
    _send(batch)


async def type_text(text: str) -> None:
    """输入一段文字（中文、emoji 都能进，不受输入法与键盘布局影响）。

    ⚠️ 走 ``KEYEVENTF_UNICODE`` 而不是虚拟键码：中文、以及任何非美式键盘布局
    上的符号都不在虚拟键码表里，按 VK 只能打出一串错字。
    ⚠️ 按 **UTF-16 码元**逐字发送（而不是按 Python 字符）—— 这样 emoji 这类
    代理对字符也能正确输入。
    ⚠️ **绝不把输入的内容写进日志**（可能是密码或私密文字）。
    """
    if not text:
        return
    units = text.encode("utf-16-le")
    batch: list[_INPUT] = []
    for index in range(0, len(units), 2):
        code = units[index] | (units[index + 1] << 8)
        batch.append(_key_input(scan=code, flags=_KEYEVENTF_UNICODE))
        batch.append(
            _key_input(scan=code, flags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP)
        )
    for start in range(0, len(batch), _INPUT_BATCH):
        _send(batch[start : start + _INPUT_BATCH])
        await asyncio.sleep(0)


def release_all_inputs() -> None:
    """尽最大努力松开所有鼠标键与修饰键。

    它是**兜底**：正常流程里不该有东西保持按下。但在异常、取消、或上一次调用
    中途崩掉之后，用户可能正处在"鼠标一直按着 / 某个修饰键卡住"的状态里 ——
    那时这一个调用是他唯一能自救的东西。所以它**不抛错**：
    再抛一个异常只会掩盖真正的问题。
    """
    if not is_supported():
        return
    try:
        batch = [
            _mouse_input(_MOUSEEVENTF_LEFTUP),
            _mouse_input(_MOUSEEVENTF_RIGHTUP),
            _mouse_input(_MOUSEEVENTF_MIDDLEUP),
        ]
        for vk in (0x10, 0x11, 0x12, 0x5B):  # shift / ctrl / alt / win
            batch.append(_key_input(vk=vk, flags=_KEYEVENTF_KEYUP))
        _send(batch)
    except Exception:  # noqa: BLE001 - 兜底函数不该再抛
        logger.debug("释放按键状态失败（忽略）", exc_info=True)


# --------------------------------------------------------------------------- #
# 窗口
# --------------------------------------------------------------------------- #
def _window_title(handle: int) -> str:
    assert _user32 is not None
    length = _user32.GetWindowTextLengthW(handle)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(handle, buffer, length + 1)
    return buffer.value


def list_windows() -> list[dict[str, Any]]:
    """列出当前**可见且有标题**的顶层窗口。

    只保留有标题的：无标题窗口是输入法候选框、托盘图标宿主这类东西，
    对"切到某个程序"没有任何用处，还会让列表长到模型读不完。
    """
    if not is_supported() or _WNDCALLBACK is None:
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None

    foreground = _user32.GetForegroundWindow()
    found: list[dict[str, Any]] = []

    def _callback(handle: Any, _lparam: Any) -> bool:
        # ⚠️ 回调里**绝不能抛异常**：异常会穿透进 ctypes 的调用栈，
        # 轻则整个枚举中断，重则让进程崩掉。所以这里逐个 try。
        try:
            if not _user32.IsWindowVisible(handle):
                return True
            title = _window_title(handle)
            if not title:
                return True
            rect = _RECT()
            if not _user32.GetWindowRect(handle, ctypes.byref(rect)):
                return True
            found.append(
                {
                    "handle": int(handle),
                    "title": title,
                    "foreground": bool(handle == foreground),
                    "left": rect.left,
                    "top": rect.top,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
            )
        except Exception:  # noqa: BLE001 - 见上面的说明
            logger.debug("枚举窗口时跳过了一项", exc_info=True)
        return True

    callback = _WNDCALLBACK(_callback)
    _user32.EnumWindows(callback, None)
    return found


def activate_window(handle: int) -> bool:
    """把窗口切到前台，返回是否**真的**切过去了。

    ⚠️ Windows 有"前台锁"：调用者不是前台进程时，``SetForegroundWindow``
    **可能被系统直接拒绝**（返回 0）。这时如实返回 False，让上层告诉用户
    "系统不允许自动切换，请手动点一下那个窗口" —— 假装成功会让模型以为
    切过去了，接着把键鼠操作发给一个其实还在后台的窗口。
    """
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    value = int(handle)
    if _user32.IsIconic(value):
        _user32.ShowWindow(value, _SW_RESTORE)
    return bool(_user32.SetForegroundWindow(value))


def foreground_window_handle() -> int:
    """当前前台窗口的句柄（0 表示取不到）。"""
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    return int(_user32.GetForegroundWindow() or 0)


# --------------------------------------------------------------------------- #
# 屏幕元素（UI Automation）
# --------------------------------------------------------------------------- #
# 为什么走 PowerShell + .NET 的 UI Automation，而不是 Python 里直接调 COM：
#   ``IUIAutomation`` 这套 COM 接口用 ctypes 手写 vtable 极其冗长且版本敏感，
#   而 .NET 的 ``System.Windows.Automation`` **是系统自带的**（Windows PowerShell
#   5.1 就能 Add-Type），完全符合本模块"只用标准库 + 系统自带命令"的约定。
#
# 为什么遍历放在子进程里：整棵 UI 树可能有几千个节点，在主进程里同步遍历会把
# 事件循环卡死（界面直接不响应）；子进程还顺带隔离了 COM 侧的崩溃。
def _ui_script(max_items: int, max_depth: int, handle: int) -> str:
    target = (
        "[System.Windows.Automation.AutomationElement]::FromHandle("
        f"[IntPtr]::new({handle}))"
        if handle
        else "[System.Windows.Automation.AutomationElement]::RootElement"
    )
    return "\n".join(
        [
            "Add-Type -AssemblyName UIAutomationClient",
            "Add-Type -AssemblyName UIAutomationTypes",
            f"$root = {target}",
            "if ($root -eq $null) { exit 0 }",
            "$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker",
            "$script:count = 0",
            "function Walk($el, $depth) {",
            f"  if ($script:count -ge {max_items}) {{ return }}",
            f"  if ($depth -gt {max_depth}) {{ return }}",
            "  try { $child = $walker.GetFirstChild($el) } catch { return }",
            "  while ($child -ne $null) {",
            f"    if ($script:count -ge {max_items}) {{ return }}",
            "    try {",
            "      $c = $child.Current",
            "      $r = $c.BoundingRectangle",
            # 名称里混进制表符/换行会把"一行一个元素"的格式冲掉，先换成空格
            "      $n = ($c.Name -replace \"[`t`r`n]\", ' ')",
            "      $t = $c.ControlType.ProgrammaticName -replace 'ControlType\\.', ''",
            "      Write-Output \"$depth`t$n`t$t`t$([int]$r.X)`t$([int]$r.Y)`t$([int]$r.Width)`t$([int]$r.Height)`t$($c.IsEnabled)`t$($c.IsKeyboardFocusable)\"",
            "      $script:count++",
            "    } catch { }",
            "    Walk $child ($depth + 1)",
            "    try { $child = $walker.GetNextSibling($child) } catch { $child = $null }",
            "  }",
            "}",
            "Walk $root 0",
        ]
    )


def _parse_ui_lines(output: str) -> list[dict[str, Any]]:
    """把子进程吐出的一行一个元素解析成字典列表。

    只保留**有名字或可聚焦**的节点：UI 树里绝大多数节点是无名的布局容器，
    全带回去会把真正能点的东西淹掉（而且模型读不完）。
    """
    result: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 9:
            continue
        depth, name, kind, x, y, width, height, enabled, focusable = parts
        try:
            item = {
                "depth": int(depth),
                "name": name.strip(),
                "type": kind.strip(),
                "left": int(x),
                "top": int(y),
                "width": int(width),
                "height": int(height),
                "enabled": enabled.strip().lower() == "true",
                "focusable": focusable.strip().lower() == "true",
            }
        except ValueError:
            continue
        if not item["name"] and not item["focusable"]:
            continue
        result.append(item)
    return result


async def read_ui_elements(
    *, window_handle: int = 0, max_items: int = 60, max_depth: int = 10
) -> list[dict[str, Any]]:
    """读出界面上有哪些元素（名称 / 类型 / 位置 / 是否可用）。

    默认读**当前前台窗口**；给它 ``window_handle`` 就读指定窗口（句柄来自
    ``list_windows``）。返回的 ``left/top`` 是屏幕像素坐标，可以直接交给
    ``mouse_click`` —— 这两者必须是同一套坐标，否则"看到的位置"和"点到的
    位置"会差一整块屏。
    """
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    items = max(1, min(int(max_items), 200))
    depth = max(1, min(int(max_depth), 15))
    handle = int(window_handle) or foreground_window_handle()
    script = _ui_script(items, depth, handle)
    output = await run_powershell(script, timeout=40.0)
    return _parse_ui_lines(output)


# --------------------------------------------------------------------------- #
# 启动程序 / 打开文件或网址
# --------------------------------------------------------------------------- #
def launch(target: str) -> None:
    """启动程序，或用系统默认关联打开一个文件 / 网址。

    ``os.startfile`` 是**标准库**（只有 Windows 有），走的是系统 shell 关联 ——
    不需要我们维护"exe 路径 ↔ 程序名"的映射表。
    """
    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    value = target.strip()
    if not value:
        raise WindowsApiError("要打开的对象不能为空。")
    try:
        os.startfile(value)  # type: ignore[attr-defined]  # 仅 Windows 存在
    except OSError as exc:
        raise WindowsApiError("打不开这个对象。", detail=str(exc)) from exc


def describe() -> dict[str, Any]:
    """给诊断用：当前环境具备哪些能力（不触发任何实际操作）。"""
    return {"platform": sys.platform, "windows_api": is_supported()}
