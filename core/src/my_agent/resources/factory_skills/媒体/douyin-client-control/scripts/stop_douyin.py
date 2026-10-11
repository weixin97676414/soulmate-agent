#!/usr/bin/env python3
"""强制关闭抖音桌面版及所有相关后台进程"""
import subprocess

PROCESSES = [
    "douyin.exe",
    "douyin.Update.exe",
    "DouyinPluginHost.exe",
    "DouyinWebHelper.exe",
    "Douyin.Tray.exe",
    "douyin_tray.exe",
]

STARTUPINFO = subprocess.STARTUPINFO()
STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
STARTUPINFO.wShowWindow = 0  # SW_HIDE

for proc in PROCESSES:
    subprocess.run(
        ["taskkill", "/f", "/im", proc],
        startupinfo=STARTUPINFO,
        capture_output=True,
    )

print("抖音已关闭")
