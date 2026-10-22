








from __future__ import annotations

import asyncio

import pytest

from my_agent.agent.engine import Agent, AgentConfig
from my_agent.agent.session import Session
from my_agent.errors import SkillPermissionError
from my_agent.llm.base import LLMResponse
from my_agent.memory.short_term import MemoryManager, is_internal
from my_agent.skill.base import BaseSkill, SkillContext
from my_agent.skill.decorator import skill
from my_agent.skill.manager import SkillManager

from ..conftest import FakeLLM, tool_call


@skill(name="echo", description="回显输入文本，用于测试。", params_model=None)
class EchoSkill(BaseSkill):
    async def run(self, ctx, **params):
        return {"echo": params.get("text", "")}


@skill(
    name="always_fail",
    description="总是失败，用于测试失败回填。",
    params_model=None,
)
class AlwaysFailSkill(BaseSkill):
    async def run(self, ctx, **params):
        raise RuntimeError("模拟的工具故障")


@skill(
    name="needs_confirm",
    description="需要人工确认的高危操作。",
    params_model=None,
    permission_level="confirm",
)
class ConfirmSkill(BaseSkill):
    async def run(self, ctx, **params):
        return "已执行"


def build_agent(llm, *, skills=None, confirm=None, config=None, memory=None):
    manager = SkillManager()
    for s in skills or []:
        manager.register(s)
    ctx = SkillContext(confirm=confirm)
    return Agent(
        llm=llm,
        skill_manager=manager,
        
        
        
        
        memory=memory if memory is not None else MemoryManager(),
        config=config or AgentConfig(),
        ctx=ctx,
    )


async def collect(agent, text):
    return [e async for e in agent.run_stream(text)]


def _tool_response(name: str) -> LLMResponse:
    return LLMResponse(
        tool_calls=[tool_call(name, {}, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )


@pytest.mark.asyncio
async def test_persona_refreshes_mid_turn_after_self_update():







    persona_state = {"text": "你是旧人格"}

    @skill(name="self_persona_update", description="改人格", params_model=None)
    class FakePersonaUpdate(BaseSkill):
        async def run(self, ctx, **params):
            persona_state["text"] = "你是新人格"
            return "已更新 SOUL"

    llm = FakeLLM([_tool_response("self_persona_update"), "好的"])
    agent = build_agent(
        llm,
        skills=[FakePersonaUpdate()],
        config=AgentConfig(persona=lambda: persona_state["text"]),
    )

    await collect(agent, "改一下你的人格")

    assert "你是旧人格" in llm.calls[0][0].content, "第一轮还没改，应是旧人格"
    assert "你是新人格" in llm.calls[1][0].content, "工具写完人格后，同轮内就要用新人格"


@pytest.mark.asyncio
async def test_tool_call_round_trip():

    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("calc", {"expression": "1+2"})],
                finish_reason="tool_calls",
            ),
            "计算结果是 3",
        ]
    )
    from my_agent.skill.builtin.system import CalculatorSkill

    agent = build_agent(llm, skills=[CalculatorSkill])
    events = await collect(agent, "1+2 等于多少")

    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "done" in types

    result = next(e for e in events if e.type == "tool_result")
    assert result.data["status"] == "ok"
    assert '"result": 3' in result.data["result"].replace("'", '"')

    
    text = "".join(e.data["text"] for e in events if e.type == "delta")
    assert "3" in text


@pytest.mark.asyncio
async def test_tool_result_is_fed_back_to_model():

    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[tool_call("echo", {"text": "hi"})], finish_reason="tool_calls"
            ),
            "收到",
        ]
    )
    agent = build_agent(llm, skills=[EchoSkill])
    events = await collect(agent, "回显 hi")

    assert len(llm.calls) == 2
    second_call_messages = llm.calls[1]
    tool_messages = [m for m in second_call_messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert "hi" in tool_messages[0].content
    assert tool_messages[0].tool_call_id == "call_1"
    
    assistant_with_calls = [
        m for m in second_call_messages if m.role == "assistant" and m.tool_calls
    ]
    assert len(assistant_with_calls) == 1
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_max_iterations_stops_loop():

    from my_agent.skill.builtin.system import CurrentTimeSkill

    script = [
        LLMResponse(
            tool_calls=[tool_call("system_time", {}, f"call_{i}")], finish_reason="tool_calls"
        )
        for i in range(10)
    ]
    llm = FakeLLM(script)
    agent = build_agent(llm, skills=[CurrentTimeSkill], config=AgentConfig(max_iterations=3))
    events = await collect(agent, "现在几点")

    types = [e.type for e in events]
    assert "error" in types
    error = next(e for e in events if e.type == "error")
    assert error.data["code"] == "agent_max_iterations"
    
    assert len(llm.calls) == 3


@pytest.mark.asyncio
async def test_tool_failure_is_fed_back_and_then_disabled():

    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[tool_call("always_fail", {}, f"c{i}")], finish_reason="tool_calls"
            )
            for i in range(6)
        ]
    )
    agent = build_agent(
        llm,
        skills=[AlwaysFailSkill],
        config=AgentConfig(max_iterations=5, same_tool_failure_tolerance=2),
    )
    events = await collect(agent, "跑一下")

    results = [e for e in events if e.type == "tool_result"]
    assert len(results) >= 2
    assert results[0].data["status"] == "error"
    
    assert any("已因连续失败被停用" in r.data["result"] for r in results)


