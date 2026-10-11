"""用量归一化与费用估算。

锁住的核心事实：**各家厂商的 usage 字段名不一样，而「缓存命中量」必须被
单独识别出来**。识别错了，费用估算会差一个数量级；识别不到，就永远无法
验证「前缀缓存优化是否真的生效」——那是本项目最大的一块成本优化。
"""

from __future__ import annotations

import pytest

from my_agent.llm.usage import PriceSpec, Usage, estimate_cost, normalize_usage


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
def test_deepseek_cache_fields():
    """DeepSeek 的命中量在 prompt_cache_hit_tokens。"""
    usage = normalize_usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "prompt_cache_hit_tokens": 800,
            "prompt_cache_miss_tokens": 200,
        }
    )
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 100
    assert usage.cached_tokens == 800
    assert usage.hit_rate == pytest.approx(0.8)
    # 未命中部分按原价计费，不能把 1000 全按原价算
    assert usage.billable_input_tokens == 200


def test_openai_nested_cache_fields():
    """OpenAI 的命中量藏在 prompt_tokens_details.cached_tokens。"""
    usage = normalize_usage(
        {
            "prompt_tokens": 2000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 1536},
        }
    )
    assert usage.cached_tokens == 1536
    assert usage.billable_input_tokens == 464


def test_anthropic_style_fields():
    """Anthropic 用 input/output_tokens，并且有独立的缓存写入量。"""
    usage = normalize_usage(
        {
            "input_tokens": 500,
            "output_tokens": 20,
            "cache_read_input_tokens": 400,
            "cache_creation_input_tokens": 300,
        }
    )
    assert usage.prompt_tokens == 500
    assert usage.completion_tokens == 20
    assert usage.cached_tokens == 400
    assert usage.cache_write_tokens == 300


def test_no_cache_fields_means_zero_not_none():
    """完全不支持缓存的端点：命中量是 0，而不是"未知"。"""
    usage = normalize_usage({"prompt_tokens": 100, "completion_tokens": 10})
    assert usage.cached_tokens == 0
    assert usage.hit_rate == pytest.approx(0.0)


def test_hit_rate_is_none_without_input_tokens():
    """没有输入 token 时命中率返回 None 而不是 0，避免界面显示"命中率 0%"误导。"""
    assert normalize_usage({"completion_tokens": 10}).hit_rate is None
    assert normalize_usage(None).hit_rate is None


def test_cached_tokens_cannot_exceed_prompt():
    """命中量不可能超过输入总量。

    某些网关在流式末帧会把两者都报一遍，不加这道限制会算出
    「命中率 180%」这种一眼假的数据，用户会直接不再信任整个统计。
    """
    usage = normalize_usage({"prompt_tokens": 100, "prompt_cache_hit_tokens": 180})
    assert usage.cached_tokens == 100
    assert usage.hit_rate == pytest.approx(1.0)


def test_garbage_values_do_not_break_pipeline():
    """厂商偶尔回字符串或 null，统计链路不能因此炸掉。"""
    usage = normalize_usage(
        {
            "prompt_tokens": "120",
            "completion_tokens": None,
            "prompt_cache_hit_tokens": "abc",
        }
    )
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 0
    assert usage.cached_tokens == 0


def test_empty_usage_is_detected():
    assert normalize_usage({}).is_empty
    assert normalize_usage(None).is_empty
    assert not normalize_usage({"prompt_tokens": 1}).is_empty


def test_usage_accumulates_across_turns():
    """一次对话有多轮模型调用，用量要能累加。"""
    total = Usage()
    total.add(normalize_usage({"prompt_tokens": 100, "completion_tokens": 10,
                               "prompt_cache_hit_tokens": 60}))
    total.add(normalize_usage({"prompt_tokens": 200, "completion_tokens": 20,
                               "prompt_cache_hit_tokens": 150}))
    assert total.prompt_tokens == 300
    assert total.completion_tokens == 30
    assert total.cached_tokens == 210
    assert total.total_tokens == 330


# --------------------------------------------------------------------------- #
# 费用估算
# --------------------------------------------------------------------------- #
def test_cost_is_none_when_prices_missing():
    """没配价格就返回 None。

    **这是刻意的**：厂商调价频繁，拿一份猜的价钱算出「¥0.03」显示给用户，
    比显示「未配置价格」糟糕得多——用户看到金额就会当真。
    """
    usage = normalize_usage({"prompt_tokens": 1000, "completion_tokens": 100})
    assert estimate_cost(usage, PriceSpec()) is None
    assert estimate_cost(usage, PriceSpec(input=1.0)) is None
    assert estimate_cost(usage, PriceSpec(output=1.0)) is None


def test_cost_uses_cache_discount():
    """命中部分必须按更低的单价算，否则缓存优化在账面上体现不出来。"""
    usage = normalize_usage(
        {"prompt_tokens": 1_000_000, "completion_tokens": 0, "prompt_cache_hit_tokens": 1_000_000}
    )
    full = estimate_cost(usage, PriceSpec(input=10.0, output=10.0, cached_input=10.0))
    discounted = estimate_cost(usage, PriceSpec(input=10.0, output=10.0, cached_input=1.0))
    assert full == pytest.approx(10.0)
    assert discounted == pytest.approx(1.0)


def test_cost_without_cached_price_is_conservative():
    """cached_input 留空时**不打折**（按未命中价算）。

    宁可高估也不要低估：猜一个折扣会算出比实际更少的钱，
    用户可能因此超出预算而毫无察觉。
    """
    usage = normalize_usage(
        {"prompt_tokens": 1_000_000, "completion_tokens": 0, "prompt_cache_hit_tokens": 1_000_000}
    )
    assert estimate_cost(usage, PriceSpec(input=10.0, output=10.0)) == pytest.approx(10.0)


def test_cost_splits_input_and_output():
    usage = normalize_usage({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    # 输入 2 元 + 输出 8 元
    cost = estimate_cost(usage, PriceSpec(input=2.0, output=8.0))
    assert cost == pytest.approx(10.0)


def test_cost_keeps_small_amounts_visible():
    """单次对话常常只有几分钱，四舍五入到 2 位会全变成 0.00。"""
    usage = normalize_usage({"prompt_tokens": 500, "completion_tokens": 100})
    cost = estimate_cost(usage, PriceSpec(input=1.0, output=2.0))
    assert cost is not None
    assert cost > 0
