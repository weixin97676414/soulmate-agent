







from __future__ import annotations

import asyncio

import pytest

from my_agent.agent.engine import Agent, AgentConfig
from my_agent.agent.planner import Planner
from my_agent.agent.reflection import Reflector
from my_agent.agent.text_tools import extract_text_tool_calls, render_tools_section
from my_agent.config.schemas import ModelSpec
from my_agent.llm.base import BaseLLM, LLMResponse, StreamChunk, ToolCall, ToolSpec
from my_agent.llm.router import ModelRouter, pick_tier, score_complexity
from my_agent.memory.short_term import MemoryManager
from my_agent.skill.base import BaseSkill, SkillContext, SkillMeta, mark_terminate
from my_agent.skill.manager import SkillManager





class ScriptedLLM(BaseLLM):


    def __init__(self, script: list[tuple[str, list[ToolCall] | None]]) -> None:
        super().__init__(model_name="scripted")
        self.script = list(script)
        self.turn = 0

    async def stream(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        text, calls = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        if text:
            yield StreamChunk(delta=text)
        yield StreamChunk(
            tool_calls=calls or None,
            finish_reason="tool_calls" if calls else "stop",
        )

    async def chat(self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling):
        return LLMResponse(content="", finish_reason="stop")


class Probe:


    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def run(self) -> str:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        
        await asyncio.sleep(0.05)
        self.active -= 1
        return "done"


def make_probe_skill(name: str, probe: Probe, *, level: str = "safe") -> BaseSkill:
    class _ProbeSkill(BaseSkill):
        meta = SkillMeta(name=name, description=f"{name} 的描述", permission_level=level)

        async def run(self, ctx, **params):
            return await probe.run()

    return _ProbeSkill()


def build_agent(
    llm: BaseLLM,
    skills: list[BaseSkill],
    *,
    enabled_skills: set[str] | None = None,
    **config_kwargs,
) -> Agent:
    manager = SkillManager()
    for skill in skills:
        manager.register(skill)
    return Agent(
        llm=llm,
        skill_manager=manager,
        memory=MemoryManager(),
        config=AgentConfig(enabled_skills=enabled_skills, **config_kwargs),
        ctx=SkillContext(session_id="test"),
    )


async def collect(agent: Agent, text: str) -> list:
    return [event async for event in agent.run_stream(text)]





class TestParallelTools:
    @pytest.mark.asyncio
    async def test_distinct_safe_tools_run_concurrently(self):

        probe = Probe()
        calls = [
            ToolCall(id="1", name="alpha", arguments={}),
            ToolCall(id="2", name="beta", arguments={}),
        ]
        agent = build_agent(
            ScriptedLLM([("", calls), ("做完了", None)]),
            [make_probe_skill("alpha", probe), make_probe_skill("beta", probe)],
        )

        await collect(agent, "两个都做")

        assert probe.max_active == 2, "两个独立工具应当并发执行"

    @pytest.mark.asyncio
    async def test_same_tool_is_serialized(self):

        probe = Probe()
        calls = [
            ToolCall(id="1", name="writer", arguments={"n": 1}),
            ToolCall(id="2", name="writer", arguments={"n": 2}),
        ]
        agent = build_agent(
            ScriptedLLM([("", calls), ("做完了", None)]),
            [make_probe_skill("writer", probe)],
        )

        await collect(agent, "写两次")

        assert probe.max_active == 1

    def test_confirm_level_tools_are_not_parallelized(self):

        agent = build_agent(ScriptedLLM([("x", None)]), [])
        safe = SkillMeta(name="a", description="", permission_level="safe")
        confirm = SkillMeta(name="b", description="", permission_level="confirm")
        calls = [ToolCall(id="1", name="a", arguments={}), ToolCall(id="2", name="b", arguments={})]

        assert agent._can_run_parallel([(calls[0], safe, "a"), (calls[1], safe, "b")])
        assert not agent._can_run_parallel([(calls[0], safe, "a"), (calls[1], confirm, "b")])

    def test_single_call_is_never_parallel(self):
        agent = build_agent(ScriptedLLM([("x", None)]), [])
        meta = SkillMeta(name="a", description="")
        assert not agent._can_run_parallel([(ToolCall(id="1", name="a", arguments={}), meta, "a")])





class TestTerminationAndGuards:
    @pytest.mark.asyncio
    async def test_termination_marker_stops_the_loop(self):


        class Finisher(BaseSkill):
            meta = SkillMeta(name="finish", description="收尾")

            async def run(self, ctx, **params):
                return mark_terminate("已提交，等人工处理")

        llm = ScriptedLLM(
            [
                ("", [ToolCall(id="1", name="finish", arguments={})]),
                ("我不该被调用到", None),
            ]
        )
        agent = build_agent(llm, [Finisher()])

        events = await collect(agent, "提交")

        assert llm.turn == 1, "终止后不应再请求模型"
        done = [e for e in events if e.type == "done"]
        assert done and done[0].data.get("terminated") is True

    @pytest.mark.asyncio
    async def test_disabled_skill_cannot_be_executed(self):

        probe = Probe()
        manager = SkillManager()
        skill = manager.register(make_probe_skill("probe", probe))
        manager.set_enabled("probe", False)

        agent = Agent(
            llm=ScriptedLLM([("", [ToolCall(id="1", name="probe", arguments={})]), ("好", None)]),
            skill_manager=manager,
            memory=MemoryManager(),
            config=AgentConfig(),
            ctx=SkillContext(session_id="t"),
        )

        events = await collect(agent, "试一下")

        assert probe.max_active == 0, "被禁用的工具不该被执行"
        results = [e for e in events if e.type == "tool_result"]
        assert results and results[0].data["status"] == "denied"
        
        assert skill.meta.enabled is False

    @pytest.mark.asyncio
    async def test_skill_outside_session_scope_is_denied(self):
        probe = Probe()
        agent = build_agent(
            ScriptedLLM([("", [ToolCall(id="1", name="probe", arguments={})]), ("好", None)]),
            [make_probe_skill("probe", probe)],
            enabled_skills={"别的技能"},
        )

        events = await collect(agent, "试一下")

        assert probe.max_active == 0
        assert any(
            e.type == "tool_result" and e.data["status"] == "denied" for e in events
        )





class TestRequires:
    def test_dependencies_are_pulled_in(self):

        manager = SkillManager()

        class NeedsOther(BaseSkill):
            meta = SkillMeta(name="exporter", description="导出", requires=["reader"])

        class Other(BaseSkill):
            meta = SkillMeta(name="reader", description="读取")

        manager.register(NeedsOther())
        manager.register(Other())

        specs = manager.to_tool_specs(filter_names={"exporter"})
        names = {s.name for s in specs}

        assert names == {"exporter", "reader"}

    def test_missing_dependency_is_skipped_not_fatal(self):
        manager = SkillManager()

        class NeedsGhost(BaseSkill):
            meta = SkillMeta(name="solo", description="", requires=["ghost"])

        manager.register(NeedsGhost())

        assert manager.requires_closure({"solo"}) == {"solo"}

    def test_mutual_dependency_does_not_hang(self):
        manager = SkillManager()

        class A(BaseSkill):
            meta = SkillMeta(name="a", description="", requires=["b"])

        class B(BaseSkill):
            meta = SkillMeta(name="b", description="", requires=["a"])

        manager.register(A())
        manager.register(B())

        assert manager.requires_closure({"a"}) == {"a", "b"}





class TestTextTools:
    def test_renders_tool_list_into_prompt(self):
        specs = [
            ToolSpec(
                name="weather",
                description="查天气",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "城市"}},
                    "required": ["city"],
                },
            )
        ]

        text = render_tools_section(specs)

        assert "weather" in text
        assert "查天气" in text
        assert "必填" in text
        assert "tool_call" in text

    def test_extracts_single_call(self):
        reply = '我来查一下。\n```tool_call\n{"name": "weather", "arguments": {"city": "北京"}}\n```'

        cleaned, calls = extract_text_tool_calls(reply)

        assert len(calls) == 1
        assert calls[0].name == "weather"
        assert calls[0].arguments == {"city": "北京"}
        
        assert "tool_call" not in cleaned
        assert cleaned.strip() == "我来查一下。"

    def test_extracts_multiple_calls(self):
        reply = (
            "```tool_call\n{\"name\": \"a\", \"arguments\": {}}\n```\n"
            "```tool_call\n{\"name\": \"b\", \"arguments\": {}}\n```"
        )

        _, calls = extract_text_tool_calls(reply)

        assert [c.name for c in calls] == ["a", "b"]

    def test_malformed_block_is_kept_as_plain_text(self):

        reply = '看这个：\n```tool_call\n{这不是 JSON}\n```'

        cleaned, calls = extract_text_tool_calls(reply)

        assert calls == []
        assert "这不是 JSON" in cleaned

    def test_plain_text_passes_through(self):
        cleaned, calls = extract_text_tool_calls("就是普通回答")

        assert calls == []
        assert cleaned == "就是普通回答"

    def test_ordinary_code_block_is_not_a_tool_call(self):

        reply = "示例：\n```python\nprint(1)\n```"

        _, calls = extract_text_tool_calls(reply)

        assert calls == []





