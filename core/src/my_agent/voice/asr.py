




















from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .models import MAX_THREADS, SENSE_VOICE_DIR, find_model_dir



from .tts import dependency_ready

logger = logging.getLogger(__name__)

_MODEL_FILE = "model.int8.onnx"
_TOKENS_FILE = "tokens.txt"

_recognizer: Any = None
_lock = threading.Lock()


@dataclass
class AsrResult:







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







    if not dependency_ready():
        return False
    model_dir = find_model_dir(SENSE_VOICE_DIR)
    if model_dir is None:
        return False
    return (model_dir / _MODEL_FILE).is_file() and (model_dir / _TOKENS_FILE).is_file()


def recognizer_ready() -> bool:

    return _recognizer is not None


def _build() -> Any:
    
    
    from .tts import prepare_espeak_env

    prepare_espeak_env()

    import sherpa_onnx  

    model_dir = find_model_dir(SENSE_VOICE_DIR)
    if model_dir is None:
        raise RuntimeError(f"未找到语音识别模型 {SENSE_VOICE_DIR}")

    logger.info("正在加载语音识别模型（%s）", model_dir.name)
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_dir / _MODEL_FILE),
        tokens=str(model_dir / _TOKENS_FILE),
        num_threads=MAX_THREADS,
        use_itn=True,  
        language="auto",  
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

    import time

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim != 1:
        raise ValueError("只接受单声道波形（前端应先把多声道混成一路）")
    duration_ms = int(len(audio) * 1000 / max(sample_rate, 1))

    started = time.perf_counter()
    recognizer = _get()
    with _lock:  
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

    global _recognizer
    with _lock:
        _recognizer = None


def _model_path_for_tests() -> Path | None:  
    return find_model_dir(SENSE_VOICE_DIR)


__all__ = [
    "AsrResult",
    "dependency_ready",
    "model_available",
    "recognize",
    "recognizer_ready",
    "reset",
]
