# -*- coding: utf-8 -*-
"""环境自检与依赖安装。

用法：
    python bootstrap.py              # 检查环境
    python bootstrap.py --install    # 检查并自动安装缺失依赖（playwright / curl_cffi / ffmpeg 提示）

Windows 下会复用 宿主托管 Python，不会污染用户全局环境。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from xhs_common import SKILL_DIR, get_logger, log

PIP_PACKAGES = [
    ("playwright", "playwright>=1.47"),
    ("curl_cffi", "curl_cffi>=0.7"),
    ("PIL", "pillow>=10.0"),          # 关键帧拼版
]

# 宿主托管 venv：所有依赖只装在这里，不污染用户全局 Python
MANAGED_VENV = (Path.home() / ".skill-runtime" / "binaries" / "python" / "envs" / "default")

#: Chromium 下载源。官方 CDN 在国内实测只有 ~1MB/分钟（170MB 要下两个多小时），
#: 改用 npmmirror 的二进制镜像通常几分钟完成。可用环境变量覆盖回官方源：
#:   PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net
DEFAULT_DOWNLOAD_HOST = "https://cdn.npmmirror.com/binaries/playwright"


def browser_env(host: str = "") -> dict:
    """构造带下载源的子进程环境（用户已设置时不覆盖）。"""
    env = os.environ.copy()
    env.setdefault("PLAYWRIGHT_DOWNLOAD_HOST", host or DEFAULT_DOWNLOAD_HOST)
    return env


def ensure_venv() -> None:
    """不在 venv 里时，切到托管 venv 重新执行本脚本（避免污染全局 Python）。

    注意：必须重跑 **调用方的脚本**（`sys.argv[0]`），不能用 `__file__`
    —— 本函数定义在 bootstrap.py 里，`setup.py` 也会调用它，用 `__file__`
    会把 setup.py 重启成 bootstrap.py，参数解析直接失败。
    """
    if "--in-venv" in sys.argv or sys.prefix != sys.base_prefix:
        return
    if os.name != "nt":
        return
    base = Path(sys.base_prefix)
    if "binaries" not in str(base).replace("\\", "/").lower():
        return  # 用户自己的 Python，尊重其选择，直接装

    venv_py = MANAGED_VENV / "Scripts" / "python.exe"
    if not venv_py.exists():
        log.info("创建托管虚拟环境：%s", MANAGED_VENV)
        proc = subprocess.run([sys.executable, "-m", "venv", str(MANAGED_VENV)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not venv_py.exists():
            log.warning("venv 创建失败，回退当前解释器：%s", proc.stderr[-200:])
            return
    entry = str(Path(sys.argv[0]).resolve())
    log.info("切换到托管虚拟环境：%s", venv_py)
    raise SystemExit(subprocess.call([str(venv_py), entry,
                                      *(a for a in sys.argv[1:] if a != "--in-venv"),
                                      "--in-venv"]))


def _run(cmd: list[str], timeout: int = 900, env: dict | None = None) -> subprocess.CompletedProcess:
    """执行命令。超时不抛异常，转成失败结果返回，避免整个安装流程崩掉。

    注意：chromium 内核约 430MB，慢网下 `playwright install` 很容易超过 15 分钟，
    子进程可能已下载完毕但管道未关闭而触发超时——因此超时后要按「可能已成功」处理，
    由 check_browser() 做最终判定，而不是直接判失败。
    """
    log.info("执行：%s", " ".join(cmd))
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=env,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as err:
        log.warning("命令超时（%ss）：%s", timeout, " ".join(cmd))
        return subprocess.CompletedProcess(cmd, returncode=124,
                                           stdout=(err.stdout or b"").decode("utf-8", "replace")
                                           if isinstance(err.stdout, bytes) else (err.stdout or ""),
                                           stderr=f"TIMEOUT after {timeout}s")
    except Exception as err:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(err))


def check_python() -> dict:
    return {"ok": True, "version": sys.version.split()[0], "path": sys.executable}


def check_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def check_ffmpeg() -> dict:
    """系统 ffmpeg 优先；没有则退而求其次用 playwright 随 chromium 下载的那一份。"""
    try:
        from xhs_media import find_ffmpeg
        exe = find_ffmpeg()
    except Exception:  # noqa: BLE001
        exe = shutil.which("ffmpeg") or ""
    return {"ok": bool(exe), "path": exe,
            "bundled": bool(exe) and "ms-playwright" in exe.replace("\\", "/")}


def check_state() -> dict:
    from xhs_common import COOKIE_FILE, STATE_FILE
    state_ok = STATE_FILE.exists()
    cookies = []
    if COOKIE_FILE.exists():
        try:
            cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cookies = []
    names = {c.get("name") for c in cookies if isinstance(c, dict)}
    # 只认 web_session：a1 / webId / acw_tc 是访客 cookie，打开页面就会下发
    login_ok = "web_session" in names
    return {"state_file": state_ok, "login_saved": login_ok,
            "cookie_names": sorted(n for n in names if n)}


def check_browser() -> dict:
    """检查 playwright chromium 内核是否就绪（直接查缓存目录，不启动驱动，避免退出噪音）。"""
    if not check_import("playwright"):
        return {"ok": False, "reason": "playwright 未安装"}
    roots = [
        Path.home() / "AppData" / "Local" / "ms-playwright",          # Windows
        Path.home() / ".cache" / "ms-playwright",                      # Linux
        Path.home() / "Library" / "Caches" / "ms-playwright",          # macOS
    ]
    pattern = "chrome*.exe" if platform.system() == "Windows" else "chrome"
    for root in roots:
        if not root.exists():
            continue
        for folder in sorted(root.glob("chromium*"), reverse=True):
            if not (folder / "INSTALLATION_COMPLETE").exists():
                continue
            for hit in folder.rglob(pattern):
                if hit.is_file() and hit.parent.name in ("chrome-win", "chrome-win64", "chrome-linux"):
                    return {"ok": True, "path": str(hit)}
            for hit in folder.rglob("headless_shell*"):
                if hit.is_file():
                    return {"ok": True, "path": str(hit)}
    return {"ok": False, "reason": "chromium 未下载，执行 bootstrap.py --install"}


def install(logger, with_browser: bool = True, download_host: str = "") -> dict:
    """安装缺失依赖。`with_browser=False` 时跳过 chromium 下载

    （纯分析/渲染脚本不需要浏览器，不该为了跑 `xhs_analyze.py` 下载 430MB 内核）。
    """
    results = {}
    for mod, spec in PIP_PACKAGES:
        if check_import(mod):
            results[mod] = "already"
            continue
        proc = _run([sys.executable, "-m", "pip", "install", "-U", spec], timeout=600)
        results[mod] = "installed" if proc.returncode == 0 else f"failed: {proc.stderr[-300:]}"

    if not with_browser:
        results["chromium"] = "skipped（--no-browser）"
        return results

    if check_import("playwright"):
        if check_browser().get("ok"):
            results["chromium"] = "already"
        else:
            env = browser_env(download_host)
            logger.info("Chromium 下载源：%s", env["PLAYWRIGHT_DOWNLOAD_HOST"])
            # chromium 约 430MB，慢网下可能超过 30 分钟；超时也不直接判失败，
            # 由 check_browser() 复查缓存目录里的 INSTALLATION_COMPLETE 标记。
            proc = _run([sys.executable, "-m", "playwright", "install", "chromium"],
                        timeout=1800, env=env)
            if check_browser().get("ok"):
                results["chromium"] = "installed"
            elif proc.returncode == 124:
                results["chromium"] = "timeout（内核可能仍在下载，请稍后重跑本命令确认）"
            else:
                results["chromium"] = f"failed: {proc.stderr[-300:]}"
    return results


def main() -> int:
    if "--in-venv" not in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--in-venv"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="自动安装缺失依赖")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--in-venv", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    # 自检也要在托管 venv 里做 —— 否则裸跑会用基础解释器检查 import，
    # 明明 venv 里依赖齐全却报 MISSING，还会把基础解释器推荐给用户。
    ensure_venv()

    if args.install:
        result = install(log)
        log.info("安装结果：%s", result)

    report = {
        "python": check_python(),
        "platform": platform.platform(),
        "skill_dir": str(SKILL_DIR),
        "deps": {mod: check_import(mod) for mod, _ in PIP_PACKAGES},
        "browser": check_browser(),
        "ffmpeg": check_ffmpeg(),
        "login_state": check_state(),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("=" * 56)
    print("小红书账号深度拆解 - 环境自检")
    print("=" * 56)
    print(f"Python      : {report['python']['version']}  ({report['python']['path']})")
    print(f"系统        : {report['platform']}")
    for mod, ok in report["deps"].items():
        print(f"{mod:<11} : {'OK' if ok else 'MISSING'}")
    print(f"chromium    : {'OK' if report['browser'].get('ok') else report['browser'].get('reason', 'MISSING')}")
    print(f"ffmpeg      : {'OK' if report['ffmpeg']['ok'] else 'MISSING（视频抽帧不可用）'}"
          f"{'（复用 playwright 内置版）' if report['ffmpeg'].get('bundled') else ''}")
    st = report["login_state"]
    print("登录态      : " + ("（当前存在登录态文件）" if st["login_saved"] else "（无）")
          + " · 每次抓取都会先清空再要求重新扫码/验证码登录")
    print(f"后续命令请用这个解释器：{sys.executable}")

    missing = [m for m, ok in report["deps"].items() if not ok]
    if missing and not args.install:
        print("\n提示：执行 `python bootstrap.py --install` 安装缺失依赖。")
    if not report["ffmpeg"]["ok"]:
        print("\n提示：缺少可用的 ffmpeg，视频抽帧与关键帧拼版不可用，"
              "爆款分镜拆解会降级为「仅封面 + 文本」分析。")
        print("      任选其一安装后重跑本脚本确认：")
        print("      · 系统级：Windows `winget install Gyan.FFmpeg` / macOS `brew install ffmpeg`")
        print("      · 免改 PATH：`npm install ffmpeg-static`（装到托管 workspace 即会被自动找到）")
        print("      注意：playwright 内置的 ffmpeg 只有编码器，读不了 mp4，不能替代。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
