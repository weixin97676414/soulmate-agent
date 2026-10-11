"""服务商预设表（``routes/models.py::PRESETS``）与平台策略的**对应关系**。

本次把内置服务商从 4 家扩到 17 家，用户的原话是
"多增加一些主流服务商，我们也要能支持这些服务商模型的思考程度设置"。
所以这里钉的不是"加了几个名字"，而是**三件会静默出问题的事**：

1. **每家都得有平台策略**：没有策略的厂商会走"通用兜底"——温度按 0~1 夹、
   思考字段按 OpenAI 风格发。对一家其实要 `thinking` 对象的厂商，
   表现就是"档位设了没生效"（请求成功、回答正常，只有开关什么都没干）。
2. **新增的几家不许预填模型名**（用户明确要求）：写了不存在的模型名，
   用户照着选会撞"模型不存在"，而他不知道那行字是我们编的。
3. **思考字段必须能被自适应禁用**：厂商回 "Unknown parameter: 'thinking'" 时，
   只有在 `_ADAPTIVE_PARAMS` 里找得到这个名字才禁得掉 —— 找不到就是**硬报错**，
   而不是我们承诺的"档位静默失效、对话照常"。这条是最容易被漏掉的一环。
"""

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

#: 走**原生协议**的服务商（不用 OpenAI 兼容路径，因此不需要 PlatformProfile）
NATIVE_ADAPTER_PROVIDERS = {"anthropic"}

#: 本次新增/恢复的服务商 —— 它们的 `models` 必须留空（产品要求）
NEW_IN_BATCH = {
    "moonshot",
    "zhipu",
    "volcengine",
    "minimax",
    "hunyuan",
    "qianfan",
    "stepfun",
    "anthropic",
    "gemini",
    "xai",
    "openrouter",
    "groq",
    "mistral",
}

REQUIRED_KEYS = ("provider", "name", "base_url", "models", "docs", "apply_url", "token_limit")


def test_预设表本身是完整且不重复的():
    providers = [item["provider"] for item in PRESETS]
    assert len(providers) == len(set(providers)), f"provider 有重复：{providers}"
    # 展示名与地址也不能撞车：撞了界面会出现两个看起来一样、点起来不一样的条目
    assert len({item["name"] for item in PRESETS}) == len(PRESETS), "展示名有重复"
    assert len({item["base_url"] for item in PRESETS}) == len(PRESETS), "base_url 有重复"

    for item in PRESETS:
        missing = [key for key in REQUIRED_KEYS if key not in item]
        assert not missing, f"{item.get('provider')} 缺字段 {missing}"
        assert item["base_url"].startswith("https://"), f"{item['provider']} 的地址不是 https"
        # ⚠️ 申请 Key 的直达页也必须是 https 且非空：给空壳等于「获取 Key」按钮点了没反应
        assert item["docs"].startswith("https://"), f"{item['provider']} 的 docs 不是 https"
        assert item["apply_url"].startswith("https://"), f"{item['provider']} 的 apply_url 不是 https"
        assert item["token_limit"] > 0
        assert item["name"].strip(), f"{item['provider']} 没有展示名"
        assert isinstance(item["models"], list)


def test_每个_openai_兼容预设都命中一个平台策略():
    """漏配策略 = 温度被按通用区间夹、思考字段按 OpenAI 风格发（静默失效）。"""
    generic = []
    for item in PRESETS:
        if item["provider"] in NATIVE_ADAPTER_PROVIDERS:
            continue  # 原生协议不走 PlatformProfile（Anthropic 的翻译在适配器里）
        profile = detect_profile(item["base_url"])
        if profile is DEFAULT_PROFILE:
            generic.append(item["provider"])
    assert not generic, f"这些服务商没有平台策略，会走通用兜底：{generic}"


def test_新增的服务商不预填模型名():
    """产品要求：宁可他点一次「获取模型」，也不要预设里写错模型名。"""
    prefilled = [item["provider"] for item in PRESETS if item["provider"] in NEW_IN_BATCH and item["models"]]
    assert not prefilled, f"这些新增服务商不该预填模型：{prefilled}"


def test_老预设仍然带着模型快照():
    """反过来也要钉住：原有那 4 家的候选清单**不许**被顺手清空
    （没填 Key 时那是用户唯一能看到的候选）。"""
    by_provider = {item["provider"]: item for item in PRESETS}
    for provider in ("siliconflow", "deepseek", "openai", "dashscope"):
        assert by_provider[provider]["models"], f"{provider} 的模型快照被清空了"


def test_思考字段全都列进了自适应禁用名单():
    """⚠️ 这条是本次最要紧的不变式（少一个就是"厂商报未知参数 ⇒ 整条对话报错"）。"""
    missing = sorted(THINKING_FIELD_NAMES - set(_ADAPTIVE_PARAMS))
    assert not missing, f"这些思考字段不在 _ADAPTIVE_PARAMS 里，厂商拒绝时禁不掉：{missing}"

    # 逐条策略再核一遍：将来有人加新样式、忘了加字段名，会在这里红
    offenders: dict[str, list[str]] = {}
    for _hosts, profile in _PROFILES:
        for level in (*THINKING_LEVELS, None):
            for field in profile.thinking.payload_for(level):
                if field not in _ADAPTIVE_PARAMS:
                    offenders.setdefault(profile.name, []).append(field)
    assert not offenders, f"这些厂商会发出发不出去的字段：{offenders}"


def test_Anthropic_预设走原生适配器():
    anthropic = next(item for item in PRESETS if item["provider"] == "anthropic")
    assert anthropic.get("adapter") == "anthropic", "Claude 必须走原生协议，否则必然 404"
    # 只有它一家是原生的：别的家标错 adapter 会立刻连不上
    natives = [item["provider"] for item in PRESETS if item.get("adapter")]
    assert natives == ["anthropic"], f"原生适配器的服务商应当只有 anthropic，实际 {natives}"


@pytest.mark.parametrize(
    ("provider", "level", "expected"),
    [
        # 各家"思考强度"按官方文档该发什么 —— 这几条是对着 platform.py 的策略表核的
        ("openai", "high", {"reasoning_effort": "high"}),
        ("deepseek", "low", {"reasoning_effort": "low"}),
        ("groq", "medium", {"reasoning_effort": "medium"}),
        ("dashscope", "high", {"enable_thinking": True, "thinking_budget": 32768}),
        ("zhipu", "low", {"thinking": {"type": "disabled"}}),
        ("volcengine", "medium", {"thinking": {"type": "enabled"}}),
        ("openrouter", "high", {"reasoning": {"effort": "high"}}),
    ],
)
def test_思考档位映射符合各家写法(provider: str, level: str, expected: dict):
    item = next(entry for entry in PRESETS if entry["provider"] == provider)
    profile = detect_profile(item["base_url"])
    assert profile.thinking.payload_for(level) == expected


def test_档位为空时不发任何字段():
    """界面上的「关闭」就是这一档：一个字段都不许发（多数网关不认识它们）。"""
    for _hosts, profile in _PROFILES:
        assert profile.thinking.payload_for(None) == {}
        assert profile.thinking.payload_for("") == {}
