




















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


WINDOWS_ONLY_HINT = "该功能依赖 Windows 系统能力，当前系统不支持。"

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_GMEM_ZEROINIT = 0x0040




_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF

_KEYEVENTF_KEYUP = 0x0002


class WindowsApiError(Exception):


    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


def is_supported() -> bool:

    return sys.platform == "win32"


if is_supported():  
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    
    
    
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
else:  
    _user32 = None
    _kernel32 = None





async def run_powershell(script: str, *, timeout: float = 20.0) -> str:





    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)

    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        
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
        
        
        
        with contextlib.suppress(Exception):
            await asyncio.wait_for(process.wait(), timeout=5.0)
        raise WindowsApiError(f"系统命令执行超时（{timeout:.0f} 秒）") from None

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise WindowsApiError("系统命令执行失败", detail=text[-500:] or f"退出码{process.returncode}")
    return text


def _ps_quote(value: str) -> str:





    return "'" + value.replace("'", "''") + "'"





def _open_clipboard(retries: int = 5) -> None:






    assert _user32 is not None
    import time

    for attempt in range(retries):
        if _user32.OpenClipboard(None):
            return
        time.sleep(0.05 * (attempt + 1))
    raise WindowsApiError("剪贴板被其它程序占用，稍后再试。")


def read_clipboard_text() -> str:

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
        
        
    finally:
        _user32.CloseClipboard()


async def save_clipboard_image(target: Path) -> bool:

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

    if not source.exists():
        raise WindowsApiError(f"图片不存在：{source}")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        f"$img = [System.Drawing.Image]::FromFile({_ps_quote(str(source))});"
        
        "$copy = New-Object System.Drawing.Bitmap($img);"
        "[Windows.Forms.Clipboard]::SetImage($copy);"
        "$copy.Dispose(); $img.Dispose();"
        "Write-Output 'OK'"
    )
    await run_powershell(script)





def _tap_media_key(key_code: int, times: int = 1) -> None:

    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    for _ in range(max(1, min(times, 50))):
        _user32.keybd_event(key_code, 0, 0, 0)
        _user32.keybd_event(key_code, 0, _KEYEVENTF_KEYUP, 0)


def volume_step(action: str, *, times: int = 2) -> None:






    if action == "up":
        _tap_media_key(_VK_VOLUME_UP, times)
    elif action == "down":
        _tap_media_key(_VK_VOLUME_DOWN, times)
    else:
        raise WindowsApiError(f"不支持的音量操作：{action}")















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


_VOLUME_STATE_COMMAND = "Write-Output ([Audio]::GetState())"


def _parse_volume_state(output: str) -> tuple[int, bool] | None:




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

    output = await run_powershell(_VOLUME_INTEROP + script, timeout=30.0)
    state = _parse_volume_state(output)
    if state is None:
        
        raise WindowsApiError(f"{action}后读回的音量状态无法解析。", detail=output[-200:])
    return state


async def get_volume_state() -> tuple[int, bool]:

    return await _run_volume_script(_VOLUME_STATE_COMMAND, "读取音量")


async def set_volume_percent(percent: int, *, unmute: bool = True) -> tuple[int, bool]:










    value = max(0, min(int(percent), 100))
    script = f"[Audio]::SetVolume({value / 100}, {1 if unmute else 0});" + _VOLUME_STATE_COMMAND
    return await _run_volume_script(script, "设置音量")


async def set_muted(muted: bool) -> tuple[int, bool]:






    script = f"[Audio]::SetMute({1 if muted else 0});" + _VOLUME_STATE_COMMAND
    return await _run_volume_script(script, "设置静音")


async def get_brightness() -> int:

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





def lock_workstation() -> None:

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





    target.parent.mkdir(parents=True, exist_ok=True)
    if region is not None:
        x, y, width, height = (int(item) for item in region)
        if width <= 0 or height <= 0:
            raise WindowsApiError("截图区域的宽高必须大于 0。")
        bounds = f"$x = {x}; $y = {y}; $w = {width}; $h = {height}"
    else:
        
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


_KEYEVENTF_UNICODE = 0x0004


_WHEEL_DELTA = 120


_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_SW_RESTORE = 9



_INPUT_BATCH = 200







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


