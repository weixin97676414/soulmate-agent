"""语音接口：识别 / 唤醒判定 / 朗读。

⚠️ **唤醒判定没有独立模型**：曾经挂过专门的 KWS 小模型，但它对真人命中率太糟
（详见 ``voice_wake`` 的说明），2026-10-04 彻底弃用 —— 现在直接用识别结果去匹配
唤醒词（**按拼音**，不是按字面）。

## 为什么音频走 JSON 里的 base64

前端拿到的就是 ``Float32Array``，转 base64 只是一次内存编码；而 multipart 在
FastAPI 里要多一层文件解析，且 16kHz / 1 秒的音频本来就只有 64KB —— 不需要
流式上传那一套。

## 为什么这些端点是同步函数（``def`` 而不是 ``async def``）

sherpa-onnx 的推理是**同步阻塞**的 CPU 计算（识别 300ms、朗读 3s）。用
``async def`` 会把整个事件循环卡住（别的请求、SSE 流全部停摆）；写成 ``def``
FastAPI 会自动丢进线程池，这才是对的用法。
"""

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
    """一段文本 → **无声调拼音串**，专供同音比较。

    ## 为什么必须这样做

    实测：唤醒词「你好搭子」被识别成「你好，**大子**」—— 同音字。语音识别
    永远会有同音错字（它不会知道"搭子"是你要的自定义词），所以**按字面比
    必然失败**。按拼音比之后，「搭子 / 大子 / 达子」都能匹配上。

    ⚠️ **不带声调**：识别对声调尤其不准（"搭" dā 与 "大" dà 在连读里几乎一样），
    带调就是把最不可靠的那一维拿来比较。

    ⚠️ 用整串 ``lazy_pinyin`` 而不是逐字：它能借词组消歧多音字（"行长" → hang zhang），
    也天然把非中文段（英文、数字）原样带过。
    """
    from pypinyin import lazy_pinyin

    cleaned = clean_text(text)
    if not cleaned:
        return ""
    return "".join(lazy_pinyin(cleaned)).lower()


def _find_wake_word(text: str, words: list[str]) -> str | None:
    """在识别结果里找唤醒词，命中返回**用户填的那个词**。

    用"包含"而不是"相等"：用户常常一口气说「你好搭子，帮我看看这个」——
    唤醒词和正文连着说是很自然的说法，要求整句相等等于逼他刻意停顿。
    代价是"他刚才喊了你好搭子"这种句子也会命中，但那对唤醒场景无伤大雅。
    """
    heard = _pinyin_key(text)
    if not heard:
        return None
    for word in words:
        target = _pinyin_key(word)
        if target and target in heard:
            return word
    return None


class PcmPayload(BaseModel):
    """一段单声道音频。"""

    pcm: str
    """base64 编码的 float32 小端序列（前端 ``Float32Array`` 直接转）。"""

    sample_rate: int = 16000


class WakePayload(PcmPayload):
    """唤醒检测：额外带当前生效的唤醒词（用户可随时改）。"""

    words: list[str] = []


class CommandCandidate(BaseModel):
    """一个候选命令：动作 id + 它当前生效的命令词。"""

    id: str
    word: str


class MatchPayload(BaseModel):
    """一段识别文本 + 当前可用的命令词，问"它是不是某个命令"。"""

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
    except Exception as exc:  # noqa: BLE001 - 客户端传了半截/脏 base64，是 422 不是 500
        raise HTTPException(status_code=422, detail=f"音频不是合法的 base64：{exc}") from exc
    if len(raw) % 4:
        raise HTTPException(status_code=422, detail="音频字节数不是 float32 的整数倍")
    return np.frombuffer(raw, dtype="<f4")


def _require(ok: bool, what: str) -> None:
    """模型不在就**明确报错**，绝不静默降级到系统识别（用户对静默降级零容忍）。"""
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"{what}模型未就绪：安装包里缺少模型文件，请重新安装或补跑模型拉取脚本。",
        )


@router.get("/v1/voice/status")
def voice_status() -> dict[str, Any]:
    """三种能力的就位情况。

    分成 ``available``（模型在不在）与 ``loaded``（是否已载入内存）两个维度：
    设置页要据此告诉用户"能用 / 正在加载 / 缺文件"，而不是等点了才失败。
    """
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
    """整段音频 → 文本（含情感与事件标签）。"""
    # ⚠️ 参数校验**排在可用性检查之前**（调整）：请求本身写错了就该是 422，
    # 不该被"模型未就绪"的 503 盖过去 —— 那样调用方会以为是服务的问题，查错方向。
    # 这两件事本来就互不依赖：`_decode` 是纯校验，不需要模型在位。
    samples = _decode(payload)
    _require(asr.model_available(), "语音识别")
    try:
        return asr.recognize(samples, payload.sample_rate).to_dict()
    except Exception as exc:  # noqa: BLE001 - 转成结构化错误，别让 500 淹没原因
        raise HTTPException(status_code=500, detail=f"识别失败：{exc}") from exc


