"""MCP 子进程树的回收（Windows 专用）。

## 问题

``npx`` 在 Windows 上是个 ``.cmd`` 包装：它启动 ``node``，``node`` 再去跑真正的
MCP Server。MCP SDK 的 ``stdio_client`` 关掉的是它**直接创建的那个进程**，
于是 ``npx.cmd`` 被终止后，它派生出来的 ``node`` 可能继续活着。

后果不是"多占一点内存"：这些孤儿进程还占着端口、文件句柄和数据库连接，
下次用户重连同一个 Server 时会撞上"端口被占用"或者"文件被锁"，
而进程列表里那东西的名字跟我们的应用看起来毫无关系。

## 怎么定位"哪些进程是我们的"

没有可靠的办法从 SDK 拿到子进程的 PID（``stdio_client`` 只产出读写流）。
所以走一条朴素的路径：**在我们进程的直接子进程里取差集** ——
建连前后各拍一次快照，新出现的那些就是这次启动的 Server 树根。

这个判断有前提：同一时刻不能有别的组件也在 fork。所有 MCP 建连都经过
``McpManager`` 的锁，所以实际上成立。即便偶有误判，``taskkill`` 的是
"刚刚由我们自己创建的子进程"，最坏情况也只是提前结束一个本来就要结束的进程，
不会波及用户自己的程序 —— 这一点是刻意的，绝不去按进程名（如 ``node``）
模糊匹配，那才是真会误杀。

## 只在 Windows 生效

POSIX 上父进程退出后子进程会被 init 收养，但 MCP SDK 用的是进程组信号，
实际不会留下孤儿；而 ``taskkill`` 是 Windows 专有命令，在别处调用只会报错。
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"


def _list_child_pids(parent_pid: int) -> set[int]:
    """列出某个进程的直接子进程 PID（仅 Windows）。

    用 ``wmic`` 是无奈之选：它在新版 Windows 上已被标记为弃用，
    但 ``Get-CimInstance`` 要起 PowerShell（冷启动几百毫秒，而这里在启动路径上），
    而 psutil 会引入一个新的打包依赖（体积 + 若干 MB）。
    拿不到就返回空集，退化成"没有可回收的进程"，不影响主流程。
    """
    if not IS_WINDOWS:
        return set()
    try:
        completed = subprocess.run(
            ["wmic", "process", "where", f"ParentProcessId={parent_pid}", "get", "ProcessId"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return set()

    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def snapshot_children() -> set[int]:
    """当前进程的直接子进程快照。

    ⚠️ **阻塞调用**：内部会起 ``wmic`` / PowerShell 子进程（上限 10 秒）。
    在协程里请用 ``await asyncio.to_thread(procs.snapshot_children)`` ——
    直接调用会把事件循环占住，所有正在流式输出的会话一起"假死"。
    """
    return _list_child_pids(os.getpid())


def adopt_new_children(before: set[int]) -> set[int]:
    """把"建连过程中新出现的子进程"认作本次启动的进程树根。"""
    return snapshot_children() - before


def kill_tree(pids: set[int], *, reason: str = "") -> int:
    """强制结束进程树（含后代），返回实际尝试的根进程数量。

    ``/T`` 是关键：只 ``/F`` 杀掉根进程的话，孙进程照样活着 ——
    而那正是要用这个函数的原因。
    """
    if not IS_WINDOWS or not pids:
        return 0

    killed = 0
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            killed += 1
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            logger.debug("回收 MCP 进程树失败 pid=%s: %s", pid, exc)

    if killed:
        logger.info("已强制回收 MCP 进程树 %s 个%s", killed, f"（{reason}）" if reason else "")
    return killed