if is_supported():  
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
    assert _WNDCALLBACK is not None  
    _user32.EnumWindows.argtypes = [_WNDCALLBACK, ctypes.c_void_p]
    _user32.EnumWindows.restype = ctypes.c_bool


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> _INPUT:
    item = _INPUT()
    item.type = _INPUT_MOUSE
    item.union.mi = _MOUSEINPUT(
        dx=dx,
        dy=dy,
        
        
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






    left, top, width, height = virtual_screen()
    if width <= 0 or height <= 0:
        raise WindowsApiError("读不到屏幕尺寸，无法换算坐标。")
    if not (left <= x < left + width and top <= y < top + height):
        
        
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

    nx, ny = _absolute(int(x), int(y))
    _send([_mouse_input(_move_flags(), nx, ny)])


def mouse_click(x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:





    down, up = _require_button(button)
    count = max(1, min(int(clicks), 3))
    nx, ny = _absolute(int(x), int(y))
    batch = [_mouse_input(_move_flags(), nx, ny)]
    for _ in range(count):
        batch.append(_mouse_input(down, nx, ny))
        batch.append(_mouse_input(up, nx, ny))
    _send(batch)


def mouse_scroll(amount: int) -> None:

    value = int(amount)
    if value == 0:
        return
    if abs(value) > 20:
        raise WindowsApiError("一次最多滚动 20 格。")
    _send([_mouse_input(_MOUSEEVENTF_WHEEL, 0, 0, value * _WHEEL_DELTA)])


async def mouse_drag(
    x1: int, y1: int, x2: int, y2: int, *, button: str = "left", steps: int = 12
) -> None:









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
    _VK_NAMES[f"f{_index}"] = 0x6F + _index  


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

    if not keys:
        raise WindowsApiError("至少要给一个按键。")
    if len(keys) > 4:
        raise WindowsApiError("一次最多按 4 个键。")
    codes = [_vk_for(item) for item in keys]
    batch = [_key_input(vk=code) for code in codes]
    
    for code in reversed(codes):
        batch.append(_key_input(vk=code, flags=_KEYEVENTF_KEYUP))
    _send(batch)


async def type_text(text: str) -> None:








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







    if not is_supported():
        return
    try:
        batch = [
            _mouse_input(_MOUSEEVENTF_LEFTUP),
            _mouse_input(_MOUSEEVENTF_RIGHTUP),
            _mouse_input(_MOUSEEVENTF_MIDDLEUP),
        ]
        for vk in (0x10, 0x11, 0x12, 0x5B):  
            batch.append(_key_input(vk=vk, flags=_KEYEVENTF_KEYUP))
        _send(batch)
    except Exception:  
        logger.debug("释放按键状态失败（忽略）", exc_info=True)





def _window_title(handle: int) -> str:
    assert _user32 is not None
    length = _user32.GetWindowTextLengthW(handle)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(handle, buffer, length + 1)
    return buffer.value


def list_windows() -> list[dict[str, Any]]:





    if not is_supported() or _WNDCALLBACK is None:
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None

    foreground = _user32.GetForegroundWindow()
    found: list[dict[str, Any]] = []

    def _callback(handle: Any, _lparam: Any) -> bool:
        
        
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
        except Exception:  
            logger.debug("枚举窗口时跳过了一项", exc_info=True)
        return True

    callback = _WNDCALLBACK(_callback)
    _user32.EnumWindows(callback, None)
    return found


def activate_window(handle: int) -> bool:







    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    value = int(handle)
    if _user32.IsIconic(value):
        _user32.ShowWindow(value, _SW_RESTORE)
    return bool(_user32.SetForegroundWindow(value))


def foreground_window_handle() -> int:

    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    assert _user32 is not None
    return int(_user32.GetForegroundWindow() or 0)












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







    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    items = max(1, min(int(max_items), 200))
    depth = max(1, min(int(max_depth), 15))
    handle = int(window_handle) or foreground_window_handle()
    script = _ui_script(items, depth, handle)
    output = await run_powershell(script, timeout=40.0)
    return _parse_ui_lines(output)





def launch(target: str) -> None:





    if not is_supported():
        raise WindowsApiError(WINDOWS_ONLY_HINT)
    value = target.strip()
    if not value:
        raise WindowsApiError("要打开的对象不能为空。")
    try:
        os.startfile(value)  
    except OSError as exc:
        raise WindowsApiError("打不开这个对象。", detail=str(exc)) from exc


def describe() -> dict[str, Any]:

    return {"platform": sys.platform, "windows_api": is_supported()}
