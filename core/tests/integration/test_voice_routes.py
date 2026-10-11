"""语音路由：状态、关键词校验，以及真链路的冒烟。

识别与朗读都要**真模型 + 真算**（识别 300ms、朗读 3s），所以各自 ``skipif`` ——
但它们是"到底能不能用"的判据，不能只靠 mock 绿着：那种绿什么都说明不了。
"""

from __future__ import annotations

import base64
import wave
from pathlib import Path

import numpy as np
import pytest

from my_agent.voice import asr, tts

pytestmark = pytest.mark.asyncio

#: 一段真人感不足、但内容确定的短音频（"发送"）。用系统 TTS 生成后入库，
#: 59KB —— 比塞一段真录音小得多，且内容永远一致。
FIXTURE = Path(__file__).parent.parent / "fixtures" / "voice" / "cmd.wav"


def read_fixture() -> tuple[np.ndarray, int]:
    with wave.open(str(FIXTURE), "rb") as fh:
        rate = fh.getframerate()
        raw = fh.readframes(fh.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, rate


def b64(samples: np.ndarray) -> str:
    return base64.b64encode(samples.astype("<f4").tobytes()).decode("ascii")


async def test_状态端点列出两种能力(client):
    """⚠️ 只有识别与朗读。

    唤醒用的 KWS 小模型已**彻底弃用**（2026-10-04），它不再是独立能力 ——
    唤醒现在就是"识别 + 拼音匹配唤醒词"。如果哪天这里又冒出 ``wake``，
    说明有人把 KWS 加回来了，那是有意为之还是回退，需要说清楚。
    """
    resp = await client.get("/v1/voice/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"asr", "tts"}
    for name, value in body.items():
        assert {"available", "loaded"} <= set(value), name
    # 加载是懒的：只问状态不该把 228MB 的模型拉起来
    assert body["asr"]["loaded"] is False


async def test_识别_空音频报422(client):
    resp = await client.post("/v1/voice/asr", json={"pcm": "", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_识别_采样率不合理报422(client):
    resp = await client.post("/v1/voice/asr", json={"pcm": b64(np.zeros(16, "f4")), "sample_rate": 4000})
    assert resp.status_code == 422


async def test_识别_字节数不是四的倍数报422(client):
    # "AAAA" 是合法 base64（4 个字符 → 3 字节），但 3 不是 4 的倍数：
    # 说明调用方少传了尾字节，必须拦下来而不是硬解成半个 float32
    resp = await client.post("/v1/voice/asr", json={"pcm": "AAAA", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_识别_脏base64报422而不是500(client):
    # 5 个字符是"4 的倍数加一"，Python 的 base64 会直接抛异常 —— 那是调用方的问题，
    # 不该变成 500（500 意味着"我们挂了"，而这里我们没挂）
    resp = await client.post("/v1/voice/asr", json={"pcm": "AAAAA", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_唤醒_没有配唤醒词报422(client):
    resp = await client.post(
        "/v1/voice/wake", json={"pcm": b64(np.zeros(1600, "f4")), "sample_rate": 16000, "words": []}
    )
    assert resp.status_code == 422


@pytest.mark.skipif(not asr.model_available(), reason="识别模型不在位")
async def test_识别_真链路(client):
    """真跑一次识别：这是"语音输入到底能不能用"的唯一判据。"""
    samples, rate = read_fixture()
    resp = await client.post("/v1/voice/asr", json={"pcm": b64(samples), "sample_rate": rate})
    assert resp.status_code == 200
    body = resp.json()
    assert "发送" in body["text"], body
    # 时长要按**传入的**采样率算，不能拿模型内部的 16k 硬套
    assert abs(body["duration_ms"] - len(samples) * 1000 / rate) < 50
    assert body["took_ms"] > 0


@pytest.mark.skipif(not asr.model_available(), reason="识别模型不在位")
async def test_唤醒_真链路能听出唤醒词(client):
    """真跑一次唤醒判定：夹具里说的是「发送」，就拿它当唤醒词。

    这条断言是**能**钉死的：唤醒判定走的是识别 + 拼音匹配，夹具内容确定，
    所以「发送」必须命中。不再像 KWS 时代那样只能验"跑得通"——
    那正是当时"喊四五次才中一次"没被测试拦下的原因。
    """
    samples, rate = read_fixture()
    resp = await client.post(
        "/v1/voice/wake",
        json={"pcm": b64(samples), "sample_rate": rate, "words": ["发送"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hit"] == "发送", body
    assert body["source"] == "asr"
    assert "发送" in body["text"]


@pytest.mark.skipif(not tts.model_available(), reason="朗读模型不在位")
async def test_朗读_真链路(client):
    resp = await client.post("/v1/voice/tts", json={"text": "发送", "speaker": 0, "speed": 1.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["duration_ms"] > 0
    data = base64.b64decode(body["wav"])
    # RIFF/WAVE 头：自己封的 WAV 必须真的是 WAV，别让前端拿到一坨裸 PCM
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"


async def test_朗读_空文本报422(client):
    resp = await client.post("/v1/voice/tts", json={"text": "   "})
    assert resp.status_code == 422
