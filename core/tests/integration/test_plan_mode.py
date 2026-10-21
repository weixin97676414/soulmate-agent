













from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.llm.base import LLMResponse

from ..conftest import FakeLLM, tool_call
from .conftest import install_fake_model, read_sse




MULTI_STEP = "帮我做一份月度报告，然后整理成表格，再分别导出对比"

PLAN_JSON = '{"goal": "出一份月度报告", "steps": ["拉取数据", "整理成表格", "导出对比"]}'
REVISED_PLAN_JSON = (
    '{"goal": "出一份月度报告", "steps": ["拉取数据", "整理成表格", "画趋势图", "导出对比"]}'
)


async def _chat_with_decider(client, payload: dict, decider) -> list[tuple[str, dict]]:





    events: list[tuple[str, dict]] = []
    async with client.stream("POST", "/v1/chat", json=payload) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                data = json.loads(line[6:])
                events.append((current, data))
                if current == "plan" and data.get("state") == "awaiting":
                    approved, feedback = decider(data, events)
                    answer = await client.post(
                        "/v1/plan/decision",
                        json={
                            "plan_id": data["id"],
                            "approved": approved,
                            "feedback": feedback,
                        },
                    )
                    assert answer.status_code == 200, await answer.aread()
                current = None
    return events


def _plans(events: list[tuple[str, dict]]) -> list[dict]:
    return [data for name, data in events if name == "plan"]


@pytest.mark.asyncio
async def test_plan_waits_for_approval_before_any_tool(runtime, client):

    fake = FakeLLM(
        [
            LLMResponse(content=PLAN_JSON, finish_reason="stop"),
            LLMResponse(
                content="",
                
                tool_calls=[
                    tool_call("plan_update", {"step": "1", "status": "done"}),
                    tool_call("plan_update", {"step": "2", "status": "done"}),
                    tool_call("plan_update", {"step": "3", "status": "done"}),
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="报告已经出好了。", finish_reason="stop"),
        ]
    )
    install_fake_model(runtime, fake)

    def decider(plan, events):
        
        assert not [name for name, _ in events if name == "tool_call"]
        assert plan["state"] == "awaiting"
        assert [step["status"] for step in plan["steps"]] == ["pending"] * 3
        return True, ""

    events = await _chat_with_decider(
        client, {"message": MULTI_STEP, "model_id": "fake"}, decider
    )

    plans = _plans(events)
    assert [plan["state"] for plan in plans] == ["awaiting", "executing"]

    updates = [data for name, data in events if name == "plan_update"]
    assert updates, "执行中的进度要广播出来，否则卡片不会打勾"
    assert updates[0]["steps"][0]["status"] == "done"
    
    assert updates[-1]["state"] == "done"

    
    text = "".join(data.get("text", "") for name, data in events if name == "delta")
    assert "已经出好" in text, text


@pytest.mark.asyncio
async def test_revision_regenerates_plan_with_feedback(runtime, client):

    fake = FakeLLM(
        [
            LLMResponse(content=PLAN_JSON, finish_reason="stop"),
            LLMResponse(content=REVISED_PLAN_JSON, finish_reason="stop"),
            LLMResponse(content="好，按新计划来。", finish_reason="stop"),
        ]
    )
    install_fake_model(runtime, fake)

    seen: list[dict] = []

    def decider(plan, events):
        seen.append(plan)
        if len(seen) == 1:
            return False, "第 2 步换成画趋势图"
        return True, ""

    events = await _chat_with_decider(
        client, {"message": MULTI_STEP, "model_id": "fake"}, decider
    )

    plans = _plans(events)
    assert [plan["state"] for plan in plans] == ["awaiting", "awaiting", "executing"]
    assert plans[0]["id"] != plans[1]["id"], "重拟必须换 id，否则旧卡片上的按钮还能唤醒新计划"
    assert len(plans[1]["steps"]) == 4, "第二版应当是重拟出来的那一份"

    
    revise_request = fake.calls[1]
    assert "第 2 步换成画趋势图" in revise_request[-1].content


@pytest.mark.asyncio
async def test_abort_stops_without_running_tools(runtime, client):

    
    fake = FakeLLM([LLMResponse(content=PLAN_JSON, finish_reason="stop")])
    install_fake_model(runtime, fake)

    events = await _chat_with_decider(
        client, {"message": MULTI_STEP, "model_id": "fake"}, lambda plan, events: (False, "")
    )

    plans = _plans(events)
    assert [plan["state"] for plan in plans] == ["awaiting", "aborted"]
    assert not [name for name, _ in events if name == "tool_call"]

    text = "".join(data.get("text", "") for name, data in events if name == "delta")
    assert text.strip(), "用户消息后面必须有个回应，不能留下'没人搭理'"


@pytest.mark.asyncio
async def test_bad_step_number_is_refused_with_available_steps(runtime, client):

    fake = FakeLLM(
        [
            LLMResponse(content=PLAN_JSON, finish_reason="stop"),
            LLMResponse(
                content="",
                tool_calls=[tool_call("plan_update", {"step": "9", "status": "done"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="好了。", finish_reason="stop"),
        ]
    )
    install_fake_model(runtime, fake)

    events = await _chat_with_decider(
        client, {"message": MULTI_STEP, "model_id": "fake"}, lambda plan, events: (True, "")
    )

    results = [data for name, data in events if name == "tool_result"]
    assert results, "工具结果要回填给模型"
    assert "可用的步号" in json.dumps(results[0], ensure_ascii=False)
    
    assert not [name for name, _ in events if name == "plan_update"]


@pytest.mark.asyncio
async def test_simple_chat_gets_no_plan(runtime, client):

    fake = FakeLLM([LLMResponse(content="你好呀，需要我做什么？", finish_reason="stop")])
    install_fake_model(runtime, fake)

    events = await read_sse(client, {"message": "你好", "model_id": "fake"})

    assert not _plans(events)
    assert len(fake.calls) == 1, "简单任务不该白白多跑一次规划"


@pytest.mark.asyncio
async def test_plan_is_persisted_with_the_message(runtime, client):

    fake = FakeLLM(
        [
            LLMResponse(content=PLAN_JSON, finish_reason="stop"),
            LLMResponse(
                content="",
                tool_calls=[tool_call("plan_update", {"step": "1", "status": "done"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="报告已经出好了。", finish_reason="stop"),
        ]
    )
    install_fake_model(runtime, fake)

    events = await _chat_with_decider(
        client, {"message": MULTI_STEP, "model_id": "fake"}, lambda plan, events: (True, "")
    )

    session_id = next(data["session_id"] for name, data in events if name == "meta")
    
    stored: list[dict] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 15
    while loop.time() < deadline and not stored:
        payload = (await client.get(f"/v1/sessions/{session_id}/messages")).json()
        stored = [m for m in payload["messages"] if m.get("plan")]
        if not stored:
            await asyncio.sleep(0.05)

    assert stored, "计划必须随消息落库，否则重开对话就看不到卡片了"
    plan = stored[0]["plan"]
    assert plan["goal"] == "出一份月度报告"
    assert plan["steps"][0]["status"] == "done"
    assert len(plan["steps"]) == 3
