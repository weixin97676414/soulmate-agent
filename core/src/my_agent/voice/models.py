









from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

VOICE_SUBDIR = "voice"


SENSE_VOICE_DIR = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"

KOKORO_DIR = "kokoro-int8-multi-lang-v1_0"





ENV_VOICE_DIR = "AGENT_VOICE_MODEL_DIR"


MAX_THREADS = 4


def candidate_roots() -> list[Path]:

    override = os.environ.get(ENV_VOICE_DIR, "").strip()
    if override:
        return [Path(override)]

    roots: list[Path] = []

    
    
    
    
    
    
    
    data_root = os.environ.get("AGENT_DATA_DIR", "").strip()
    if data_root:
        roots.append(Path(data_root) / "models" / VOICE_SUBDIR)
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            roots.append(Path(appdata) / "Soulmate Agent" / "models" / VOICE_SUBDIR)

    
    
    
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass) / "models" / VOICE_SUBDIR)

    here = Path(__file__).resolve()
    
    roots.append(here.parents[3] / "models" / VOICE_SUBDIR)
    
    for parent in list(here.parents)[:8]:
        roots.append(parent / "models" / VOICE_SUBDIR)

    return roots


def find_model_dir(dirname: str) -> Path | None:





    for root in candidate_roots():
        path = root / dirname
        if path.is_dir():
            return path
    logger.warning("未找到语音模型 %s（候选根：%s）", dirname, candidate_roots())
    return None
