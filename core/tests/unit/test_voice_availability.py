












from __future__ import annotations

import importlib.util

from my_agent.voice import asr, tts


def test_依赖在位时能如实报告():

    assert tts.dependency_ready() is True
    assert asr.dependency_ready() is True
    
    assert asr.dependency_ready() is tts.dependency_ready()


def test_缺依赖时一律报不可用(monkeypatch):





    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: None)
    assert tts.dependency_ready() is False
    assert asr.dependency_ready() is False
    assert tts.model_available() is False
    assert asr.model_available() is False
