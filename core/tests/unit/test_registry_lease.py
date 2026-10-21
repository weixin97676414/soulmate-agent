













from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from my_agent.agent import engine as engine_mod
from my_agent.llm.base import BaseLLM, StreamChunk
from my_agent.llm.registry import LlmRegistry
from my_agent.server import runtime as runtime_mod


class _FakeLLM(BaseLLM):


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

    registry = LlmRegistry()
    llm = _FakeLLM(["你", "好", "呀"])
    registry.register("m1", llm, is_default=True)

    seen: list[str] = []
    async for chunk in llm.leased_stream([]):
        seen.append(chunk.delta or "")
        if len(seen) == 1:
            
            await registry.retire()
            assert llm.closed is False, "还有请求在跑，绝不能关掉客户端"

    
    assert "".join(seen) == "你好呀"
    
    assert llm.closed is True


@pytest.mark.asyncio
async def test_retire_without_inflight_closes_immediately() -> None:

    registry = LlmRegistry()
    llm = _FakeLLM()
    registry.register("m1", llm, is_default=True)

    await registry.retire()

    assert llm.closed is True


@pytest.mark.asyncio
async def test_lease_is_released_on_stream_error() -> None:






    class _Boom(_FakeLLM):
        async def stream(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:
            yield StreamChunk(delta="半")
            raise RuntimeError("网络断了")

    registry = LlmRegistry()
    llm = _Boom()
    registry.register("m1", llm, is_default=True)

    stream = llm.leased_stream([])
    
    
    assert (await stream.__anext__()).delta == "半"
    await registry.retire()
    assert llm.closed is False
    assert registry.active_leases == 1

    with pytest.raises(RuntimeError):
        await stream.__anext__()

    
    assert registry.active_leases == 0
    assert llm.closed is True


@pytest.mark.asyncio
async def test_lease_without_registry_is_noop() -> None:

    llm = _FakeLLM(["x"])

    seen = [chunk.delta async for chunk in llm.leased_stream([])]

    assert seen == ["x"]


@pytest.mark.asyncio
async def test_turn_lease_survives_retire_during_tool_execution() -> None:










    from my_agent.agent.engine import Agent, AgentConfig
    from my_agent.llm.base import ToolCall
    from my_agent.memory.short_term import MemoryManager
    from my_agent.skill.base import BaseSkill, SkillContext
    from my_agent.skill.decorator import skill
    from my_agent.skill.manager import SkillManager

    registry = LlmRegistry()
    probes: dict[str, Any] = {}

    class _TwoRoundLLM(BaseLLM):


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
            
            await registry.retire()
            probes["closed_during_tool"] = llm.closed
            return "ok"

    manager = SkillManager()
    manager.register(_Probe)
    agent = Agent(
        llm=llm,  
        skill_manager=manager,
        memory=MemoryManager(),
        config=AgentConfig(),
        ctx=SkillContext(),
    )

    events = [event async for event in agent.run_stream("跑一下")]

    assert probes["closed_during_tool"] is False, "工具执行期间不得关闭在用客户端"
    assert [e for e in events if e.type == "done"], "这一轮必须完整跑完"
    assert llm.rounds == 2, "第二次模型调用必须能正常发出"
    
    assert llm.closed is True





def test_engine_runs_streams_under_a_lease() -> None:






    source = Path(engine_mod.__file__).read_text(encoding="utf-8")

    assert "leased_stream" in source
    assert "self.llm.stream(" not in source


def test_reload_models_retires_instead_of_closing() -> None:





    source = Path(runtime_mod.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    assert "await old.retire()" in code
    assert "old.aclose()" not in code
