"""SenseVoice 识别：整段音频进、文本出。

## 为什么是"整段"而不是流式

前端已经把音频解码成 16kHz 单声道 Float32，并用 Web Audio 的 RMS 做了 VAD
（静音 0.8 秒判定"说完了"）。所以到这里永远是一段**完整**的语音 ——
不需要流式会话、不需要增量解码；一段一请求，失败还能整段重试。

## 单例 + 串行

实测 ``from_sense_voice`` 每次调用都要**重新加载约 1 秒**（模型 228MB），所以
必须做成进程内单例，且第一次真正用到时才建。识别器本身是有状态的 C++ 对象，
这里用一把锁把调用串起来：语音同一时刻只会有一路，串行不影响体验，
但能避免并发踩坏内部状态。

## 采样率不用管

sherpa-onnx 内部会重采样（实测喂 22050Hz 进去，它自己转到 16000 并打印一行
resampler 日志）。所以调用方把**真实采样率**传进来即可，不必自己转。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .models import MAX_THREADS, SENSE_VOICE_DIR, find_model_dir

# ⚠️ 模块级导入是安全的：``tts`` 顶层**不导入** sherpa_onnx（那是 `_build()` 里
#    才做的事），所以这里不会提前把原生库拉起来、更不会定死 espeak 的数据路径。
from .tts import dependency_ready

logger = logging.getLogger(__name__)

_MODEL_FILE = "model.int8.onnx"
_TOKENS_FILE = "tokens.txt"

_recognizer: Any = None
_lock = threading.Lock()


@dataclass
class AsrResult:
    """一段语音的识别结果。

    除文本外还带上 SenseVoice 顺带给出的情感与音频事件（``<|NEUTRAL|>`` /
    ``<|Speech|>`` 这类）。目前界面不用它们，但**丢弃比保留更麻烦** ——
    以后想让搭子感知语气时不用再来改协议。
    """

    text: str = ""
    emotion: str = ""
    event: str = ""
    language: str = ""
    duration_ms: int = 0
    took_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "emotion": self.emotion,
            "event": self.event,
            "language": self.language,
            "duration_ms": self.duration_ms,
            "took_ms": self.took_ms,
        }


def model_available() -> bool:
    """识别能不能用：**依赖在位** 且 模型文件齐全。

    用于给出"语音不可用"的明确原因，而不是等用户点了才发现。

    ⚠️ 两件事都要查（2026-10-06 补）：只查文件的话，"模型在、但 ``sherpa_onnx``
    没装"的环境会被判成可用 —— 状态接口说能用，用户点了才 500。踩过。
    """
    if not dependency_ready():
        return False
    model_dir = find_model_dir(SENSE_VOICE_DIR)
    if model_dir is None:
        return False
    return (model_dir / _MODEL_FILE).is_file() and (model_dir / _TOKENS_FILE).is_file()


def recognizer_ready() -> bool:
    """识别器是否**已经加载**（区别于"模型在不在"）。"""
    return _recognizer is not None


def _build() -> Any:
    # ⚠️ 必须在 import sherpa_onnx **之前**：只要它被 import 一次，espeak-ng 的
    #    数据路径就定死了，之后朗读再设环境变量已经来不及（详见 tts 的说明）。
    from .tts import prepare_espeak_env

    prepare_espeak_env()

    import sherpa_onnx  # 局部导入：sherpa_onnx 只在这条链路上需要

    model_dir = find_model_dir(SENSE_VOICE_DIR)
    if model_dir is None:
        raise RuntimeError(f"未找到语音识别模型 {SENSE_VOICE_DIR}")

    logger.info("正在加载语音识别模型（%s）", model_dir.name)
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_dir / _MODEL_FILE),
        tokens=str(model_dir / _TOKENS_FILE),
        num_threads=MAX_THREADS,
        use_itn=True,  # 数字/标点归一化："下午三点" → "下午3点"
        language="auto",  # 自动判别中英日韩粤，免得用户还得先选语言
        debug=False,
    )


def _get() -> Any:
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:
                _recognizer = _build()
    return _recognizer


def recognize(samples: np.ndarray, sample_rate: int) -> AsrResult:
    """识别一段波形。``samples`` 是单声道 float32（[-1, 1]），采样率传真实的。"""
    import time

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim != 1:
        raise ValueError("只接受单声道波形（前端应先把多声道混成一路）")
    duration_ms = int(len(audio) * 1000 / max(sample_rate, 1))

    started = time.perf_counter()
    recognizer = _get()
    with _lock:  # 串行调用：同一时刻只允许一路识别用这个有状态的 C++ 对象
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio)
        recognizer.decode_stream(stream)
        result = stream.result
    took_ms = int((time.perf_counter() - started) * 1000)

    return AsrResult(
        text=(result.text or "").strip(),
        emotion=getattr(result, "emotion", "") or "",
        event=getattr(result, "event", "") or "",
        language=getattr(result, "lang", "") or "",
        duration_ms=duration_ms,
        took_ms=took_ms,
    )


def reset() -> None:
    """丢掉已加载的识别器（测试与"模型换了"的场景用）。"""
    global _recognizer
    with _lock:
        _recognizer = None


def _model_path_for_tests() -> Path | None:  # pragma: no cover - 便于排查
    return find_model_dir(SENSE_VOICE_DIR)


__all__ = [
    "AsrResult",
    "dependency_ready",
    "model_available",
    "recognize",
    "recognizer_ready",
    "reset",
]
