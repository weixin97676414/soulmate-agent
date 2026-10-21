


























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


ASCII_ROOT = Path(os.environ.get("TEMP") or "/tmp") / "soulmate-voice-ascii"



DEFAULT_SPEAKER = 0

_env_prepared = False
_tts: Any = None
_lock = threading.Lock()


def _ascii_path(path: Path) -> Path:

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














    return importlib.util.find_spec("sherpa_onnx") is not None


def model_available() -> bool:

    if not dependency_ready():
        return False
    model_dir = find_model_dir(KOKORO_DIR)
    if model_dir is None:
        return False
    return (model_dir / _MODEL_FILE).is_file() and (model_dir / _VOICES_FILE).is_file()


def tts_ready() -> bool:

    return _tts is not None


def _build() -> Any:
    
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

    return int(getattr(_tts, "num_speakers", 0)) if _tts is not None else 0


def synthesize(text: str, *, speaker: int = DEFAULT_SPEAKER, speed: float = 1.0) -> tuple[Any, int]:




    content = (text or "").strip()
    if not content:
        raise ValueError("要朗读的内容为空")

    engine = _get()
    with _lock:  
        audio = engine.generate(content, sid=speaker, speed=speed)
    return audio.samples, int(audio.sample_rate)


def wav_bytes(samples: Any, sample_rate: int) -> bytes:





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
