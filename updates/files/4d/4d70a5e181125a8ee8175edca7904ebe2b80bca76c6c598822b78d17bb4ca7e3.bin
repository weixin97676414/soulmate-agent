# -*- coding: utf-8 -*-
"""运行前环境自检与自动引导。

任何主脚本（`xhs_crawl.py` / `xhs_login.py` / `xhs_analyze.py` / `xhs_report.py`）
在开工前先调一次 `ensure_ready()`：

    环境已就绪 → 直接返回，零开销；
    环境缺失   → 自动跑 `setup.py` 补齐（pip 依赖 + Chromium），
                 必要时切到托管虚拟环境的解释器重新执行当前命令。

由此实现「安装技能 = 环境就绪」：用户不需要手工敲任何安装命令。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from xhs_common import log

#: 自动引导标记：子进程继承此变量，避免「装完又回来检查」的死循环
_GUARD = "XHS_ENV_BOOTSTRAPPED"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SETUP = _SCRIPTS_DIR / "setup.py"

#: 最小可用集：playwright（浏览器通道）、curl_cffi（HTTP 通道）、PIL（关键帧拼版）
REQUIRED = ["playwright", "curl_cffi", "PIL"]

MANAGED_VENV = Path.home() / ".skill-runtime" / "binaries" / "python" / "envs" / "default"


def venv_python() -> Path | None:
    exe = MANAGED_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return exe if exe.exists() else None


def importable(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def missing_mods() -> list[str]:
    return [m for m in REQUIRED if not importable(m)]


def browser_ready() -> bool:
    try:
        from bootstrap import check_browser
        return bool(check_browser().get("ok"))
    except Exception:  # noqa: BLE001
        return False


def _venv_has_deps(venv: Path) -> bool:
    code = "import " + ", ".join(REQUIRED)
    try:
        return subprocess.run([str(venv), "-c", code], capture_output=True,
                              timeout=120).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _rerun_in(interpreter: Path) -> None:
    """用指定解释器重新执行当前命令（保持参数不变）。"""
    script = str(Path(sys.argv[0]).resolve())
    cmd = [str(interpreter), script, *sys.argv[1:]]
    log.info("切换到已配置好的解释器重新执行：%s", interpreter)
    raise SystemExit(subprocess.call(cmd))


def _maybe_switch() -> None:
    """依赖装在托管 venv、当前却是别的解释器 → 切换过去，避免"明明装了却 import 不到"。"""
    venv = venv_python()
    if not venv or not missing_mods():
        return
    try:
        same = Path(sys.executable).resolve() == venv.resolve()
    except Exception:  # noqa: BLE001
        same = False
    if not same and _venv_has_deps(venv):
        _rerun_in(venv)


def ensure_ready(need_browser: bool = True, auto_install: bool = True) -> None:
    """确保依赖与（可选的）浏览器内核就绪。

    need_browser=False 用于纯分析 / 渲染脚本 —— 不该为了跑 `xhs_analyze.py`
    去下载 430MB 的 Chromium。
    """
    if os.environ.get(_GUARD) == "1":
        return
    os.environ[_GUARD] = "1"

    gaps = missing_mods()
    need_setup = bool(gaps) or (need_browser and not browser_ready())

    if need_setup:
        if not auto_install:
            raise SystemExit(
                "运行环境未就绪，缺失：" + "、".join(gaps or ["chromium"]) +
                f"\n请执行：{sys.executable} {_SETUP}"
            )
        reason = "缺少依赖 " + "、".join(gaps) if gaps else "缺少 Chromium 内核"
        log.info("首次运行，正在自动配置环境（%s）…", reason)
        cmd = [sys.executable, str(_SETUP)]
        if not need_browser:
            cmd.append("--no-browser")
        code = subprocess.call(cmd)
        if code != 0:
            log.warning("自动配置返回码 %s，继续尝试（可能是可选组件失败）", code)
        # 关键：依赖很可能被装进了托管 venv，而当前解释器看不到 —— 先切换再复查，
        # 否则会误报「自动配置未完成」。
        _maybe_switch()
        gaps = missing_mods()
        if gaps:
            raise SystemExit(
                "环境自动配置未完成，仍缺失：" + "、".join(gaps) +
                f"\n请手动执行：{sys.executable} {_SETUP}"
            )
        if need_browser and not browser_ready():
            raise SystemExit(
                "Chromium 内核仍未就绪。请手动执行："
                f"{sys.executable} {_SETUP}\n"
                "（内核约 430MB，慢网下可能超时，重跑会断点续传）"
            )
        return

    _maybe_switch()
