





























from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"


def _list_child_pids(parent_pid: int) -> set[int]:







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






    return _list_child_pids(os.getpid())


def adopt_new_children(before: set[int]) -> set[int]:

    return snapshot_children() - before


def kill_tree(pids: set[int], *, reason: str = "") -> int:





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
        except (OSError, subprocess.SubprocessError) as exc:  
            logger.debug("回收 MCP 进程树失败 pid=%s: %s", pid, exc)

    if killed:
        logger.info("已强制回收 MCP 进程树 %s 个%s", killed, f"（{reason}）" if reason else "")
    return killed