@router.post("/v1/voice/wake")
def voice_wake(payload: WakePayload) -> dict[str, Any]:
    """一小段音频 → 有没有说出唤醒词。

    ## 为什么**只用**识别模型，不用更"对口"的 KWS

    KWS（关键词唤醒）看着更合适：模型只有 5MB、几乎不耗 CPU，天生为"常开待命"设计。
    但**真人**实测命中率很糟 —— 它的训练音频是合成音（音调平、语速稳），真人喊同一个
    词要重复四五次才中一次。这不是调阈值能救的：阈值调到能蒙中的位置，环境噪音就
    也能把它唤醒了。

    而识别模型（SenseVoice）本来就是做"听清人话"的，拿它的结果去匹配唤醒词，一次就中。
    代价是每次检测多花约 300ms 的 CPU —— 但它只在**用户确实说了话**之后才跑
    （前端 VAD 断句后才发请求），待命时什么也不做。这个交换值。

    ⚠️ 匹配必须**按拼音**（见 ``_find_wake_word``）：识别会把「搭子」写成同音字
    「大子」，按字面比永远不中。

    ⚠️ 前端会把**最近几秒**的音频一起发过来（滑动窗口）：用户常常「你好…搭子」中间
    带停顿，只发被 VAD 断出的那一段会被切碎、两边都匹配不上 —— 这正是"要喊四五次
    才中一次"的真相。

    返回里带上 ``text``（这一段到底被听成了什么）：喊不醒时，用户能一眼看出是
    "它没听懂"还是"听懂了但词不匹配"，否则只有无尽地重复喊。
    """
    # ⚠️ 同 voice_asr：请求自己的毛病（没配唤醒词）先按 422 报，别被 503 盖住
    words = [word.strip() for word in payload.words if word.strip()]
    if not words:
        raise HTTPException(status_code=422, detail="没有配置唤醒词")
    _require(asr.model_available(), "语音识别")

    samples = _decode(payload)
    try:
        heard = asr.recognize(samples, payload.sample_rate).text
    except Exception:  # noqa: BLE001 - 认不出就当没听见，别让整条链路报错
        logger.exception("唤醒识别失败")
        return {"hit": None, "source": "asr", "text": ""}

    return {"hit": _find_wake_word(heard, words), "source": "asr", "text": heard}


@router.post("/v1/voice/match")
def voice_match(payload: MatchPayload) -> dict[str, Any]:
    """识别文本 → 命中的命令 id（按拼音，**要求整句相等**）。

    ## 为什么这里是"整句相等"，而唤醒词那边是"包含"

    唤醒词要"包含"：用户会连着正文一起说「你好搭子，帮我看看这个」，
    要求整句相等等于逼他刻意停顿。

    **命令词恰恰相反** —— 它们很短（「确认」「不用了」），用"包含"的话
    「帮我**确认**一下这个文件」会被判成批准一个高危操作。那是会出事的。
    所以这里宁可让用户重说一遍，也不放宽。

    ## 为什么放在核心

    同音字匹配要拼音，而拼音库（pypinyin）在核心。前端已经先做过一次**字面**
    整句相等，不中才来这里 —— 日常路径因此没有额外往返。
    """
    said = _pinyin_key(payload.text)
    if not said:
        return {"id": None}
    for item in payload.candidates:
        if item.id and _pinyin_key(item.word) == said:
            return {"id": item.id}
    return {"id": None}


@router.post("/v1/voice/tts")
def voice_tts(payload: TtsPayload) -> dict[str, Any]:
    """文本 → WAV（base64）。"""
    # ⚠️ 同 voice_asr：空文本是请求自己的毛病，先按 422 报
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="要朗读的内容为空")
    _require(tts.model_available(), "朗读")
    try:
        samples, rate = tts.synthesize(
            payload.text, speaker=payload.speaker, speed=payload.speed
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"朗读失败：{exc}") from exc

    data = tts.wav_bytes(samples, rate)
    return {
        "wav": base64.b64encode(data).decode("ascii"),
        "sample_rate": rate,
        "duration_ms": int(len(samples) * 1000 / max(rate, 1)),
    }



