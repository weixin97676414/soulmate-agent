---
name: douyin-client-control
description: 抖音桌面客户端启动与关闭控制（Windows）。通过 Python 脚本静默启动或强制关闭抖音桌面客户端及其后台进程。触发词：打开抖音、启动抖音、关闭抖音、退出抖音、开抖音、关抖音。
author: Soulmate Agent团队成员：岸
---

# 抖音客户端 — 启动与关闭

## 概述

通过 Python 脚本控制抖音桌面版客户端的启动和关闭，所有操作静默执行（不弹出命令行窗口）。

## 使用方法

### 启动抖音

```powershell
python scripts/start_douyin.py
```

静默启动抖音，不弹出命令行窗口。

### 关闭抖音

```powershell
python scripts/stop_douyin.py
```

强制关闭抖音主程序及所有相关后台进程：

- douyin.exe（主程序）
- douyin.Update.exe（更新服务）
- DouyinPluginHost.exe（插件宿主）
- DouyinWebHelper.exe（Web 助手）
- Douyin.Tray.exe / douyin_tray.exe（托盘图标）

## 抖音安装路径

`C:\Program Files (x86)\ByteDance\douyin\douyin.exe`

## 注意事项

- 脚本使用 `subprocess.STARTUPINFO` 隐藏窗口，不会弹出命令行
- 关闭使用 `taskkill /f` 强制终止，确保所有相关进程被清理
- 仅适用于 Windows；启动脚本会检查安装路径是否存在，未找到会提示

