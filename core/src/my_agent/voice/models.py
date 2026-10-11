"""语音模型的位置探测。

与 ``memory/local_embedding.py`` 同一套思路，理由也相同：**同一份代码要在三种
形态下跑** —— PyInstaller 打包后的核心、源码里直接跑、以及测试环境。任何单一路径
写法都会在其中一种下找不到文件，而那种失败通常表现为"功能悄悄不可用"，不报错。

模型随包分发，放在 ``core/models/voice/<模型名>/``（与嵌入模型 ``core/models/
qwen3-embedding-0.6b`` 同一层级）—— 由仓库根的 ``_fetch_voice_models.py`` 拉取。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

VOICE_SUBDIR = "voice"

#: SenseVoice-Small：中/英/日/韩/粤 + 情感与音频事件，非自回归（CPU 上 10s 音频约 70ms）
SENSE_VOICE_DIR = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
#: 朗读：Kokoro 多语言（含中文），54 个音色
KOKORO_DIR = "kokoro-int8-multi-lang-v1_0"

# 这里曾有 ``KWS_DIR``（唤醒词专用的 zipformer 小模型）。彻底弃用：
# 它对真人的命中率太糟（见 voice/__init__.py 的说明），唤醒改用识别模型 + 拼音匹配。

#: 环境变量覆盖，给测试与"外挂模型"用（与嵌入模型的 ``AGENT_EMBEDDING_MODEL_DIR`` 对齐）
ENV_VOICE_DIR = "AGENT_VOICE_MODEL_DIR"

#: 线程上限。本地 CPU 推理，放开会把整机占满（用户那边可能还在跑别的程序）。
MAX_THREADS = 4


def candidate_roots() -> list[Path]:
    """``models/voice`` 可能所在的位置，按优先级排列。"""
    override = os.environ.get(ENV_VOICE_DIR, "").strip()
    if override:
        return [Path(override)]

    roots: list[Path] = []

    # 0) **用户按需下载的目录**（起模型不再随包，改成首启按需下载）：
    #    ``%APPDATA%/Soulmate Agent/models/voice``。
    #    ⚠️ 排在**最前**：万一包里还留着旧模型（打包配置漏改），也应该优先用
    #    用户自己下过的那份 —— 用户看到的是"我下载的生效了"，而不是"下了没反应"。
    #    ⚠️ 这里不能 import ``config.paths``：本模块要能在"核心还没初始化路径"时被
    #    单独 import（测试与状态探测都会这么做）。所以按同样的规则自己算一次，
    #    并用 ``AGENT_DATA_DIR`` 覆盖保持一致 —— 两处必须同源，否则测试里会对不上。
    data_root = os.environ.get("AGENT_DATA_DIR", "").strip()
    if data_root:
        roots.append(Path(data_root) / "models" / VOICE_SUBDIR)
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            roots.append(Path(appdata) / "Soulmate Agent" / "models" / VOICE_SUBDIR)

    # 1) PyInstaller 打包后：sys._MEIPASS 指向 _internal，模型就在它的 models/voice 下。
    #    用 _MEIPASS 而不是靠 __file__ 往上数层级 —— 打包后模块在 PYZ 里，
    #    __file__ 的层级不一定和源码里一样，数层级是脆的。
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass) / "models" / VOICE_SUBDIR)

    here = Path(__file__).resolve()
    # 2) 源码里直接跑：<repo>/core/src/my_agent/voice/models.py -> <repo>/core/models/voice
    roots.append(here.parents[3] / "models" / VOICE_SUBDIR)
    # 3) 兜底：沿目录往上找（覆盖其它打包形态）
    for parent in list(here.parents)[:8]:
        roots.append(parent / "models" / VOICE_SUBDIR)

    return roots


def find_model_dir(dirname: str) -> Path | None:
    """定位某个语音模型目录；找不到返回 ``None``。

    返回 ``None`` 而不是抛异常：调用方据此给出**明确的不可用提示**，
    而不是让整个核心起不来 —— 语音是可选能力，不该拖垮主流程。
    """
    for root in candidate_roots():
        path = root / dirname
        if path.is_dir():
            return path
    logger.warning("未找到语音模型 %s（候选根：%s）", dirname, candidate_roots())
    return None
