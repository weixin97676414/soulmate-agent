











from __future__ import annotations

import re
from datetime import date

from my_agent.agent.prompts import DEFAULT_SYSTEM_PROMPT, build_system_prompt


def test_prompt_contains_no_clock_time():





    text = build_system_prompt()
    matched = re.search(r"\d{1,2}:\d{2}", text)
    assert matched is None, (
        f"system 提示词里出现了时钟时间「{matched.group() if matched else ''}」。"
        "这会让整段前缀缓存每分钟失效一次，长会话输入成本一直按 full price 计费。"
        "需要精确时间请让模型调用 system_time 工具。"
    )


def test_prompt_is_byte_stable_across_calls():





    samples = {build_system_prompt() for _ in range(5)}
    assert len(samples) == 1, "同一时刻多次构造的结果不一致，前缀缓存无法命中"


def test_prompt_contains_today_and_weekday():

    text = build_system_prompt()
    assert date.today().strftime("%Y-%m-%d") in text
    assert "星期" in text


def test_prompt_points_model_to_system_time_skill():

    assert "system_time" in build_system_prompt()


def test_custom_prompt_replaces_default():

    text = build_system_prompt("你是一名只回答数字的数据分析师。")
    assert "你是一名只回答数字的数据分析师。" in text
    assert DEFAULT_SYSTEM_PROMPT not in text


def test_blank_custom_falls_back_to_default():

    for blank in ("", "   ", "\n\t "):
        assert DEFAULT_SYSTEM_PROMPT in build_system_prompt(blank)
