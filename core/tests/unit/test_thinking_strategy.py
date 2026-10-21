












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





def test_default_profile_uses_reasoning_effort() -> None:

    payload = _payload(_adapter(), "high")

    assert payload["reasoning_effort"] == "high"


def test_no_effort_means_no_field_at_all() -> None:




    assert "reasoning_effort" not in _payload(_adapter(), None)


def test_effort_is_skipped_when_model_does_not_support_reasoning() -> None:
    adapter = _adapter()
    adapter.supports_reasoning = False

    assert "reasoning_effort" not in _payload(adapter, "high")





def test_dashscope_gets_enable_thinking_and_budget() -> None:

    payload = _payload(_adapter("https://dashscope.aliyuncs.com/compatible-mode/v1"), "high")

    assert payload["enable_thinking"] is True
    assert payload["thinking_budget"] == 32768
    
    assert "reasoning_effort" not in payload


def test_zhipu_gets_thinking_object() -> None:
    payload = _payload(_adapter("https://open.bigmodel.cn/api/paas/v4"), "medium")

    assert payload["thinking"] == {"type": "enabled"}
    assert "reasoning_effort" not in payload


def test_zhipu_low_means_disabled() -> None:





    payload = _payload(_adapter("https://open.bigmodel.cn/api/paas/v4"), "low")

    assert payload["thinking"] == {"type": "disabled"}


def test_every_level_maps_to_something_for_known_vendors() -> None:





    for url in (
        "https://api.openai.com/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://open.bigmodel.cn/api/paas/v4",
    ):
        profile = detect_profile(url)
        for level in THINKING_LEVELS:
            assert profile.thinking.supports(level), f"{profile.name} 缺少档位 {level}"
            assert profile.thinking.payload_for(level), f"{profile.name} 的 {level} 是空的"





def test_strategy_returns_a_copy() -> None:


    strategy = reasoning_effort_style()

    first = strategy.payload_for("high")
    first["reasoning_effort"] = "被改掉了"

    assert strategy.payload_for("high")["reasoning_effort"] == "high"


def test_unknown_level_yields_nothing() -> None:
    assert ThinkingStrategy(kind="x", fields={}).payload_for("high") == {}
    assert reasoning_effort_style().payload_for("超高") == {}





def test_no_effect_notice_is_actionable_and_honest() -> None:





    notice = _thinking_no_effect_notice()

    assert "不受影响" in notice
    assert "reasoning_effort" in notice
    assert "enable_thinking" in notice
    assert "thinking" in notice


class _StubLLM(BaseLLM):







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
        llm=_StubLLM(chunks),  
        skill_manager=SkillManager(),
        memory=MemoryManager(),
        config=AgentConfig(reasoning_effort=effort),
        ctx=SkillContext(),
    )
    return agent.run_stream("你好")


@pytest.mark.asyncio
async def test_engine_warns_when_effort_set_but_no_reasoning() -> None:





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

    events = [
        event
        async for event in _run_agent(
            [StreamChunk(delta="答案", finish_reason="stop", tool_calls=[])], effort=None
        )
    ]

    assert not [event for event in events if event.type == "warning"]
