










from __future__ import annotations

import pytest

from my_agent.agent.context import ContextPolicy
from my_agent.agent.engine import Agent, AgentConfig
from my_agent.llm.base import BaseLLM, LLMResponse, StreamChunk
from my_agent.llm.factory import resolve_utility_llm
from my_agent.llm.registry import LlmRegistry
from my_agent.memory.short_term import MemoryManager
from my_agent.skill.base import SkillContext
from my_agent.skill.manager import SkillManager


class RecordingLLM(BaseLLM):






    def __init__(
        self,
        name: str,
        *,
        reply: str = "（摘要）",
        answer: str = "好的。",
        supports_tools: bool = False,
    ) -> None:
        super().__init__(model_name=name, supports_tools=supports_tools)
        self.reply = reply
        self.answer = answer
        self.chats: list[str] = []
        self.streams = 0

    async def chat(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        self.chats.append(messages[-1].content)
        return LLMResponse(content=self.reply, finish_reason="stop")

    async def stream(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        self.streams += 1
        yield StreamChunk(delta=self.answer)
        yield StreamChunk(finish_reason="stop")


def fill(memory: MemoryManager, turns: int, *, chars: int = 200) -> None:

    memory.ensure_system("系统提示词")
    for index in range(turns):
        memory.add_user(f"用户第 {index} 条：{'填' * chars}")
        memory.add_assistant(f"助手第 {index} 条：{'答' * chars}")


def make_agent(
    main: BaseLLM,
    *,
    utility: BaseLLM | None = None,
    memory: MemoryManager | None = None,
    **config_kwargs,
) -> Agent:
    return Agent(
        llm=main,
        utility_llm=utility,
        skill_manager=SkillManager(),
        memory=memory or MemoryManager(),
        config=AgentConfig(**config_kwargs),
        ctx=SkillContext(session_id="test"),
    )


def registry_with(*ids: str) -> LlmRegistry:
    registry = LlmRegistry()
    for model_id in ids:
        registry.register(model_id, RecordingLLM(model_id))
    return registry





class TestResolveUtilityLlm:
    def test_empty_means_follow_session_model(self):

        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "", fallback) is fallback

    def test_registered_model_wins(self):
        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "cheap", fallback) is registry.get("cheap")

    def test_deleted_model_falls_back_instead_of_raising(self):

        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "早就删掉的模型", fallback) is fallback





class TestEngineUsesUtilityModel:
    @pytest.mark.asyncio
    async def test_compression_uses_utility_model(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 40)
        main = RecordingLLM("main")
        cheap = RecordingLLM("cheap", reply="（压缩后的摘要）")
        agent = make_agent(
            main,
            utility=cheap,
            memory=memory,
            
            token_limit=2000,
            context_policy=ContextPolicy(keep_recent=4, compress_threshold=0.5),
        )

        events = [event async for event in agent.run_stream("继续")]

        assert any(event.type == "context_compressed" for event in events), "应当压缩过一次"
        assert cheap.chats, "压缩应当走指定的辅助模型"
        assert not main.chats, "主模型不该被拿去写摘要"

    @pytest.mark.asyncio
    async def test_planner_uses_utility_model(self):
        main = RecordingLLM("main", supports_tools=True)
        cheap = RecordingLLM("cheap", reply="1. 先查数据\n2. 再整理表格")

        async def approve(_plan: dict) -> tuple[bool, str]:
            return True, ""

        agent = make_agent(main, utility=cheap, enable_planner=True, plan_decider=approve)

        events = [
            event
            async for event in agent.run_stream(
                "帮我做一份月度报告，然后整理成表格，再分别导出对比"
            )
        ]

        assert any(event.type == "plan" for event in events), "这个任务应当触发规划"
        assert cheap.chats, "规划应当走指定的辅助模型"
        assert not main.chats, "主模型不该被拿去做规划"

    @pytest.mark.asyncio
    async def test_no_plan_without_decider(self):





        main = RecordingLLM("main", supports_tools=True)
        cheap = RecordingLLM("cheap", reply="1. 先查数据\n2. 再整理表格")
        agent = make_agent(main, utility=cheap, enable_planner=True)

        events = [
            event
            async for event in agent.run_stream(
                "帮我做一份月度报告，然后整理成表格，再分别导出对比"
            )
        ]

        assert not any(event.type == "plan" for event in events)
        assert not cheap.chats, "没有确认通道时不该白白多花一次规划调用"

    @pytest.mark.asyncio
    async def test_reflection_uses_utility_model(self):
        long_answer = "这是本轮回答的正文。" * 8
        main = RecordingLLM("main", answer=long_answer)
        cheap = RecordingLLM("cheap", reply="OK")
        agent = make_agent(main, utility=cheap, enable_reflection=True, reflection_rounds=1)

        events = [event async for event in agent.run_stream("帮我核对一下这份清单")]

        
        assert not any(event.type == "reflection" for event in events)
        assert cheap.chats, "自检应当走指定的辅助模型"
        assert not main.chats, "主模型不该被拿去做自检"

    @pytest.mark.asyncio
    async def test_default_keeps_session_model(self):

        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 40)
        main = RecordingLLM("main")
        agent = make_agent(
            main,
            memory=memory,
            token_limit=2000,
            context_policy=ContextPolicy(keep_recent=4, compress_threshold=0.5),
        )

        assert agent.utility_llm is main

        events = [event async for event in agent.run_stream("继续")]

        assert any(event.type == "context_compressed" for event in events)
        assert main.chats, "没有指定辅助模型时，压缩仍应走主模型"
