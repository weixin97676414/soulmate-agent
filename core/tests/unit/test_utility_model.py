"""「压缩 / 规划 / 自检用哪个模型」这条设置的行为闸。

背景（用户要求）：这三件事各自要向模型**额外**发一次请求，而它们产出的都是
中间结果（摘要、计划、自检意见）。用户希望能把它们指到另一个模型上 ——
通常是更便宜的那个 —— 而不是一律用主对话模型。

这组用例守两件事：
1. 设置生效：辅助调用真的走了指定的模型，主模型没被拿去写摘要；
2. **配错不致命**：模型被删/停用后照旧能对话（退回主模型），而不是整轮报错。
"""

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
    """记录自己被问了几次的假模型。

    用 ``chat`` 的次数区分"谁写了摘要 / 计划 / 自检意见"：
    主对话走 ``stream``，辅助调用走 ``chat``，两者不会混。
    """

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
    """往记忆里塞若干轮问答（够长，能顶到压缩阈值）。"""
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


# --------------------------------------------------------------------------- #
# 解析设置
# --------------------------------------------------------------------------- #
class TestResolveUtilityLlm:
    def test_empty_means_follow_session_model(self):
        """没配（默认）就是老行为：跟随当前会话的模型。"""
        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "", fallback) is fallback

    def test_registered_model_wins(self):
        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "cheap", fallback) is registry.get("cheap")

    def test_deleted_model_falls_back_instead_of_raising(self):
        """用户删了那个便宜模型却没改这条设置 —— 不能因此整个回答发不出去。"""
        registry = registry_with("main", "cheap")
        fallback = registry.get("main")

        assert resolve_utility_llm(registry, "早就删掉的模型", fallback) is fallback


# --------------------------------------------------------------------------- #
# 引擎里三个辅助调用点
# --------------------------------------------------------------------------- #
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
            # 窗口压到很小，让首次循环就撞上压缩阈值
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
        """没注入 plan_decider 的路径（群聊 / 定时任务 / 命令行）行为不变。

        这是"计划模式只在单聊用"这道口径的闸：即便有人把 enable_planner 打开，
        没有确认通道的地方也不该突然弹计划卡片。
        """
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

        # 自检通过（答 "OK"）时不该产生需要修订的事件
        assert not any(event.type == "reflection" for event in events)
        assert cheap.chats, "自检应当走指定的辅助模型"
        assert not main.chats, "主模型不该被拿去做自检"

    @pytest.mark.asyncio
    async def test_default_keeps_session_model(self):
        """不传 utility_llm 时三个调用点仍用主模型 —— 保证老配置行为不变。"""
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
