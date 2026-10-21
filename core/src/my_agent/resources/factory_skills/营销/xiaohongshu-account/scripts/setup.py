# -*- coding: utf-8 -*-












from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from xhs_common import SKILL_DIR, log

try:  
    import bootstrap
except Exception as err:  
    bootstrap = None
    log.warning("无法载入 bootstrap.py（%s），自检能力降级", err)

PIP_PACKAGES = [
    ("playwright", "playwright>=1.47"),
    ("curl_cffi", "curl_cffi>=0.7"),
    ("PIL", "pillow>=10.0"),
]


NODE_WORKSPACE = Path.home() / ".skill-runtime" / "binaries" / "node" / "workspace"


NPM_MIRROR = "https://registry.npmmirror.com"





def check_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:  
        return False


def check_browser() -> dict:
    if bootstrap is not None:
        return bootstrap.check_browser()
    return {"ok": False, "reason": "bootstrap 不可用"}


def check_ffmpeg() -> dict:
    if bootstrap is not None:
        return bootstrap.check_ffmpeg()
    exe = shutil.which("ffmpeg") or ""
    return {"ok": bool(exe), "path": exe, "bundled": False}


def collect_report() -> dict:
    return {
        "python": {"version": sys.version.split()[0], "path": sys.executable},
        "skill_dir": str(SKILL_DIR),
        "deps": {mod: check_import(mod) for mod, _ in PIP_PACKAGES},
        "browser": check_browser(),
        "ffmpeg": check_ffmpeg(),
    }





def install_ffmpeg_static() -> str:




    npm = shutil.which("npm")
    if not npm:
        log.warning("未找到 npm，跳过 ffmpeg-static 安装")
        return ""
    NODE_WORKSPACE.mkdir(parents=True, exist_ok=True)
    log.info("安装 ffmpeg-static → %s", NODE_WORKSPACE)
    exe = NODE_WORKSPACE / "node_modules" / "ffmpeg-static" / (
        "ffmpeg.exe" if os.name == "nt" else "ffmpeg")

    
    for extra in ([], ["--registry", NPM_MIRROR]):
        try:
            subprocess.run([npm, "install", "ffmpeg-static", "--no-audit", "--no-fund", *extra],
                           cwd=str(NODE_WORKSPACE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        except Exception as err:  
            log.warning("ffmpeg-static 安装失败：%s", str(err)[:160])
        if exe.exists():
            log.info("ffmpeg 就绪：%s", exe)
            return str(exe)
        if not extra:
            log.info("官方 npm 源未成功，改用镜像重试：%s", NPM_MIRROR)

    log.warning("ffmpeg-static 安装后未找到二进制，视频抽帧可能不可用")
    return ""


def prepare(with_browser: bool = True, with_ffmpeg: bool = False,
            download_host: str = "") -> dict:

    if bootstrap is None:
        return {"error": "bootstrap.py 不可用，无法安装依赖"}
    result = bootstrap.install(log, with_browser=with_browser, download_host=download_host)
    if with_ffmpeg and not check_ffmpeg().get("ok"):
        path = install_ffmpeg_static()
        result["ffmpeg_static"] = path or "failed"
    return result





def main() -> int:
    ap = argparse.ArgumentParser(description="小红书账号拆解技能 - 一键环境准备")
    ap.add_argument("--check", action="store_true", help="只自检并输出 JSON")
    ap.add_argument("--no-browser", action="store_true", help="跳过 Chromium 下载")
    ap.add_argument("--with-ffmpeg", action="store_true", help="尝试安装 ffmpeg-static")
    ap.add_argument("--host", default="", help="Chromium 下载源（默认走国内镜像；"
                                               "官方源：https://playwright.azureedge.net）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出最终自检结果")
    ap.add_argument("--in-venv", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.check:
        print(json.dumps(collect_report(), ensure_ascii=False, indent=2))
        return 0

    
    if bootstrap is not None and "--in-venv" not in sys.argv:
        bootstrap.ensure_venv()

    log.info("开始环境准备（浏览器内核：%s）…", "跳过" if args.no_browser else "需要")
    result = prepare(with_browser=not args.no_browser, with_ffmpeg=args.with_ffmpeg,
                     download_host=args.host)
    log.info("安装结果：%s", result)

    report = collect_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("=" * 56)
    print("环境自检")
    print("=" * 56)
    print(f"Python   : {report['python']['version']}")
    for mod, ok in report["deps"].items():
        print(f"{mod:<9}: {'OK' if ok else 'MISSING'}")
    print(f"chromium : {'OK' if report['browser'].get('ok') else report['browser'].get('reason', 'MISSING')}")
    print(f"ffmpeg   : {'OK' if report['ffmpeg'].get('ok') else 'MISSING（视频抽帧不可用）'}")
    print(f"\n后续命令请用这个解释器：\n{sys.executable}")

    missing = [m for m, ok in report["deps"].items() if not ok]
    if missing:
        print(f"\n⚠️ 仍有依赖缺失：{'、'.join(missing)}，请重跑 `python setup.py`。")
        return 1
    if not report["browser"].get("ok") and not args.no_browser:
        print("\n⚠️ Chromium 未就绪（可能是下载超时），重跑 `python setup.py` 会断点续传。")
        return 1
    print("\n✅ 环境就绪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
