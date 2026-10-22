





from __future__ import annotations

import base64
import wave
from pathlib import Path

import numpy as np
import pytest

from my_agent.voice import asr, tts

pytestmark = pytest.mark.asyncio



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






    resp = await client.get("/v1/voice/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"asr", "tts"}
    for name, value in body.items():
        assert {"available", "loaded"} <= set(value), name
    
    assert body["asr"]["loaded"] is False


async def test_识别_空音频报422(client):
    resp = await client.post("/v1/voice/asr", json={"pcm": "", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_识别_采样率不合理报422(client):
    resp = await client.post("/v1/voice/asr", json={"pcm": b64(np.zeros(16, "f4")), "sample_rate": 4000})
    assert resp.status_code == 422


async def test_识别_字节数不是四的倍数报422(client):
    
    
    resp = await client.post("/v1/voice/asr", json={"pcm": "AAAA", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_识别_脏base64报422而不是500(client):
    
    
    resp = await client.post("/v1/voice/asr", json={"pcm": "AAAAA", "sample_rate": 16000})
    assert resp.status_code == 422


async def test_唤醒_没有配唤醒词报422(client):
    resp = await client.post(
        "/v1/voice/wake", json={"pcm": b64(np.zeros(1600, "f4")), "sample_rate": 16000, "words": []}
    )
    assert resp.status_code == 422


@pytest.mark.skipif(not asr.model_available(), reason="识别模型不在位")
async def test_识别_真链路(client):

    samples, rate = read_fixture()
    resp = await client.post("/v1/voice/asr", json={"pcm": b64(samples), "sample_rate": rate})
    assert resp.status_code == 200
    body = resp.json()
    assert "发送" in body["text"], body
    
    assert abs(body["duration_ms"] - len(samples) * 1000 / rate) < 50
    assert body["took_ms"] > 0


@pytest.mark.skipif(not asr.model_available(), reason="识别模型不在位")
async def test_唤醒_真链路能听出唤醒词(client):






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
    
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"


async def test_朗读_空文本报422(client):
    resp = await client.post("/v1/voice/tts", json={"text": "   "})
    assert resp.status_code == 422
