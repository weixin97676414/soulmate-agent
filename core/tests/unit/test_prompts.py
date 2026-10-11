"""系统提示词的**缓存稳定性**回归测试。

这些用例存在的唯一目的：防止有人把时分秒加回 ``system`` 消息。

``system`` 位于消息序列的**第 0 位**，而所有主流厂商的 prompt caching 都是
**前缀匹配**（DeepSeek 磁盘缓存命中价约为未命中的 1/10，OpenAI 缓存输入约 5 折，
Anthropic 读约 1 折）。system 里出现任何按分钟变化的内容，都会让
「system + 全部历史消息」的缓存**整段失效** —— 而这是长会话里最大的一块输入成本。

如果将来有人觉得「把当前时间告诉模型更方便」而改回去，这些用例会失败。
"""

from __future__ import annotations

import re
from datetime import date

from my_agent.agent.prompts import DEFAULT_SYSTEM_PROMPT, build_system_prompt


def test_prompt_contains_no_clock_time():
    """**核心断言**：system 里不能出现 HH:MM。

    这是本项目最容易犯、代价最大的一个错误：时间戳在序列最前端，
    跨分钟就击穿整段前缀缓存。
    """
    text = build_system_prompt()
    matched = re.search(r"\d{1,2}:\d{2}", text)
    assert matched is None, (
        f"system 提示词里出现了时钟时间「{matched.group() if matched else ''}」。"
        "这会让整段前缀缓存每分钟失效一次，长会话输入成本一直按 full price 计费。"
        "需要精确时间请让模型调用 system_time 工具。"
    )


def test_prompt_is_byte_stable_across_calls():
    """同一天内多次构造必须逐字节一致。

    ``Agent.run_stream`` 每轮都会重新构造一次 system 提示词，
    只要有任何抖动，会话中间的那一轮就会把缓存打掉。
    """
    samples = {build_system_prompt() for _ in range(5)}
    assert len(samples) == 1, "同一时刻多次构造的结果不一致，前缀缓存无法命中"


def test_prompt_contains_today_and_weekday():
    """日期与星期仍然要注入，否则模型无法处理「明天」「本周」这类相对时间。"""
    text = build_system_prompt()
    assert date.today().strftime("%Y-%m-%d") in text
    assert "星期" in text


def test_prompt_points_model_to_system_time_skill():
    """既然不给精确时间，就必须告诉模型去哪里拿。"""
    assert "system_time" in build_system_prompt()


def test_custom_prompt_replaces_default():
    """助手自定义人设应当完全替换默认提示词。"""
    text = build_system_prompt("你是一名只回答数字的数据分析师。")
    assert "你是一名只回答数字的数据分析师。" in text
    assert DEFAULT_SYSTEM_PROMPT not in text


def test_blank_custom_falls_back_to_default():
    """空白人设要回落到默认，不能拼出一段空的 system。"""
    for blank in ("", "   ", "\n\t "):
        assert DEFAULT_SYSTEM_PROMPT in build_system_prompt(blank)
