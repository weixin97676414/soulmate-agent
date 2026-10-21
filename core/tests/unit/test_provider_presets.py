























from __future__ import annotations

import pytest

from my_agent.llm.platform import (
    _ADAPTIVE_PARAMS,
    _PROFILES,
    DEFAULT_PROFILE,
    THINKING_FIELD_NAMES,
    THINKING_LEVELS,
    detect_profile,
)
from my_agent.server.routes.models import PRESETS


KEPT_PROVIDERS = ("siliconflow", "deepseek", "openai", "dashscope")

REQUIRED_KEYS = ("provider", "name", "base_url", "models", "docs", "apply_url", "token_limit")


def test_预设表本身是完整且不重复的():
    providers = [item["provider"] for item in PRESETS]
    assert len(providers) == len(set(providers)), f"provider 有重复：{providers}"
    
    assert len({item["name"] for item in PRESETS}) == len(PRESETS), "展示名有重复"
    assert len({item["base_url"] for item in PRESETS}) == len(PRESETS), "base_url 有重复"

    for item in PRESETS:
        missing = [key for key in REQUIRED_KEYS if key not in item]
        assert not missing, f"{item.get('provider')} 缺字段 {missing}"
        assert item["base_url"].startswith("https://"), f"{item['provider']} 的地址不是 https"
        
        assert item["docs"].startswith("https://"), f"{item['provider']} 的 docs 不是 https"
        assert item["apply_url"].startswith("https://"), f"{item['provider']} 的 apply_url 不是 https"
        assert item["token_limit"] > 0
        assert item["name"].strip(), f"{item['provider']} 没有展示名"
        assert isinstance(item["models"], list)


def test_只保留产品指定的那四家():





    assert tuple(item["provider"] for item in PRESETS) == KEPT_PROVIDERS


def test_每个_openai_兼容预设都命中一个平台策略():

    generic = []
    for item in PRESETS:
        
        
        if detect_profile(item["base_url"]) is DEFAULT_PROFILE:
            generic.append(item["provider"])
    assert not generic, f"这些服务商没有平台策略，会走通用兜底：{generic}"





REVERTED_SILICONFLOW_MODELS = (
    "deepseek-ai/DeepSeek-R1",
    "Qwen/Qwen3-VL-32B-Thinking",
    "Qwen/Qwen3-VL-30B-A3B-Thinking",
)


def test_硅基流动快照回到原口径且默认模型没被换掉():










    item = next(entry for entry in PRESETS if entry["provider"] == "siliconflow")
    came_back = [name for name in REVERTED_SILICONFLOW_MODELS if name in item["models"]]
    assert not came_back, f"已被推翻的模型又回到了硅基流动快照：{came_back}"
    assert item["models"][0] == "deepseek-v4-flash", (
        f"第一家（硅基流动）的默认模型被换成了 {item['models'][0]!r}："
        "新建服务商时会直接用它，别动这一项"
    )


def test_保留的预设都带着模型快照():





    by_provider = {item["provider"]: item for item in PRESETS}
    for provider in KEPT_PROVIDERS:
        assert by_provider[provider]["models"], f"{provider} 的模型快照被清空了"


def test_思考字段全都列进了自适应禁用名单():






    missing = sorted(THINKING_FIELD_NAMES - set(_ADAPTIVE_PARAMS))
    assert not missing, f"这些思考字段不在 _ADAPTIVE_PARAMS 里，厂商拒绝时禁不掉：{missing}"

    
    offenders: dict[str, list[str]] = {}
    for _hosts, profile in _PROFILES:
        for level in (*THINKING_LEVELS, None):
            for field in profile.thinking.payload_for(level):
                if field not in _ADAPTIVE_PARAMS:
                    offenders.setdefault(profile.name, []).append(field)
    assert not offenders, f"这些厂商会发出发不出去的字段：{offenders}"


@pytest.mark.parametrize(
    ("provider", "level", "expected"),
    [
        
        
        
        ("openai", "high", {"reasoning_effort": "high"}),
        ("deepseek", "low", {"reasoning_effort": "low"}),
        ("dashscope", "high", {"enable_thinking": True, "thinking_budget": 32768}),
    ],
)
def test_思考档位映射符合各家写法(provider: str, level: str, expected: dict):
    item = next(entry for entry in PRESETS if entry["provider"] == provider)
    profile = detect_profile(item["base_url"])
    assert profile.thinking.payload_for(level) == expected


def test_档位为空时不发任何字段():

    for _hosts, profile in _PROFILES:
        assert profile.thinking.payload_for(None) == {}
        assert profile.thinking.payload_for("") == {}
