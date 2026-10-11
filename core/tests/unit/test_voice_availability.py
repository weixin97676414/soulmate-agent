"""语音可用性判定：**模型文件在不在**与"到底能不能用"是两件事。

## 这一组的由来

``model_available()`` 原先只查模型**文件**在不在。于是"模型在、但 ``sherpa_onnx``
这个包没装"的环境（系统 Python、换机、手动卸包）会被判成**可用** ——
状态接口说"能用"，用户点了才 500。

这不是假想：当时用系统 Python（``C:\\Python314``，没装 sherpa_onnx）跑核心测试，
语音真链路那三条全红（两条 ``assert 500 == 200``、一条 ``{'hit': None, 'text': ''}``），
换成项目 venv 跑就全绿。**判据本身在说谎**，比功能坏掉更难查。
"""

from __future__ import annotations

import importlib.util

from my_agent.voice import asr, tts


def test_依赖在位时能如实报告():
    """本环境（venv）里 sherpa_onnx 是装着的 —— 顺带钉住"检查没写反"。"""
    assert tts.dependency_ready() is True
    assert asr.dependency_ready() is True
    # 两侧共用同一个判定，不该出现"一边说有一边没有"
    assert asr.dependency_ready() is tts.dependency_ready()


def test_缺依赖时一律报不可用(monkeypatch):
    """把 ``find_spec`` 打掉，模拟"包没装"：两侧都必须如实说不可用。

    ⚠️ 这条同时是"实现真的在**查**、而不是在**导**"的证据 —— 如果实现写成
    ``import sherpa_onnx``，这里的 monkeypatch 根本拦不住它，断言就会失败。
    """
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: None)
    assert tts.dependency_ready() is False
    assert asr.dependency_ready() is False
    assert tts.model_available() is False
    assert asr.model_available() is False
