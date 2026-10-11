"""回复正文段首时间戳净化的单测。

背景：发给模型的历史消息每条都带 `[MM-DD HH:MM] ` 前缀，模型模仿这个格式，
在每次工具调用之后的正文开头自己写时间戳，一条回复能刷出几十个。
这里钉住两层净化：非流式的整段剥离 + 流式的"扣住开头"剥离器。

## 为什么要有流式版

delta 逐字到来，单看 `[`、`09` 判断不了是不是时间戳开头。剥离器把段首
"还像时间戳"的字符扣住，能确定后一次吐出 —— 否则流式过程中时间戳会
闪现、定稿时又消失，观感比不修还差。
"""

from __future__ import annotations

from my_agent.agent.engine import _StampStripper, strip_timestamp_prefix


def test_strip_single_stamp() -> None:
    assert strip_timestamp_prefix("[09-28 18:00] 我写好了。") == "我写好了。"


def test_strip_chained_stamps() -> None:
    """模型会把时间戳连排（截图里就是 `[..][..]` 顶着正文）。"""
    assert (
        strip_timestamp_prefix("[09-28 18:00][09-28 18:01] 已更新档案。")
        == "已更新档案。"
    )


def test_strip_keeps_body_after_prefix() -> None:
    """只剥**段首**的：正文中间引用的时间戳一字不动。"""
    text = "09-28 那天我们聊过 [10-00 00:00] 这个写法。"
    assert strip_timestamp_prefix(text) == text


def test_strip_plain_text_untouched() -> None:
    assert strip_timestamp_prefix("普通回复，没有戳。") == "普通回复，没有戳。"


def test_stripper_holds_partial_stamp_in_stream() -> None:
    """流式：时间戳写到一半（"[09-2"）时必须扣住，不能让碎片闪现给用户。"""
    stripper = _StampStripper()
    assert stripper.feed("[") == ""
    assert stripper.feed("09-") == ""
    assert stripper.feed("28 18:") == ""
    assert stripper.feed("00] ") == ""
    # 完整时间戳剥完，后面的正文原样放行
    assert stripper.feed("写好了。") == "写好了。"


def test_stripper_flushes_trailing_half_stamp() -> None:
    """模型只发了半个时间戳就结束段落：flush 把扣住的字符还给正文。"""
    stripper = _StampStripper()
    assert stripper.feed("[09-2") == ""
    assert stripper.flush() == "[09-2"


def test_stripper_chained_stamps_across_deltas() -> None:
    stripper = _StampStripper()
    out = ""
    for delta in ("[09-28 18:00]", "[09-28 18:01] ", "开", "工。"):
        out += stripper.feed(delta)
    out += stripper.flush()
    assert out == "开工。"


def test_stripper_passes_non_stamp_bracket() -> None:
    """正文以 `[` 开头但不是时间戳（如 `[笔记]`）时要尽快放行，不吞字。"""
    stripper = _StampStripper()
    assert stripper.feed("[笔记] 开工。") == "[笔记] 开工。"


def test_stripper_handles_date_only_bracket() -> None:
    """`[2026` 这类日期开头不是我们要剥的形状：放行，不无限扣住。"""
    stripper = _StampStripper()
    out = stripper.feed("[2026 年总结]")
    assert out.startswith("[2026")
