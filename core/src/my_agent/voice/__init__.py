"""语音能力：识别 / 朗读。

## 为什么放在核心而不是前端

``onnxruntime`` 已经随包（chromadb 的依赖，见 ``build/agent-core.spec``），核心侧
加 ``sherpa-onnx`` 只多 2.4MB；而前端要跑就得引 onnxruntime-web（WASM + 200MB 资源），
又慢又重，还要多维护一套模型分发。

## 职责边界

- **识别** ``asr``：整段 PCM 进、文本出。前端负责采集、VAD 与断句。
- **朗读** ``tts``：文本进、WAV 出。

⚠️ **唤醒不是独立模块**。曾经用过专门的 KWS 小模型（``kws.py``，5MB、常开待命），
但它对**真人**命中率很糟 —— 训练音频是合成音，真人喊同一个词要重复四五次才中一次，
而且这不是调阈值能救的（调到能蒙中的位置，环境噪音也能唤醒）。

2026-10-04 按用户要求**彻底弃用**：唤醒改为"用识别结果 + **拼音**匹配唤醒词"
（见 ``server/routes/voice.py`` 的 ``voice_wake``）。少一层模型，准确率反而高得多。

音频**不在核心解码**：前端用 Web Audio 直接拿得到 16kHz 单声道 Float32，
于是这里省掉 ffmpeg / librosa / soundfile 一整类依赖。

## 模型一律懒加载

模型合计约 230MB（打包后），启动时无条件载入会让冷启动多等好几秒，而多数用户
根本不用语音。第一次真正要用时才加载 —— 各模块自己持有单例。

## 模型路径

``core/models/voice/<模型名>/``，探测逻辑与 ``memory/local_embedding.py`` 一致
（打包后用 ``sys._MEIPASS``、源码里按相对位置、再沿目录上溯兜底）——
三种运行形态都要能找到，写死一个路径必然在其中一种下悄悄失效。
"""

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
