






from __future__ import annotations

import pytest

from my_agent.llm.usage import PriceSpec, Usage, estimate_cost, normalize_usage





def test_deepseek_cache_fields():

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
    
    assert usage.billable_input_tokens == 200


def test_openai_nested_cache_fields():

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

    usage = normalize_usage({"prompt_tokens": 100, "completion_tokens": 10})
    assert usage.cached_tokens == 0
    assert usage.hit_rate == pytest.approx(0.0)


def test_hit_rate_is_none_without_input_tokens():

    assert normalize_usage({"completion_tokens": 10}).hit_rate is None
    assert normalize_usage(None).hit_rate is None


def test_cached_tokens_cannot_exceed_prompt():





    usage = normalize_usage({"prompt_tokens": 100, "prompt_cache_hit_tokens": 180})
    assert usage.cached_tokens == 100
    assert usage.hit_rate == pytest.approx(1.0)


def test_garbage_values_do_not_break_pipeline():

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

    total = Usage()
    total.add(normalize_usage({"prompt_tokens": 100, "completion_tokens": 10,
                               "prompt_cache_hit_tokens": 60}))
    total.add(normalize_usage({"prompt_tokens": 200, "completion_tokens": 20,
                               "prompt_cache_hit_tokens": 150}))
    assert total.prompt_tokens == 300
    assert total.completion_tokens == 30
    assert total.cached_tokens == 210
    assert total.total_tokens == 330





def test_cost_is_none_when_prices_missing():





    usage = normalize_usage({"prompt_tokens": 1000, "completion_tokens": 100})
    assert estimate_cost(usage, PriceSpec()) is None
    assert estimate_cost(usage, PriceSpec(input=1.0)) is None
    assert estimate_cost(usage, PriceSpec(output=1.0)) is None


def test_cost_uses_cache_discount():

    usage = normalize_usage(
        {"prompt_tokens": 1_000_000, "completion_tokens": 0, "prompt_cache_hit_tokens": 1_000_000}
    )
    full = estimate_cost(usage, PriceSpec(input=10.0, output=10.0, cached_input=10.0))
    discounted = estimate_cost(usage, PriceSpec(input=10.0, output=10.0, cached_input=1.0))
    assert full == pytest.approx(10.0)
    assert discounted == pytest.approx(1.0)


def test_cost_without_cached_price_is_conservative():





    usage = normalize_usage(
        {"prompt_tokens": 1_000_000, "completion_tokens": 0, "prompt_cache_hit_tokens": 1_000_000}
    )
    assert estimate_cost(usage, PriceSpec(input=10.0, output=10.0)) == pytest.approx(10.0)


def test_cost_splits_input_and_output():
    usage = normalize_usage({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    
    cost = estimate_cost(usage, PriceSpec(input=2.0, output=8.0))
    assert cost == pytest.approx(10.0)


def test_cost_keeps_small_amounts_visible():

    usage = normalize_usage({"prompt_tokens": 500, "completion_tokens": 100})
    cost = estimate_cost(usage, PriceSpec(input=1.0, output=2.0))
    assert cost is not None
    assert cost > 0
