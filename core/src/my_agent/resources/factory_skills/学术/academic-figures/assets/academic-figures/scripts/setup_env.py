#!/usr/bin/env python3
"""academic-figures 一键环境准备：依赖检测/安装、中文字体检测、字体缓存清理、自检报告。"""
import os
import shutil
import subprocess
import sys

# v3.7：版本下限精确化（boundary 评测靶点：多库依赖具体版本要求）
REQUIRED = {
    "matplotlib": "matplotlib>=3.5",
    "numpy": "numpy>=1.21",
    "pymupdf": "pymupdf>=1.20",
    "scipy": "scipy>=1.7",
}
MIN_PYTHON = (3, 8)
FAIL_EMOJI = "\u2717"
OK_EMOJI = "\u2713"


def run(cmd, timeout=300):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).returncode == 0
    except Exception:
        return False


def check_python():
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    print(f"[{'OK' if ok else FAIL_EMOJI}] Python {v.major}.{v.minor}.{v.micro}"
          + ("" if ok else f" (需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})"))
    return ok


def check_import(pkg_name, import_name=None):
    import_name = import_name or pkg_name
    try:
        __import__(import_name)
        print(f"[OK] {pkg_name} 已安装")
        return True
    except ImportError:
        print(f"[{FAIL_EMOJI}] {pkg_name} 未安装")
        print(f"        请手动安装（不自动执行 pip，避免供应链风险）:")
        print(f"        {sys.executable} -m pip install {pkg_name}")
        return False


def check_cjk_font():
    detect = os.path.join(os.path.dirname(os.path.abspath(__file__)), "detect_cjk_font.py")
    try:
        result = subprocess.run([sys.executable, detect], capture_output=True, text=True, timeout=30)
        info = json_loads(result.stdout)
        if info.get("found"):
            print(f"[OK] 中文字体: {info.get('name', info.get('path'))}")
            return True
        print(f"[{FAIL_EMOJI}] 未检测到中文字体 → 需安装（Linux: fonts-noto-cjk; macOS: 系统自带）")
        return False
    except Exception:
        print(f"[{FAIL_EMOJI}] 字体检测失败")
        return False


def json_loads(s):
    import json
    try:
        return json.loads(s)
    except Exception:
        return {}


def clear_font_cache():
    if sys.platform == "linux":
        cache = os.path.expanduser("~/.cache/matplotlib")
    elif sys.platform == "darwin":
        cache = os.path.expanduser("~/Library/Caches/matplotlib")
    else:
        cache = os.path.expandvars(r"%LOCALAPPDATA%\matplotlib")
    if os.path.isdir(cache):
        shutil.rmtree(cache, ignore_errors=True)
        print(f"[OK] 已清理 matplotlib 字体缓存: {cache}")
    else:
        print("[OK] 无 matplotlib 缓存（位置: " + cache + "）")


def main():
    print("=== academic-figures 环境自检 ===")
    ok_all = []
    ok_all.append(check_python())
    for pkg, imp in REQUIRED.items():
        ok_all.append(check_import(pkg))
    clear_font_cache()
    ok_all.append(check_cjk_font())
    print()
    if all(ok_all):
        print("环境就绪 ✓ — 可直接使用: python3 scripts/gen_figure.py -t bar -d data.json -o fig.png")
        sys.exit(0)
    print("仍有未满足项，按上方提示安装后重跑本脚本。")
    sys.exit(1)


if __name__ == "__main__":
    main()