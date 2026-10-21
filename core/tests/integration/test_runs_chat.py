










from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.llm.base import LLMResponse, StreamChunk

from ..conftest import FakeLLM, tool_call
from .conftest import install_fake_model, read_sse


def _register_probe(runtime, calls: list[str]) -> None:

    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="probe_steps",
        display_name="探针",
        description="测试用探针（无副作用）",
        permission_level="safe",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  
            calls.append("probe_steps")
            return "ok"

    runtime.skills.register(_Probe)


async def _chat_runs(runtime) -> list:

    return [run for run in await runtime.runs.list_pending() if run.kind == "chat"]


async def _wait_chat_run(runtime, *, timeout: float = 30.0):












    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        rows = await _chat_runs(runtime)
        if rows:
            return rows[0]
        await asyncio.sleep(0.05)
    return None


@pytest.mark.asyncio
async def test_finished_chat_leaves_no_pending_run(runtime, client):
    install_fake_model(runtime, FakeLLM(["你好呀"]))
    await read_sse(client, {"message": "你好", "model_id": "fake"})

    assert await _chat_runs(runtime) == []


@pytest.mark.asyncio
async def test_step_limit_leaves_incomplete_run_and_gives_resume_topic(runtime, client):

    calls: list[str] = []
    _register_probe(runtime, calls)
    runtime.config.settings.agent.max_iterations = 2
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("probe_steps", {})],
                    finish_reason="tool_calls",
                ),
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("probe_steps", {})],
                    finish_reason="tool_calls",
                ),
            ]
        ),
    )

    events = await read_sse(client, {"message": "一直做下去", "model_id": "fake"})
    
    assert any(
        name == "error" and data.get("code") == "agent_max_iterations"
        for name, data in events
    )
    assert calls == ["probe_steps", "probe_steps"]

    run = await _wait_chat_run(runtime)
    assert run is not None, "没跑完的单聊必须留下可续跑的现场"
    assert run.status == "incomplete"
    assert run.step == 2
    assert run.last_action == "探针"
    assert run.session_id

    listed = (await client.get("/v1/runs")).json()["runs"]
    item = next(entry for entry in listed if entry["id"] == run.id)
    
    assert "没做完" in item["summary"]
    assert "上限" in item["summary"]

    resumed = (await client.post(f"/v1/runs/{run.id}/resume")).json()
    assert resumed["kind"] == "chat"
    assert resumed["session_id"] == run.session_id
    
    assert "续跑" in resumed["topic"] and "不要重做" in resumed["topic"]
    
    assert await _chat_runs(runtime) == []


class _SlowLLM(FakeLLM):








    def __init__(self) -> None:
        super().__init__([])

    async def stream(  
        self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling
    ):
        for _ in range(500):
            await asyncio.sleep(0.05)
            yield StreamChunk(delta="…")


@pytest.mark.asyncio
async def test_user_stop_keeps_a_resumable_run(runtime, client):






    install_fake_model(runtime, _SlowLLM())

    stopped_once = False
    
    
    
    
    
    
    
    async with client.stream(
        "POST", "/v1/chat", json={"message": "慢慢说", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if current == "meta":
                result = await client.post("/v1/stop", json={"task_id": data["task_id"]})
                assert result.json()["cancelled"] == 1
                stopped_once = True
            current = None

    assert stopped_once, "没读到 meta 事件，说明这次停止根本没发生（下面的断言就不可信了）"

    run = await _wait_chat_run(runtime)
    assert run is not None, "被停下的单聊同样要留下现场（用户常常只是按错了）"
    assert run.status == "cancelled"
    assert run.session_id
