











from __future__ import annotations

import types
from typing import Any

import pytest

from my_agent.agent.engine import AgentEvent
from my_agent.agent.session import Session
from my_agent.agent.turn_builder import build_agent_config
from my_agent.feishu.turn import TurnFailed, run_turn_silently


class _Skills:


    def allowed_names(self, **_kwargs: Any) -> list[str]:
        return []


def _runtime(*, models: int) -> Any:
    agent_cfg = types.SimpleNamespace(
        max_iterations=8,
        max_tool_calls_per_turn=20,
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        same_tool_failure_tolerance=2,
        keep_recent_messages=10,
        compress_threshold=0.8,
        enable_reflection=False,
        reflection_rounds=1,
    )
    settings = types.SimpleNamespace(agent=agent_cfg, trace_enabled=False)

    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    return types.SimpleNamespace(
        config=types.SimpleNamespace(
            settings=settings,
            models=types.SimpleNamespace(default_model="m1", models=[]),
        ),
        skills=_Skills(),
        registry={} if models == 0 else {"m1": object()},
        effective_context_tokens=lambda model_id: 32000,
        
        
        resolve_assistant=lambda _id: None,
        utility_llm=lambda llm: None,
        paths=None,
        workspace=None,
        path_policy=None,
        audit=types.SimpleNamespace(record=_noop, op=_noop),
        skill_services_for=lambda _id: {},
        assistant_confirm_mode=lambda _id: "auto",
        sessions=types.SimpleNamespace(persist=_noop),
    )


def test_plan_mode_is_off_without_a_decider() -> None:

    config = build_agent_config(
        runtime=_runtime(models=1),
        session=Session(id="s1"),
        profile=None,
        model_id="m1",
        llm=object(),
        plan_decider=None,
    )
    assert config.enable_planner is False
    assert config.plan_decider is None


def test_plan_mode_stays_on_when_a_decider_is_given() -> None:

    async def decider(_plan: dict[str, Any]) -> tuple[bool, str]:
        return True, ""

    config = build_agent_config(
        runtime=_runtime(models=1),
        session=Session(id="s1"),
        profile=None,
        model_id="m1",
        llm=object(),
        plan_decider=decider,
    )
    assert config.enable_planner is True


def test_context_window_comes_from_the_chosen_model() -> None:

    config = build_agent_config(
        runtime=_runtime(models=1),
        session=Session(id="s1"),
        profile=None,
        model_id="m1",
        llm=object(),
    )
    assert config.token_limit == 32000


@pytest.mark.asyncio
async def test_turn_fails_with_a_human_reason_when_no_model() -> None:

    with pytest.raises(TurnFailed) as exc:
        await run_turn_silently(_runtime(models=0), Session(id="s1"), "你好")
    assert "还没有配置任何模型" in str(exc.value)


class _FakeAgent:







    def __init__(self, chunks: list[str], memory: Any) -> None:
        self._chunks = chunks
        self._memory = memory
        self.seen_input = ""

    async def run_stream(self, user_input: str, *, images: Any = None) -> Any:
        self.seen_input = user_input
        self._memory.add_user(user_input)  
        for piece in self._chunks:
            
            yield AgentEvent("delta", {"text": piece})
        self._memory.add_assistant("".join(self._chunks))  
        yield AgentEvent("done", {"iterations": 1})


@pytest.mark.asyncio
async def test_delta_is_collected_from_the_text_field(monkeypatch) -> None:






    def _factory(**kwargs: Any) -> _FakeAgent:
        return _FakeAgent(["你", "好", "呀"], kwargs["memory"])

    monkeypatch.setattr("my_agent.feishu.turn.Agent", _factory)

    session = Session(id="s1")
    reply = await run_turn_silently(_runtime(models=1), session, "打个招呼")
    assert reply == "你好呀"

    
    
    
    roles = [m.role for m in session.memory.messages]
    assert roles.count("user") == 1, f"user 重复了：{roles}"
    assert roles.count("assistant") == 1, f"assistant 重复了：{roles}"


@pytest.mark.asyncio
async def test_empty_delta_raises_instead_of_sending_nothing(monkeypatch) -> None:

    monkeypatch.setattr(
        "my_agent.feishu.turn.Agent",
        lambda **kwargs: _FakeAgent([], kwargs["memory"]),
    )

    with pytest.raises(TurnFailed) as exc:
        await run_turn_silently(_runtime(models=1), Session(id="s1"), "你好")
    assert "空回复" in str(exc.value)