@pytest.mark.asyncio
async def test_permission_denied_does_not_break_task():


    async def deny(_request):
        return False

    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[tool_call("needs_confirm")], finish_reason="tool_calls"
            ),
            "好的，那我不执行了。",
        ]
    )
    agent = build_agent(llm, skills=[ConfirmSkill], confirm=deny)
    events = await collect(agent, "帮我删掉这个文件")

    result = next(e for e in events if e.type == "tool_result")
    assert result.data["status"] == "denied"
    assert "权限拒绝" in result.data["result"]
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_confirm_required_without_channel_is_denied():

    llm = FakeLLM(["（不应该走到这里）"])
    agent = build_agent(llm, skills=[ConfirmSkill], confirm=None)

    with pytest.raises(SkillPermissionError):
        await agent.skills.execute("needs_confirm", {}, agent.ctx)


@pytest.mark.asyncio
async def test_approved_confirm_executes():

    prompts: list[str] = []

    async def approve(request):
        prompts.append(request.skill_name)
        return True

    llm = FakeLLM(
        [
            LLMResponse(tool_calls=[tool_call("needs_confirm")], finish_reason="tool_calls"),
            "已完成",
        ]
    )
    agent = build_agent(llm, skills=[ConfirmSkill], confirm=approve)
    events = await collect(agent, "执行吧")

    result = next(e for e in events if e.type == "tool_result")
    assert result.data["status"] == "ok"
    assert prompts == ["needs_confirm"]





@skill(name="slow", description="慢工具，用于测试中断收尾。", params_model=None)
class SlowSkill(BaseSkill):
    async def run(self, ctx, **params):
        await asyncio.sleep(30)
        return "不该等到这里"


@pytest.mark.asyncio
async def test_cancel_seals_dangling_tool_calls():








    memory = MemoryManager()
    llm = FakeLLM(
        [
            LLMResponse(
                content="我来跑两个工具。",
                tool_calls=[tool_call("slow", {}, "c1"), tool_call("slow", {}, "c2")],
                finish_reason="tool_calls",
            )
        ]
    )
    agent = build_agent(llm, skills=[SlowSkill], memory=memory)

    async def consume() -> None:
        async for _ in agent.run_stream("跑两个慢工具"):
            pass

    task = asyncio.create_task(consume())
    
    for _ in range(400):
        await asyncio.sleep(0.005)
        if any(m.role == "assistant" and m.tool_calls for m in memory.messages):
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    declared = next(m for m in memory.messages if m.role == "assistant" and m.tool_calls)
    answered = {m.tool_call_id for m in memory.messages if m.role == "tool"}
    missing = {tc.id for tc in declared.tool_calls} - answered
    assert not missing, f"中断后有工具调用缺少结果 {missing}，消息序列对协议非法"

    
    assert any(
        "已中断" in m.content for m in memory.messages if m.role == "tool"
    )


@pytest.mark.asyncio
async def test_cancel_does_not_duplicate_assistant_text():





    memory = MemoryManager()
    llm = FakeLLM(
        [
            LLMResponse(
                content="先执行工具，这是正文。",
                tool_calls=[tool_call("slow", {}, "c1")],
                finish_reason="tool_calls",
            )
        ]
    )
    agent = build_agent(llm, skills=[SlowSkill], memory=memory)

    async def consume() -> None:
        async for _ in agent.run_stream("跑一个慢工具"):
            pass

    task = asyncio.create_task(consume())
    for _ in range(400):
        await asyncio.sleep(0.005)
        if any(m.role == "assistant" and m.tool_calls for m in memory.messages):
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    texts = [m.content for m in memory.messages if m.role == "assistant" and m.content]
    assert texts.count("先执行工具，这是正文。") == 1


@pytest.mark.asyncio
async def test_empty_response_nudge_is_marked_internal():





    memory = MemoryManager()
    llm = FakeLLM(["", "这才是正式回答"])
    agent = build_agent(llm, memory=memory)
    events = await collect(agent, "你好")

    
    nudges = [m for m in memory.messages if m.role == "user" and is_internal(m.content)]
    assert len(nudges) == 1

    
    session = Session(id="s1", memory=memory)
    user_texts = [item["content"] for item in session.history() if item["role"] == "user"]
    assert user_texts == ["你好"]
    assert events[-1].type == "done"
