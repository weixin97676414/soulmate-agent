"""思考强度（low/medium/high）到各厂商请求字段的映射。

## 这一组守的是什么

用户报的是"思考程度设置好像没有生效"。查下来链路是通的（前端每轮带 →
会话存库 → 引擎转发 → 适配器写进请求体），问题出在**最后一跳**：
我们一律按 OpenAI 的写法发 ``reasoning_effort``，而除 OpenAI 外的厂商
各有各的字段名，对不认识的字段是**静默忽略**的。

静默是这个 bug 里最难受的部分：请求成功、回答正常，只有那个开关什么都没干。
所以这里既测"字段发对了没"，也测"没生效时会不会说出来"。
"""

from __future__ import annotations

from typing import Any

import pytest

from my_agent.agent.engine import _thinking_no_effect_notice
from my_agent.llm.adapters.openai_compat import OpenAICompatAdapter
from my_agent.llm.base import BaseLLM, StreamChunk
from my_agent.llm.platform import (
    THINKING_LEVELS,
    ThinkingStrategy,
    detect_profile,
    reasoning_effort_style,
)


def _adapter(base_url: str = "https://api.example.com/v1") -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        base_url=base_url,
        api_key="sk-test",
        model_name="m",
    )


def _payload(adapter: OpenAICompatAdapter, effort: str | None) -> dict[str, Any]:
    return adapter._build_payload([], None, 0.7, None, stream=True, reasoning_effort=effort)


# --------------------------------------------------------------------------- #
# 默认（OpenAI 风格）
# --------------------------------------------------------------------------- #
def test_default_profile_uses_reasoning_effort() -> None:
    """未知网关按 OpenAI 写法走 —— 多数兼容网关都实现了它。"""
    payload = _payload(_adapter(), "high")

    assert payload["reasoning_effort"] == "high"


def test_no_effort_means_no_field_at_all() -> None:
    """没选档位就**一个字段都不发**（而不是发个默认值）。

    不接受的厂商收到默认值同样会 400 —— 问题在字段本身，不在取值。
    """
    assert "reasoning_effort" not in _payload(_adapter(), None)


def test_effort_is_skipped_when_model_does_not_support_reasoning() -> None:
    adapter = _adapter()
    adapter.supports_reasoning = False

    assert "reasoning_effort" not in _payload(adapter, "high")


# --------------------------------------------------------------------------- #
# 厂商差异（这一组就是"没生效"的根因）
# --------------------------------------------------------------------------- #
def test_dashscope_gets_enable_thinking_and_budget() -> None:
    """通义/DashScope 不认 reasoning_effort，它要的是布尔 + 预算 token 数。"""
    payload = _payload(_adapter("https://dashscope.aliyuncs.com/compatible-mode/v1"), "high")

    assert payload["enable_thinking"] is True
    assert payload["thinking_budget"] == 32768
    # 关键：不能再把 OpenAI 的字段也发过去（对方不认，纯属噪声）
    assert "reasoning_effort" not in payload


def test_zhipu_gets_thinking_object() -> None:
    payload = _payload(_adapter("https://open.bigmodel.cn/api/paas/v4"), "medium")

    assert payload["thinking"] == {"type": "enabled"}
    assert "reasoning_effort" not in payload


def test_zhipu_low_means_disabled() -> None:
    """智谱只有开关、没有档位：``low`` 映射成关闭。

    这是刻意的 —— 既然它表达不了"想一点"，"低"最接近的语义就是"不要多花这份预算"，
    而不是"假装开了但和 medium 完全一样"。
    """
    payload = _payload(_adapter("https://open.bigmodel.cn/api/paas/v4"), "low")

    assert payload["thinking"] == {"type": "disabled"}


def test_every_level_maps_to_something_for_known_vendors() -> None:
    """**每个档位都必须真的映射出字段**，不许有档位被静默丢掉。

    这条防的是"选了 high 但那一档在表里漏了"这种低级却难查的错 ——
    现象与"设置没生效"一模一样。
    """
    for url in (
        "https://api.openai.com/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://open.bigmodel.cn/api/paas/v4",
    ):
        profile = detect_profile(url)
        for level in THINKING_LEVELS:
            assert profile.thinking.supports(level), f"{profile.name} 缺少档位 {level}"
            assert profile.thinking.payload_for(level), f"{profile.name} 的 {level} 是空的"


