









from __future__ import annotations

import pytest

from my_agent.server.routes.voice import _find_wake_word, _pinyin_key

WORD = "你好搭子"


@pytest.mark.parametrize(
    "heard",
    [
        "你好搭子",  
        "你好，大子。",  
        "你好，达子！",
        "你好妲子",
        "你好，大紫。",  
        "你好搭子，帮我看看这个",  
    ],
)
def test_同音字与连读都要能唤醒(heard: str) -> None:
    assert _find_wake_word(heard, [WORD]) == WORD


@pytest.mark.parametrize(
    "heard",
    [
        "今天天气不错",
        "你好",  
        "大子",  
        "",
        "   ",
        "，。！？",
    ],
)
def test_无关内容不能误唤醒(heard: str) -> None:
    assert _find_wake_word(heard, [WORD]) is None


def test_拼音键不带声调() -> None:

    assert _pinyin_key("你好搭子") == _pinyin_key("你好，大子。") == "nihaodazi"


def test_英文唤醒词也能用() -> None:

    assert _find_wake_word("hey 搭子", ["hey搭子"]) == "hey搭子"
    assert _find_wake_word("over", ["over"]) == "over"


def test_多个唤醒词认最先匹配的那个() -> None:
    assert _find_wake_word("你好搭子", ["喂", WORD]) == WORD
    assert _find_wake_word("喂", ["喂", WORD]) == "喂"