def spec(model_id: str, tier: str) -> ModelSpec:
    return ModelSpec(
        id=model_id,
        model_name=model_id,
        base_url="https://x.example.com/v1",
        tier=tier,  
    )


class TestModelRouter:
    def test_short_question_prefers_cheap(self):
        router = ModelRouter(
            default_id="mid",
            candidates=[spec("cheap", "cheap"), spec("mid", "standard"), spec("big", "strong")],
        )

        assert router.pick(text="翻译一下这句话") == "cheap"

    def test_complex_task_prefers_strong(self):
        router = ModelRouter(
            default_id="mid",
            candidates=[spec("cheap", "cheap"), spec("mid", "standard"), spec("big", "strong")],
        )
        text = "帮我做一份月度分析报告，然后整理成表格，再分别导出两份对比"

        assert router.pick(text=text, need_tools=True) == "big"

    def test_missing_tier_falls_back(self):
        router = ModelRouter(default_id="mid", candidates=[spec("mid", "standard")])

        assert router.pick(text="随便问一句") == "mid"

    def test_disabled_router_returns_none(self):
        router = ModelRouter(
            default_id="mid",
            candidates=[spec("cheap", "cheap")],
            enabled=False,
        )

        assert router.pick(text="翻译") is None

    def test_only_single_model_configured(self):

        router = ModelRouter(default_id="only", candidates=[spec("only", "standard")])

        assert router.pick(text="随便") == "only"

    def test_respects_session_scope(self):
        router = ModelRouter(
            default_id="mid",
            candidates=[spec("cheap", "cheap"), spec("mid", "standard")],
        )

        
        assert router.pick(text="翻译", within={"mid"}) == "mid"

    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0, "cheap"), (2, "cheap"), (3, "standard"), (5, "standard"), (6, "strong"), (9, "strong")],
    )
    def test_tier_mapping(self, score: int, expected: str):
        assert pick_tier(score) == expected

    def test_long_input_scores_higher(self):
        assert score_complexity("短", need_tools=False) < score_complexity(
            "长" * 2000, need_tools=False
        )