# --------------------------------------------------------------------------- #
# 策略本身
# --------------------------------------------------------------------------- #
def test_strategy_returns_a_copy() -> None:
    """``payload_for`` 必须返回副本：调用方会往 payload 里塞东西，
    共享同一个 dict 会让"某一次请求的改动"漏进后续所有请求。"""
    strategy = reasoning_effort_style()

    first = strategy.payload_for("high")
    first["reasoning_effort"] = "被改掉了"

    assert strategy.payload_for("high")["reasoning_effort"] == "high"


def test_unknown_level_yields_nothing() -> None:
    assert ThinkingStrategy(kind="x", fields={}).payload_for("high") == {}
    assert reasoning_effort_style().payload_for("超高") == {}


# --------------------------------------------------------------------------- #
# 没生效时必须说出来
# --------------------------------------------------------------------------- #
def test_no_effect_notice_is_actionable_and_honest() -> None:
    """提示必须说清"回答不受影响"并给出各家的真实差异。

    不写"请到某某页面切换"这种我们做不到的话 —— 提示一个不存在的按钮
    比不提示更糟。
    """
    notice = _thinking_no_effect_notice()

    assert "不受影响" in notice
    assert "reasoning_effort" in notice
    assert "enable_thinking" in notice
    assert "thinking" in notice


class _StubLLM(BaseLLM):
    """按脚本吐流式分片的最小适配器。

    继承 ``BaseLLM`` 是为了拿到 ``leased_stream``（引擎走它）——
    手搓一个假对象的话会漏掉这些由基类提供的横切能力，
    测出来的东西和真实链路就不是一回事了。
    """

    def __init__(self, chunks: list[StreamChunk]) -> None:
        super().__init__(model_name="fake")
        self._chunks = chunks

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(self, *args: Any, **kwargs: Any) -> Any:
        for chunk in self._chunks:
            yield chunk


def _run_agent(chunks: list[StreamChunk], *, effort: str | None) -> list[Any]:
    from my_agent.agent.engine import Agent, AgentConfig
    from my_agent.memory.short_term import MemoryManager
    from my_agent.skill.base import SkillContext
    from my_agent.skill.manager import SkillManager

    agent = Agent(
        llm=_StubLLM(chunks),  # type: ignore[arg-type]
        skill_manager=SkillManager(),
        memory=MemoryManager(),
        config=AgentConfig(reasoning_effort=effort),
        ctx=SkillContext(),
    )
    return agent.run_stream("你好")


@pytest.mark.asyncio
async def test_engine_warns_when_effort_set_but_no_reasoning() -> None:
    """**核心回归**：设了档位、模型却没吐思考内容 → 必须发出一条 warning。

    对应"静默失效"：以前什么提示都没有，用户只能反复点那个开关，
    而请求是成功的、回答是正常的 —— 他没有任何办法判断是坏了还是本来如此。
    """
    events = [
        event
        async for event in _run_agent(
            [StreamChunk(delta="答案", finish_reason="stop", tool_calls=[])], effort="high"
        )
    ]

    warnings = [event for event in events if event.type == "warning"]
    assert len(warnings) == 1, "设了档位却没思考内容时必须发出一条可见提示"
    assert "思考强度" in warnings[0].data["message"]


@pytest.mark.asyncio
async def test_engine_stays_quiet_when_reasoning_arrived() -> None:
    """模型确实返回了思考内容 → 不该有任何提示（否则就是纯噪声）。"""
    events = [
        event
        async for event in _run_agent(
            [
                StreamChunk(reasoning_delta="我琢磨一下……"),
                StreamChunk(delta="答案", finish_reason="stop", tool_calls=[]),
            ],
            effort="high",
        )
    ]

    assert not [event for event in events if event.type == "warning"]
    assert [event for event in events if event.type == "reasoning"]


@pytest.mark.asyncio
async def test_engine_stays_quiet_when_no_effort_requested() -> None:
    """没选档位就什么都不说 —— 那时"没有思考内容"是完全正常的。"""
    events = [
        event
        async for event in _run_agent(
            [StreamChunk(delta="答案", finish_reason="stop", tool_calls=[])], effort=None
        )
    ]

    assert not [event for event in events if event.type == "warning"]
