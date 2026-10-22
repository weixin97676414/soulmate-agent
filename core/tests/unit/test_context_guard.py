









from __future__ import annotations

import pytest

from my_agent.agent.context import (
    ContextGuard,
    ContextPolicy,
    looks_like_context_overflow,
    render_transcript,
)
from my_agent.errors import ContextOverflowError, LLMError
from my_agent.llm.base import BaseLLM, LLMResponse, Message, ToolCall
from my_agent.memory.short_term import MemoryManager


class FakeSummarizer(BaseLLM):


    def __init__(self, *, reply: str = "摘要", error: BaseException | None = None) -> None:
        super().__init__(model_name="summarizer", supports_tools=False)
        self.reply = reply
        self.error = error
        self.calls: list[str] = []

    async def chat(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        self.calls.append(messages[-1].content)
        if self.error is not None:
            raise self.error
        return LLMResponse(content=self.reply, finish_reason="stop")

    async def stream(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        yield  


def fill(memory: MemoryManager, turns: int, *, chars: int = 40) -> None:

    memory.ensure_system("系统提示词")
    for index in range(turns):
        memory.add_user(f"用户第 {index} 条：{'填' * chars}")
        memory.add_assistant(f"助手第 {index} 条：{'答' * chars}")





class TestOverflowDetection:
    @pytest.mark.parametrize(
        "message",
        [
            "This model's maximum context length is 32768 tokens",
            "The input is too long for this model",
            "Please reduce the length of the messages",
            "context_length_exceeded",
            "too many tokens in request",
        ],
    )
    def test_recognizes_vendor_wording(self, message: str):
        assert looks_like_context_overflow(message)

    @pytest.mark.parametrize(
        "message",
        [
            "Invalid API key",
            "Rate limit reached",
            "The model does not exist",
        ],
    )
    def test_does_not_misread_other_errors(self, message: str):

        assert not looks_like_context_overflow(message)

    def test_check_raises_when_over_budget(self):
        memory = MemoryManager(max_context_tokens=200)
        fill(memory, 20)
        guard = ContextGuard(ContextPolicy(reserve_tokens=10))

        with pytest.raises(ContextOverflowError):
            guard.check(memory, token_limit=100)





class TestCompress:
    @pytest.mark.asyncio
    async def test_summary_is_recorded_and_advances(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)
        guard = ContextGuard(ContextPolicy(keep_recent=4))
        llm = FakeSummarizer(reply="用户问了十件事，助手逐条回答了。")

        ok = await guard.compress(llm, memory, token_limit=100000)

        assert ok
        assert memory.summary == "用户问了十件事，助手逐条回答了。"
        assert 0 < memory.summary_upto < len(memory.messages)

    @pytest.mark.asyncio
    async def test_messages_are_not_deleted(self):




        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)
        before = len(memory.messages)

        await ContextGuard(ContextPolicy(keep_recent=4)).compress(
            FakeSummarizer(), memory, token_limit=100000
        )

        assert len(memory.messages) == before

    @pytest.mark.asyncio
    async def test_context_shrinks_after_compression(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 30)
        guard = ContextGuard(ContextPolicy(keep_recent=4))
        before = memory.context_tokens()

        await guard.compress(FakeSummarizer(reply="很短"), memory, token_limit=100000)

        assert memory.context_tokens() < before

    @pytest.mark.asyncio
    async def test_recent_messages_survive(self):

        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)
        memory.add_user("最后一条用户消息")

        await ContextGuard(ContextPolicy(keep_recent=6)).compress(
            FakeSummarizer(), memory, token_limit=100000
        )

        rendered = render_transcript(memory.get_context())
        assert "最后一条用户消息" in rendered

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_without_raising(self):

        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)

        ok = await ContextGuard(ContextPolicy(keep_recent=4)).compress(
            FakeSummarizer(error=LLMError("模型挂了")), memory, token_limit=100000
        )

        assert ok is False
        assert memory.summary == ""

    @pytest.mark.asyncio
    async def test_existing_summary_is_merged_not_overwritten(self):

        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 6)
        guard = ContextGuard(ContextPolicy(keep_recent=4))

        await guard.compress(FakeSummarizer(reply="第一段摘要"), memory, token_limit=100000)
        fill(memory, 6)
        llm = FakeSummarizer(reply="合并后的摘要")
        await guard.compress(llm, memory, token_limit=100000)

        
        assert "第一段摘要" in llm.calls[-1]
        assert memory.summary == "合并后的摘要"

    @pytest.mark.asyncio
    async def test_nothing_to_compress_returns_false(self):
        memory = MemoryManager(max_context_tokens=100000)
        memory.ensure_system("系统提示词")
        memory.add_user("只有一条")

        ok = await ContextGuard(ContextPolicy(keep_recent=6)).compress(
            FakeSummarizer(), memory, token_limit=100000
        )

        assert ok is False

    @pytest.mark.asyncio
    async def test_large_history_is_batched(self):

        memory = MemoryManager(max_context_tokens=1000000)
        fill(memory, 60, chars=400)
        llm = FakeSummarizer(reply="分段摘要")
        guard = ContextGuard(ContextPolicy(keep_recent=2, summarize_budget_tokens=1500))

        ok = await guard.compress(llm, memory, token_limit=200000)

        assert ok
        assert len(llm.calls) > 1, "应当分多批摘要，再合并"

    @pytest.mark.asyncio
    async def test_second_compress_skips_already_covered(self):

        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)
        guard = ContextGuard(ContextPolicy(keep_recent=4))
        await guard.compress(FakeSummarizer(reply="第一段"), memory, token_limit=100000)
        covered = memory.summary_upto

        start, _ = memory.compressible_range(keep_recent=4)

        assert start >= covered


class TestCompressibleRange:
    def test_range_leaves_recent_untouched(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)
        start, end = memory.compressible_range(keep_recent=4)

        assert start == 1, "system 不参与压缩"
        assert end == len(memory.messages) - 4

    def test_empty_when_history_is_short(self):
        memory = MemoryManager()
        memory.ensure_system("s")
        memory.add_user("u")
        start, end = memory.compressible_range(keep_recent=6)

        assert start == end





def system_text(context: list[Message]) -> str:





    return "\n".join(m.content for m in context if m.role == "system")


class TestMemorySummary:
    def test_context_drops_covered_messages(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 5)
        memory.set_summary("早前的约定：输出用 CSV。", 5)

        context = memory.get_context()

        assert "早前的约定：输出用 CSV。" in system_text(context)
        
        assert all("用户第 0 条" not in m.content for m in context)

    def test_clear_also_clears_summary(self):

        memory = MemoryManager()
        memory.ensure_system("s")
        memory.add_user("u")
        memory.set_summary("旧摘要", 2)

        memory.clear(keep_system=True)

        assert memory.summary == ""

    def test_replace_restores_summary(self):

        memory = MemoryManager()

        memory.replace(
            [Message(role="system", content="s"), Message(role="user", content="hi")],
            summary="历史摘要",
            summary_upto=1,
        )

        assert memory.summary == "历史摘要"
        assert "历史摘要" in system_text(memory.get_context())

    def test_trim_never_starts_with_orphan_tool(self):

        memory = MemoryManager(max_context_tokens=1)
        memory.ensure_system("s")
        memory.add_assistant("", [ToolCall(id="a", name="t", arguments={})])
        memory.add_tool("a", "t", "结果很长" * 50)

        context = memory.get_context()

        assert all(message.role != "tool" for message in context) or context[0].role != "tool"
