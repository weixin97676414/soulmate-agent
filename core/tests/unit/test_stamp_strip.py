












from __future__ import annotations

from my_agent.agent.engine import _StampStripper, strip_timestamp_prefix


def test_strip_single_stamp() -> None:
    assert strip_timestamp_prefix("[09-28 18:00] 我写好了。") == "我写好了。"


def test_strip_chained_stamps() -> None:

    assert (
        strip_timestamp_prefix("[09-28 18:00][09-28 18:01] 已更新档案。")
        == "已更新档案。"
    )


def test_strip_keeps_body_after_prefix() -> None:

    text = "09-28 那天我们聊过 [10-00 00:00] 这个写法。"
    assert strip_timestamp_prefix(text) == text


def test_strip_plain_text_untouched() -> None:
    assert strip_timestamp_prefix("普通回复，没有戳。") == "普通回复，没有戳。"


def test_stripper_holds_partial_stamp_in_stream() -> None:

    stripper = _StampStripper()
    assert stripper.feed("[") == ""
    assert stripper.feed("09-") == ""
    assert stripper.feed("28 18:") == ""
    assert stripper.feed("00] ") == ""
    
    assert stripper.feed("写好了。") == "写好了。"


def test_stripper_flushes_trailing_half_stamp() -> None:

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

    stripper = _StampStripper()
    assert stripper.feed("[笔记] 开工。") == "[笔记] 开工。"


def test_stripper_handles_date_only_bracket() -> None:

    stripper = _StampStripper()
    out = stripper.feed("[2026 年总结]")
    assert out.startswith("[2026")
