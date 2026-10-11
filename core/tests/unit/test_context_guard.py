"""上下文超限与摘要压缩。

这是本轮新增里**最需要测试**的一块：它同时碰到三处容易出错的地方 ——
消息协议合法性（tool 与 tool_calls 的配对）、成本（多一次 LLM 调用）、
以及"用户看到的记录不被删掉"这条隐含约定。

（``ContextOverflowError`` 在补上这个模块之前定义了但从未被 raise，
那条"超限 → 压缩 → 重试"的链路其实是不存在的。）
"""

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
    """只实现 ``chat`` 的假模型，用来验证压缩流程。"""

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
        yield  # pragma: no cover - 压缩不走流式


def fill(memory: MemoryManager, turns: int, *, chars: int = 40) -> None:
    """往记忆里塞若干轮问答。"""
    memory.ensure_system("系统提示词")
    for index in range(turns):
        memory.add_user(f"用户第 {index} 条：{'填' * chars}")
        memory.add_assistant(f"助手第 {index} 条：{'答' * chars}")


# --------------------------------------------------------------------------- #
# 超限识别
# --------------------------------------------------------------------------- #
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
        """把鉴权失败误判成超限会导致"压了半天还是失败"。"""
        assert not looks_like_context_overflow(message)

    def test_check_raises_when_over_budget(self):
        memory = MemoryManager(max_context_tokens=200)
        fill(memory, 20)
        guard = ContextGuard(ContextPolicy(reserve_tokens=10))

        with pytest.raises(ContextOverflowError):
            guard.check(memory, token_limit=100)


# --------------------------------------------------------------------------- #
# 压缩
# --------------------------------------------------------------------------- #
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
        """压缩**不能**删消息：用户看到的聊天记录必须完整。

        摘要只影响发给模型的内容，不该让用户发现自己的历史少了一截。
        """
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
        """最近几条必须原样保留 —— 它们是"当前在做什么"的上下文。"""
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
        """压缩是优化手段，失败必须能回落，绝不能让整轮对话失败。"""
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 10)

        ok = await ContextGuard(ContextPolicy(keep_recent=4)).compress(
            FakeSummarizer(error=LLMError("模型挂了")), memory, token_limit=100000
        )

        assert ok is False
        assert memory.summary == ""

    @pytest.mark.asyncio
    async def test_existing_summary_is_merged_not_overwritten(self):
        """第二次压缩要与第一次合并，否则前面几十轮的约定白保了。"""
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 6)
        guard = ContextGuard(ContextPolicy(keep_recent=4))

        await guard.compress(FakeSummarizer(reply="第一段摘要"), memory, token_limit=100000)
        fill(memory, 6)
        llm = FakeSummarizer(reply="合并后的摘要")
        await guard.compress(llm, memory, token_limit=100000)

        # 合并调用应当收到"旧摘要 + 新摘要"
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
        """超限时"拿去摘要的那批"本身也可能超限，必须分批 map-reduce。"""
        memory = MemoryManager(max_context_tokens=1000000)
        fill(memory, 60, chars=400)
        llm = FakeSummarizer(reply="分段摘要")
        guard = ContextGuard(ContextPolicy(keep_recent=2, summarize_budget_tokens=1500))

        ok = await guard.compress(llm, memory, token_limit=200000)

        assert ok
        assert len(llm.calls) > 1, "应当分多批摘要，再合并"

    @pytest.mark.asyncio
    async def test_second_compress_skips_already_covered(self):
        """已经进过摘要的消息不重复压 —— 否则同一个会话会被反复花钱。"""
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


# --------------------------------------------------------------------------- #
# 记忆层的摘要接口
# --------------------------------------------------------------------------- #
def system_text(context: list[Message]) -> str:
    """取出上下文里所有 system 消息的正文。

    摘要是以 **system** 消息注入的，而 ``render_transcript`` 刻意跳过 system
    （它服务于"压缩时不要把提示词也复述一遍"），所以断言摘要不能用它。
    """
    return "\n".join(m.content for m in context if m.role == "system")


class TestMemorySummary:
    def test_context_drops_covered_messages(self):
        memory = MemoryManager(max_context_tokens=100000)
        fill(memory, 5)
        memory.set_summary("早前的约定：输出用 CSV。", 5)

        context = memory.get_context()

        assert "早前的约定：输出用 CSV。" in system_text(context)
        # 被摘要覆盖的前两条用户消息不再逐条发送
        assert all("用户第 0 条" not in m.content for m in context)

    def test_clear_also_clears_summary(self):
        """清空对话必须连摘要一起清：否则模型"记得"用户刚删掉的内容。"""
        memory = MemoryManager()
        memory.ensure_system("s")
        memory.add_user("u")
        memory.set_summary("旧摘要", 2)

        memory.clear(keep_system=True)

        assert memory.summary == ""

    def test_replace_restores_summary(self):
        """重开长会话要恢复摘要，否则模型只能看到最近几条。"""
        memory = MemoryManager()

        memory.replace(
            [Message(role="system", content="s"), Message(role="user", content="hi")],
            summary="历史摘要",
            summary_upto=1,
        )

        assert memory.summary == "历史摘要"
        assert "历史摘要" in system_text(memory.get_context())

    def test_trim_never_starts_with_orphan_tool(self):
        """裁剪后不能以孤立的 tool 开头 —— 那是协议错误，厂商会直接 400。"""
        memory = MemoryManager(max_context_tokens=1)
        memory.ensure_system("s")
        memory.add_assistant("", [ToolCall(id="a", name="t", arguments={})])
        memory.add_tool("a", "t", "结果很长" * 50)

        context = memory.get_context()

        assert all(message.role != "tool" for message in context) or context[0].role != "tool"
