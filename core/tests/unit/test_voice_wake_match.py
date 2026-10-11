"""唤醒词匹配：**按拼音比，不按字面比**。

这组用例的存在理由，是用户实测踩到的一个具体失败：
唤醒词「你好搭子」被识别成「你好，**大子**」，字面比较永远不中 ——
表现就是"喊四五次才醒一次"。

识别写同音错字是**常态**（它不会知道"搭子"是你要的自定义词），所以这层
拼音比较是唤醒能不能用的关键，值得钉死。
"""

from __future__ import annotations

import pytest

from my_agent.server.routes.voice import _find_wake_word, _pinyin_key

WORD = "你好搭子"


@pytest.mark.parametrize(
    "heard",
    [
        "你好搭子",  # 完全正确
        "你好，大子。",  # ← 用户实测截图里的原句
        "你好，达子！",
        "你好妲子",
        "你好，大紫。",  # 声母韵母都同音，只是字不同
        "你好搭子，帮我看看这个",  # 唤醒词与正文连着说（很自然的说法）
    ],
)
def test_同音字与连读都要能唤醒(heard: str) -> None:
    assert _find_wake_word(heard, [WORD]) == WORD


@pytest.mark.parametrize(
    "heard",
    [
        "今天天气不错",
        "你好",  # 只说了一半
        "大子",  # 只说了一半
        "",
        "   ",
        "，。！？",
    ],
)
def test_无关内容不能误唤醒(heard: str) -> None:
    assert _find_wake_word(heard, [WORD]) is None


def test_拼音键不带声调() -> None:
    """带声调的话「搭」(dā) 与「大」(dà) 就分开了 —— 而声调恰恰是识别最不准的一维。"""
    assert _pinyin_key("你好搭子") == _pinyin_key("你好，大子。") == "nihaodazi"


def test_英文唤醒词也能用() -> None:
    """混排与纯英文都要支持（有人习惯喊 over / hey）。"""
    assert _find_wake_word("hey 搭子", ["hey搭子"]) == "hey搭子"
    assert _find_wake_word("over", ["over"]) == "over"


def test_多个唤醒词认最先匹配的那个() -> None:
    assert _find_wake_word("你好搭子", ["喂", WORD]) == WORD
    assert _find_wake_word("喂", ["喂", WORD]) == "喂"
