#!/usr/bin/env python3
"""启动抖音桌面版（静默，不弹出命令行窗口）"""
import subprocess, os

DOUYIN_PATH = r"C:\Program Files (x86)\ByteDance\douyin\douyin.exe"
STARTUPINFO = subprocess.STARTUPINFO()
STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
STARTUPINFO.wShowWindow = 0  # SW_HIDE

if os.path.exists(DOUYIN_PATH):
    subprocess.Popen([DOUYIN_PATH], startupinfo=STARTUPINFO)
    print("抖音已启动")
else:
    print(f"未找到抖音: {DOUYIN_PATH}")
