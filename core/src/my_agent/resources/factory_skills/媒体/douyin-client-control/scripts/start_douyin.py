#!/usr/bin/env python3

import subprocess, os

DOUYIN_PATH = r"C:\Program Files (x86)\ByteDance\douyin\douyin.exe"
STARTUPINFO = subprocess.STARTUPINFO()
STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
STARTUPINFO.wShowWindow = 0  

if os.path.exists(DOUYIN_PATH):
    subprocess.Popen([DOUYIN_PATH], startupinfo=STARTUPINFO)
    print("抖音已启动")
else:
    print(f"未找到抖音: {DOUYIN_PATH}")
