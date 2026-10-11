"""注册表租约：**正在进行的流式回答不能被"改配置"打断**。

## 这一组守的是什么

用户报的现象："搭子工作当中，切出去，还是会被打断，报错：模型流式调用网络异常。"

根因不在"切页面"本身，而在**切页面会触发一次自动保存**（``PUT /v1/models``
→ ``runtime.reload_models()``），而那次保存会把旧注册表连同里面所有适配器的
httpx 客户端一起 ``aclose()`` —— 正在跑的那条流当场断掉。

所以这组测试的核心是一条不变量：
**只要还有请求在用旧注册表，就不能关它。**
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from my_agent.agent import engine as engine_mod
from my_agent.llm.base import BaseLLM, StreamChunk
from my_agent.llm.registry import LlmRegistry
from my_agent.server import runtime as runtime_mod


class _FakeLLM(BaseLLM):
    """能流式吐几段文字、并记录自己有没有被关掉的假适配器。"""

    def __init__(self, chunks: list[str] | None = None) -> None:
        super().__init__(model_name="fake")
        self.closed = False
        self._chunks = chunks if chunks is not None else ["a", "b", "c"]

    async def chat(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(
        self, messages: Any, tools: Any = None, **kwargs: Any
    ) -> Any:
        for text in self._chunks:
            yield StreamChunk(delta=text)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_retire_waits_for_inflight_stream() -> None:
    """**核心回归**：流跑到一半时 retire，流必须能完整跑完。"""
    registry = LlmRegistry()
    llm = _FakeLLM(["你", "好", "呀"])
    registry.register("m1", llm, is_default=True)

    seen: list[str] = []
    async for chunk in llm.leased_stream([]):
        seen.append(chunk.delta or "")
        if len(seen) == 1:
            # 此刻用户切到设置页 → 自动保存 → reload_models → retire
            await registry.retire()
            assert llm.closed is False, "还有请求在跑，绝不能关掉客户端"

    # 流完整跑完（这正是用户要的：切个页面不该打断回答）
    assert "".join(seen) == "你好呀"
    # 归还最后一个租约后，旧注册表才被回收
    assert llm.closed is True


@pytest.mark.asyncio
async def test_retire_without_inflight_closes_immediately() -> None:
    """没有在途请求时立刻回收 —— 保持与旧行为一致，不留下悬空连接。"""
    registry = LlmRegistry()
    llm = _FakeLLM()
    registry.register("m1", llm, is_default=True)

    await registry.retire()

    assert llm.closed is True


@pytest.mark.asyncio
async def test_lease_is_released_on_stream_error() -> None:
    """流中途抛异常时租约也必须归还。

    不归还的话旧注册表会**永远**不被回收（连接一直挂着），
    而且这个泄漏只在"正好出错 + 正好改配置"时出现，极难发现。
    """

    class _Boom(_FakeLLM):
        async def stream(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:
            yield StreamChunk(delta="半")
            raise RuntimeError("网络断了")

    registry = LlmRegistry()
    llm = _Boom()
    registry.register("m1", llm, is_default=True)

    stream = llm.leased_stream([])
    # 先真的**开始**消费：租约是在进入生成器时才借出的，
    # 没开始消费就 retire 属于"没有在途请求"，会（正确地）立刻关掉。
    assert (await stream.__anext__()).delta == "半"
    await registry.retire()
    assert llm.closed is False
    assert registry.active_leases == 1

    with pytest.raises(RuntimeError):
        await stream.__anext__()

    # 异常路径也必须归还租约，否则旧注册表永远不会被回收
    assert registry.active_leases == 0
    assert llm.closed is True


@pytest.mark.asyncio
async def test_lease_without_registry_is_noop() -> None:
    """没接注册表的适配器（单测里直接构造的那种）也要能正常用。"""
    llm = _FakeLLM(["x"])

    seen = [chunk.delta async for chunk in llm.leased_stream([])]

    assert seen == ["x"]


@pytest.mark.asyncio
async def test_turn_lease_survives_retire_during_tool_execution() -> None:
    """**用户报的那个错**：工具执行期间改配置，这一轮不能被打断。

    现象：buddy 执行任务时切到设置页 → 自动保存 `PUT /v1/models` →
    `reload_models` → `retire()`。如果租约只覆盖"单次模型流"，此刻**工具正在执行、
    没有租约**，旧客户端会被当场关掉，该轮后面那次模型调用就抛
    ``RuntimeError: Cannot send a request, as the client has been closed.``

    这条测试把"整轮持租"这个不变量钉住：retire 发生时客户端**不能**被关闭，
    且这一轮必须完整跑完。
    """
    from my_agent.agent.engine import Agent, AgentConfig
    from my_agent.llm.base import ToolCall
    from my_agent.memory.short_term import MemoryManager
    from my_agent.skill.base import BaseSkill, SkillContext
    from my_agent.skill.decorator import skill
    from my_agent.skill.manager import SkillManager

    registry = LlmRegistry()
    probes: dict[str, Any] = {}

    class _TwoRoundLLM(BaseLLM):
        """第一轮要求调工具，第二轮给最终答复。"""

        def __init__(self) -> None:
            super().__init__(model_name="fake")
            self.closed = False
            self.rounds = 0

        async def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError

        async def stream(self, *args: Any, **kwargs: Any) -> Any:
            self.rounds += 1
            if self.rounds == 1:
                yield StreamChunk(
                    tool_calls=[ToolCall(id="c1", name="probe", raw_arguments="{}")],
                    finish_reason="tool_calls",
                )
            else:
                yield StreamChunk(delta="完成", finish_reason="stop")

        async def aclose(self) -> None:
            self.closed = True

    llm = _TwoRoundLLM()
    registry.register("m1", llm, is_default=True)

    @skill(name="probe", description="探测工具", params_model=None)
    class _Probe(BaseSkill):
        async def run(self, ctx: Any, **params: Any) -> Any:
            # 模拟"用户在工具执行期间切到设置页并触发保存"
            await registry.retire()
            probes["closed_during_tool"] = llm.closed
            return "ok"

    manager = SkillManager()
    manager.register(_Probe)
    agent = Agent(
        llm=llm,  # type: ignore[arg-type]
        skill_manager=manager,
        memory=MemoryManager(),
        config=AgentConfig(),
        ctx=SkillContext(),
    )

    events = [event async for event in agent.run_stream("跑一下")]

    assert probes["closed_during_tool"] is False, "工具执行期间不得关闭在用客户端"
    assert [e for e in events if e.type == "done"], "这一轮必须完整跑完"
    assert llm.rounds == 2, "第二次模型调用必须能正常发出"
    # 整轮结束后最后一个租约归还，旧注册表才被回收
    assert llm.closed is True


# --------------------------------------------------------------------------- #
# 静态闸：防止有人把这两处改回去
# --------------------------------------------------------------------------- #
def test_engine_runs_streams_under_a_lease() -> None:
    """引擎必须走 ``leased_stream``。

    改成 ``self.llm.stream(...)`` 的话，租约就没人借了，
    ``reload_models`` 会立刻关掉旧客户端 —— 也就是那个"切页面就打断"的老问题。
    这类退化不会报错、只会在某个时刻表现为网络异常，所以只能用静态断言守。
    """
    source = Path(engine_mod.__file__).read_text(encoding="utf-8")

    assert "leased_stream" in source
    assert "self.llm.stream(" not in source


def test_reload_models_retires_instead_of_closing() -> None:
    """``reload_models`` 必须 ``retire()``，**不能**直接 ``aclose()`` 旧注册表。

    注释行要被剔除：那段"不能这么写"的说明里天然带着旧写法，
    不剔除的话这条断言会拦住的恰恰是解释它为什么错的注释。
    """
    source = Path(runtime_mod.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    assert "await old.retire()" in code
    assert "old.aclose()" not in code