class TestPlanner:
    def test_disabled_by_default(self):
        assert not Planner().should_plan("帮我做一份报告然后导出", need_tools=True)

    def test_enabled_only_for_complex_tasks(self):
        planner = Planner(enabled=True)

        assert planner.should_plan("你好", need_tools=False) is False
        assert planner.should_plan(
            "帮我做一份月度报告，然后整理成表格，再分别导出对比", need_tools=True
        )

    @pytest.mark.asyncio
    async def test_llm_failure_returns_no_plan(self):
        class Broken(BaseLLM):
            async def chat(self, *a, **kw):
                raise RuntimeError("boom")

            async def stream(self, *a, **kw):
                yield  

        planner = Planner(enabled=True)

        
        assert await planner.make_plan(Broken(model_name="b"), user_input="做点事") is None

    @pytest.mark.asyncio
    async def test_json_plan_is_parsed(self):
        class Fake(BaseLLM):
            async def chat(self, *a, **kw):
                return LLMResponse(
                    content='好的，这是计划：\n```json\n{"goal": "出一份月报", '
                    '"steps": ["拉取数据", "整理成表", "导出对比"]}\n```',
                    finish_reason="stop",
                )

            async def stream(self, *a, **kw):
                yield  

        plan = await Planner(enabled=True).make_plan(Fake(model_name="f"), user_input="做月报")

        assert plan is not None
        assert plan.goal == "出一份月报"
        assert [step.text for step in plan.steps] == ["拉取数据", "整理成表", "导出对比"]
        assert [step.status for step in plan.steps] == ["pending", "pending", "pending"]

    @pytest.mark.asyncio
    async def test_numbered_text_falls_back(self):


        class Fake(BaseLLM):
            async def chat(self, *a, **kw):
                return LLMResponse(content="1. 先查数据\n2. 再整理表格", finish_reason="stop")

            async def stream(self, *a, **kw):
                yield  

        plan = await Planner(enabled=True).make_plan(Fake(model_name="f"), user_input="做月报")

        assert plan is not None
        assert [step.text for step in plan.steps] == ["先查数据", "再整理表格"]

    @pytest.mark.asyncio
    async def test_single_step_is_not_a_plan(self):


        class Fake(BaseLLM):
            async def chat(self, *a, **kw):
                return LLMResponse(
                    content='{"goal": "打招呼", "steps": ["问好"]}', finish_reason="stop"
                )

            async def stream(self, *a, **kw):
                yield  

        assert await Planner(enabled=True).make_plan(Fake(model_name="f"), user_input="你好") is None


