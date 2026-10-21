


















from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...voice import asr, tts
from ...voice.text import clean_text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

def _pinyin_key(text: str) -> str:














    from pypinyin import lazy_pinyin

    cleaned = clean_text(text)
    if not cleaned:
        return ""
    return "".join(lazy_pinyin(cleaned)).lower()


def _find_wake_word(text: str, words: list[str]) -> str | None:






    heard = _pinyin_key(text)
    if not heard:
        return None
    for word in words:
        target = _pinyin_key(word)
        if target and target in heard:
            return word
    return None


class PcmPayload(BaseModel):


    pcm: str
    """base64 编码的 float32 小端序列（前端 ``Float32Array`` 直接转）。"""

    sample_rate: int = 16000


class WakePayload(PcmPayload):


    words: list[str] = []


class CommandCandidate(BaseModel):


    id: str
    word: str


class MatchPayload(BaseModel):


    text: str
    candidates: list[CommandCandidate] = []


class TtsPayload(BaseModel):
    text: str
    speaker: int = tts.DEFAULT_SPEAKER
    speed: float = 1.0


def _decode(payload: PcmPayload) -> Any:
    import numpy as np

    if not payload.pcm:
        raise HTTPException(status_code=422, detail="音频内容为空")
    if not 8000 <= payload.sample_rate <= 48000:
        raise HTTPException(status_code=422, detail=f"采样率不合理：{payload.sample_rate}")
    try:
        raw = base64.b64decode(payload.pcm, validate=False)
    except Exception as exc:  
        raise HTTPException(status_code=422, detail=f"音频不是合法的 base64：{exc}") from exc
    if len(raw) % 4:
        raise HTTPException(status_code=422, detail="音频字节数不是 float32 的整数倍")
    return np.frombuffer(raw, dtype="<f4")


def _require(ok: bool, what: str) -> None:

    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"{what}模型未就绪：安装包里缺少模型文件，请重新安装或补跑模型拉取脚本。",
        )


@router.get("/v1/voice/status")
def voice_status() -> dict[str, Any]:





    return {
        "asr": {"available": asr.model_available(), "loaded": asr.recognizer_ready()},
        "tts": {
            "available": tts.model_available(),
            "loaded": tts.tts_ready(),
            "speakers": tts.speaker_count(),
        },
    }


@router.post("/v1/voice/asr")
def voice_asr(payload: PcmPayload) -> dict[str, Any]:

    
    
    
    samples = _decode(payload)
    _require(asr.model_available(), "语音识别")
    try:
        return asr.recognize(samples, payload.sample_rate).to_dict()
    except Exception as exc:  
        raise HTTPException(status_code=500, detail=f"识别失败：{exc}") from exc


@router.post("/v1/voice/wake")
def voice_wake(payload: WakePayload) -> dict[str, Any]:























    
    words = [word.strip() for word in payload.words if word.strip()]
    if not words:
        raise HTTPException(status_code=422, detail="没有配置唤醒词")
    _require(asr.model_available(), "语音识别")

    samples = _decode(payload)
    try:
        heard = asr.recognize(samples, payload.sample_rate).text
    except Exception:  
        logger.exception("唤醒识别失败")
        return {"hit": None, "source": "asr", "text": ""}

    return {"hit": _find_wake_word(heard, words), "source": "asr", "text": heard}


@router.post("/v1/voice/match")
def voice_match(payload: MatchPayload) -> dict[str, Any]:
















    said = _pinyin_key(payload.text)
    if not said:
        return {"id": None}
    for item in payload.candidates:
        if item.id and _pinyin_key(item.word) == said:
            return {"id": item.id}
    return {"id": None}


@router.post("/v1/voice/tts")
def voice_tts(payload: TtsPayload) -> dict[str, Any]:

    
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="要朗读的内容为空")
    _require(tts.model_available(), "朗读")
    try:
        samples, rate = tts.synthesize(
            payload.text, speaker=payload.speaker, speed=payload.speed
        )
    except Exception as exc:  
        raise HTTPException(status_code=500, detail=f"朗读失败：{exc}") from exc

    data = tts.wav_bytes(samples, rate)
    return {
        "wav": base64.b64encode(data).decode("ascii"),
        "sample_rate": rate,
        "duration_ms": int(len(samples) * 1000 / max(rate, 1)),
    }



