


































from __future__ import annotations

from .asr import AsrResult, recognize, recognizer_ready
from .tts import synthesize, tts_ready

__all__ = [
    "AsrResult",
    "recognize",
    "recognizer_ready",
    "synthesize",
    "tts_ready",
]
