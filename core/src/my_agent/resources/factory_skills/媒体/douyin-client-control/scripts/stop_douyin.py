#!/usr/bin/env python3

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
STARTUPINFO.wShowWindow = 0  

for proc in PROCESSES:
    subprocess.run(
        ["taskkill", "/f", "/im", proc],
        startupinfo=STARTUPINFO,
        capture_output=True,
    )

print("抖音已关闭")
