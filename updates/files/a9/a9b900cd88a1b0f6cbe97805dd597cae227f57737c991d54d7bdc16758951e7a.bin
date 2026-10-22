#!/usr/bin/env python3
"""video-script-dissect 环境一键自检。

检测本地视频分析所需的依赖是否齐全，并给出补装命令。
只做检测与提示：不自动安装、不联网、不修改任何文件。

运行：
    python scripts/check_env.py
（建议用隔离 venv：python）
"""
import importlib.util
import shutil
import sys

PYPI = " -i https://pypi.org/simple"


def have_cmd(name):
    return shutil.which(name) is not None


def have_module(name):
    return importlib.util.find_spec(name) is not None


def main():
    print("🔧 video-script-dissect 环境自检\n")

    rows = []

    # ffmpeg（系统 或 imageio 兜底）
    if have_cmd("ffmpeg"):
        rows.append(("ffmpeg (系统)", "✅", "已就绪"))
    elif have_module("imageio_ffmpeg"):
        rows.append(("ffmpeg (imageio 兜底)", "✅", "已就绪（imageio-ffmpeg 自带二进制）"))
    else:
        rows.append(("ffmpeg", "❌",
                     "缺。二选一：系统装 ffmpeg，或 pip install imageio-ffmpeg" + PYPI))

    # faster-whisper（ASR 核心）
    ok = have_module("faster_whisper")
    rows.append(("faster-whisper", "✅" if ok else "❌",
                 "已就绪" if ok else "缺（语音转写核心）。pip install faster-whisper" + PYPI + "（首次会下语音模型几百 MB）"))

    # imageio-ffmpeg（抽帧兜底）
    ok = have_module("imageio_ffmpeg")
    rows.append(("imageio-ffmpeg", "✅" if ok else "⚠️",
                 "已就绪" if ok else "可选兜底。pip install imageio-ffmpeg" + PYPI))

    # reportlab（PDF 导出）
    ok = have_module("reportlab")
    rows.append(("reportlab", "✅" if ok else "❌",
                 "已就绪" if ok else "缺（PDF 导出用）。pip install reportlab==4.2.5" + PYPI))

    # yt-dlp（公网链接直连下载，可选）
    ok = have_module("yt_dlp")
    rows.append(("yt-dlp", "✅" if ok else "⚠️",
                 "已就绪" if ok else "可选（公网链接直连下载用）。pip install yt-dlp" + PYPI))

    ok = have_module("cryptography")
    rows.append(("cryptography", "✅" if ok else "⚠️",
                 "已就绪" if ok else "可选（按需）。pip install cryptography" + PYPI))

    # 隔离 venv
    isolated = sys.prefix != sys.base_prefix
    rows.append(("隔离 venv", "✅" if isolated else "⚠️",
                 "运行于隔离 venv" if isolated else "警告：当前是系统 Python，建议用隔离 venv 运行"))

    maxn = max(len(r[0]) for r in rows)
    for name, mark, msg in rows:
        print("  {name:<24} {mark}  {msg}".format(name=name, mark=mark, msg=msg))

    print("\n说明：❌ = 影响核心功能需补；⚠️ = 可选 / 降级可用。")
    print("所有依赖仅从官方 PyPI 源安装：" + PYPI.strip())


if __name__ == "__main__":
    main()