class TestReflector:
    def test_review_skipped_for_tiny_answers(self):
        reflector = Reflector(enabled=True)

        assert not reflector.should_review("好的", rounds_done=0)

    def test_round_limit_is_respected(self):
        reflector = Reflector(enabled=True, max_rounds=1)
        answer = "这是一段足够长的回答内容，长到值得为它自检一次，不会因为太短被跳过。"

        assert reflector.should_review(answer, rounds_done=0)
        assert not reflector.should_review(answer, rounds_done=1)

    @pytest.mark.asyncio
    async def test_ok_verdict_passes(self):
        class Reviewer(BaseLLM):
            async def chat(self, *a, **kw):
                return LLMResponse(content="OK", finish_reason="stop")

            async def stream(self, *a, **kw):
                yield  

        result = await Reflector(enabled=True).review(
            Reviewer(model_name="r"), user_input="问", answer="答"
        )

        assert result.passed

    @pytest.mark.asyncio
    async def test_revise_verdict_carries_feedback(self):
        class Reviewer(BaseLLM):
            async def chat(self, *a, **kw):
                return LLMResponse(content="REVISE: 漏了第二条要求", finish_reason="stop")

            async def stream(self, *a, **kw):
                yield  

        result = await Reflector(enabled=True).review(
            Reviewer(model_name="r"), user_input="问", answer="答"
        )

        assert result.needs_revision
        assert "漏了第二条" in result.feedback

    @pytest.mark.asyncio
    async def test_review_failure_never_blocks(self):


        class Broken(BaseLLM):
            async def chat(self, *a, **kw):
                raise RuntimeError("boom")

            async def stream(self, *a, **kw):
                yield  

        result = await Reflector(enabled=True).review(
            Broken(model_name="b"), user_input="问", answer="答"
        )

        assert result.passed
