"""Kokoro 朗读：文本进、WAV 字节出。

## ⚠️ espeak-ng 的中文路径坑（本模块存在的最大理由）

espeak-ng 是 C 库，**按本地代码页打开数据文件**，于是：

1. 路径里有中文 → 直接 ``Illegal byte sequence``。开发环境的仓库路径恰好是
   ``d:\\win版客户端开发\\Soulmate Agent 开源代码\\...``，必踩；
2. 它在**库初始化**时就读 ``ESPEAK_DATA_PATH`` —— 环境变量必须在
   ``import sherpa_onnx`` **之前**设好。``os.environ`` 之后再改已经晚了；
3. 8.3 短名是常见绕法，但这台机器上 NTFS 短名被禁用（``GetShortPathNameW``
   原样返回长路径），所以只能**复制**。

于是 ``prepare_espeak_env()`` 负责：把 ``espeak-ng-data`` / ``dict`` /
``lexicon-*.txt`` 复制到**纯 ASCII 的临时根目录**、设好环境变量。
它是幂等的，且必须在任何 ``import sherpa_onnx`` 之前调用 ——
**识别侧（``asr.py``）也调它**，因为只要 sherpa_onnx 被 import 一次，
espeak 的路径就定死了，之后朗读再设就来不及。

打包后的安装路径是英文，这一步会自动跳过（那个坑只在 dev 出现）。

## 实时率只有 1.0–1.2x

实测 int8 版合成 4 秒语音要 4 秒（对比识别是 28x）。**够用但不宽裕**，
所以调用方应当**按句切分、边合边播**，不要等整段回复合完才开口。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from .models import KOKORO_DIR, MAX_THREADS, find_model_dir

logger = logging.getLogger(__name__)

_MODEL_FILE = "model.int8.onnx"
_VOICES_FILE = "voices.bin"
_TOKENS_FILE = "tokens.txt"
_LEXICONS = ("lexicon-us-en.txt", "lexicon-zh.txt", "lexicon-gb-en.txt")

#: 复制到哪 —— 纯 ASCII，且不放在数据目录（那是用户的东西，这是派生物）
ASCII_ROOT = Path(os.environ.get("TEMP") or "/tmp") / "soulmate-voice-ascii"

#: 默认音色。Kokoro 多语言版有 54 个，中文可用的在其中一部分；
#: 具体哪个最终留下来由用户试听决定（见设计稿第 7 节）。
DEFAULT_SPEAKER = 0

_env_prepared = False
_tts: Any = None
_lock = threading.Lock()


def _ascii_path(path: Path) -> Path:
    """含非 ASCII 就复制到 ASCII 根；纯 ASCII 原样返回。"""
    if all(ord(ch) < 128 for ch in str(path)):
        return path

    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 1024):
        short = Path(buf.value)
        if all(ord(ch) < 128 for ch in str(short)):
            return short

    target = ASCII_ROOT / path.name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
        logger.info("espeak-ng 需要 ASCII 路径，已复制 %s → %s", path.name, target)
    return target


def prepare_espeak_env() -> Path | None:
    """准备好 espeak-ng 的数据目录并设好环境变量（幂等）。

    **必须在任何 ``import sherpa_onnx`` 之前调用。** 模型不在时返回 ``None``
    并什么都不做 —— 让调用方去报"朗读不可用"，而不是在这里抛异常。
    """
    global _env_prepared
    if _env_prepared:
        return Path(os.environ.get("ESPEAK_DATA_PATH") or "") or None

    model_dir = find_model_dir(KOKORO_DIR)
    if model_dir is None:
        return None

    data_dir = _ascii_path(model_dir / "espeak-ng-data")
    os.environ["ESPEAK_DATA_PATH"] = str(data_dir)
    _env_prepared = True
    return data_dir


def dependency_ready() -> bool:
    """``sherpa_onnx``（朗读与识别共用的那个引擎包）在当前解释器里**能不能导入**。

    ⚠️ 为什么"模型文件在不在"之外还要查这个 —— 那是两件事。换机、dev 用错了
    解释器、或有人手动卸了包时，模型文件都还在，可引擎**根本建不起来**；
    只查文件的话状态会报"可用"，用户点了才失败（2026-10-06 真踩到过：系统 Python
    没装 sherpa_onnx，``/v1/voice/asr`` 直接 500）。

    ⚠️ 用 ``find_spec`` 而**不是**真的 ``import``：导入会加载原生库，而且会在
    导入那一刻**定死 espeak-ng 的数据路径**（见模块 docstring：环境变量必须在
    ``import sherpa_onnx`` 之前设好）。一个"能不能用"的状态查询不该有这种副作用 ——
    否则 ``prepare_espeak_env()`` 就永远赶不上了。

    ``asr.py`` 也用这个函数（两侧共用同一个包）。
    """
    return importlib.util.find_spec("sherpa_onnx") is not None


def model_available() -> bool:
    """朗读能不能用：**依赖在位** 且 模型文件齐全。"""
    if not dependency_ready():
        return False
    model_dir = find_model_dir(KOKORO_DIR)
    if model_dir is None:
        return False
    return (model_dir / _MODEL_FILE).is_file() and (model_dir / _VOICES_FILE).is_file()


def tts_ready() -> bool:
    """引擎是否**已经加载**（区别于"模型在不在"）。"""
    return _tts is not None


def _build() -> Any:
    # ⚠️ 顺序不能反：环境变量必须在 import sherpa_onnx 之前设好（见模块 docstring）
    data_dir = prepare_espeak_env()

    import sherpa_onnx

    model_dir = find_model_dir(KOKORO_DIR)
    if model_dir is None:
        raise RuntimeError(f"未找到朗读模型 {KOKORO_DIR}")

    lexicon = ",".join(str(_ascii_path(model_dir / name)) for name in _LEXICONS)
    logger.info("正在加载朗读模型（%s）", model_dir.name)
    return sherpa_onnx.OfflineTts(
        sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=str(model_dir / _MODEL_FILE),
                    voices=str(model_dir / _VOICES_FILE),
                    tokens=str(model_dir / _TOKENS_FILE),
                    data_dir=str(data_dir) if data_dir else "",
                    dict_dir=str(_ascii_path(model_dir / "dict")),
                    lexicon=lexicon,
                ),
                num_threads=MAX_THREADS,
                provider="cpu",
            ),
            max_num_sentences=1,
        )
    )


def _get() -> Any:
    global _tts
    if _tts is None:
        with _lock:
            if _tts is None:
                _tts = _build()
    return _tts


def speaker_count() -> int:
    """可用音色数（引擎没加载时返回 0，避免为了问一句就把 180MB 拉起来）。"""
    return int(getattr(_tts, "num_speakers", 0)) if _tts is not None else 0


def synthesize(text: str, *, speaker: int = DEFAULT_SPEAKER, speed: float = 1.0) -> tuple[Any, int]:
    """合成一段语音，返回 ``(float32 采样列表, 采样率)``。

    不直接返回 WAV 字节：前端与"试听"两条路都要用，让调用方决定怎么封。
    """
    content = (text or "").strip()
    if not content:
        raise ValueError("要朗读的内容为空")

    engine = _get()
    with _lock:  # 同一个 C++ 引擎串行用
        audio = engine.generate(content, sid=speaker, speed=speed)
    return audio.samples, int(audio.sample_rate)


def wav_bytes(samples: Any, sample_rate: int) -> bytes:
    """把采样封成 16-bit PCM WAV。

    不用 ``audio.save()``：1.13.8 的 ``GeneratedAudio`` 上**没有**这个方法（实测
    AttributeError），它只给 ``samples`` / ``sample_rate``，自己封反而更稳。
    """
    import array
    import io
    import wave

    buf = io.BytesIO()
    clipped = array.array("h", (max(-32768, min(32767, int(s * 32767))) for s in samples))
    with wave.open(buf, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(clipped.tobytes())
    return buf.getvalue()


def reset() -> None:
    """丢掉已加载的引擎（测试与"换音色重载"用）。"""
    global _tts
    with _lock:
        _tts = None


__all__ = [
    "DEFAULT_SPEAKER",
    "dependency_ready",
    "model_available",
    "prepare_espeak_env",
    "speaker_count",
    "synthesize",
    "tts_ready",
    "wav_bytes",
]
