





from __future__ import annotations

import pytest

from my_agent.agent.group_discussion import _GROUP_KEEP_RECENT, compressed_group_history_text


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, token_limit: int = 5000, fail: bool = False) -> None:
        self.token_limit = token_limit
        self.fail = fail
        self.calls = 0

    async def chat(self, messages, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("模拟摘要失败")
        return _Resp("【这是更早讨论的摘要】")


class _FakeRuntime:
    def __init__(self) -> None:
        self._group_history_summary: dict[tuple[str, str], str] = {}


class _FakeGroup:
    id = "g1"


def _history(n: int, chars: int = 200) -> list[dict[str, str]]:
    return [
        {"role": "assistant", "name": f"搭子{i}", "content": f"第{i}条发言" + "内容" * chars, "at": "2026-10-22T10:00:00"}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_短历史直接拼原文不调摘要() -> None:
    runtime = _FakeRuntime()
    llm = _FakeLLM()
    history = _history(3, chars=2)

    text = await compressed_group_history_text(runtime, _FakeGroup(), "t1", history, llm, token_limit=llm.token_limit)

    assert llm.calls == 0, "没超阈值时不该花一次 LLM 调用"
    assert "第0条发言" in text and "第2条发言" in text, "原文应完整保留"


@pytest.mark.asyncio
async def test_超阈值摘要早期并保留最近() -> None:
    runtime = _FakeRuntime()
    llm = _FakeLLM()
    history = _history(50, chars=100)  

    text = await compressed_group_history_text(runtime, _FakeGroup(), "t1", history, llm, token_limit=llm.token_limit)

    assert llm.calls == 1
    assert "【这是更早讨论的摘要】" in text, "早期历史应被摘要替代"
    assert "第49条发言" in text, "最近一条原文必须保留"
    assert "第0条发言" not in text, "最早一条应已进入摘要、不再原文保留"
    assert ("g1", "t1") in runtime._group_history_summary, "摘要应写入缓存"


@pytest.mark.asyncio
async def test_摘要失败回落只保留最近() -> None:
    runtime = _FakeRuntime()
    llm = _FakeLLM(fail=True)
    history = _history(50, chars=100)

    text = await compressed_group_history_text(runtime, _FakeGroup(), "t1", history, llm, token_limit=llm.token_limit)

    assert "【这是更早讨论的摘要】" not in text, "摘要失败就不该有摘要"
    assert "第49条发言" in text, "最近一条原文必须保留"
    
    assert f"第{50 - _GROUP_KEEP_RECENT - 1}条发言" not in text


@pytest.mark.asyncio
async def test_缓存命中不重复调摘要() -> None:
    runtime = _FakeRuntime()
    llm = _FakeLLM()
    history = _history(50, chars=100)

    await compressed_group_history_text(runtime, _FakeGroup(), "t1", history, llm, token_limit=llm.token_limit)
    first_calls = llm.calls
    assert first_calls == 1

    await compressed_group_history_text(runtime, _FakeGroup(), "t1", history, llm, token_limit=llm.token_limit)
    assert llm.calls == first_calls, "同一段历史有缓存就不该再调一次摘要"
