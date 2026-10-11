"""单聊计划模式：多步任务先出计划，用户点头才动手。

这组守四件事，任何一件坏了用户都会当场发现：

1. **未确认不动手** —— 计划卡片出来之后、用户点「开始执行」之前，一个工具都不能跑。
   这是整个模式的立身之本：能看见却不拦人，等于又退回了"AI 自己决定要不要跳过"。
2. **改一下能重拟** —— 带意见回传后出**新**计划（新 id），旧卡片上的按钮随即失效，
   免得用户点着上一版的「开始执行」把中间一版执行了。
3. **不用了真停** —— 用户放弃时助手补一句回应。不留这一句，重开对话看到的就是
   "说了话却没人搭理"。
4. **进度如实** —— ``plan_update`` 把某步标成 done 会让卡片打勾；步号写错则明确拒绝
   并给出可用步号（不让模型一路错着汇报完）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.llm.base import LLMResponse

from ..conftest import FakeLLM, tool_call
from .conftest import install_fake_model, read_sse

# 这句话要能让 should_plan 判定成多步任务（复用 ModelRouter 的零成本启发式）。
# 换句子时先确认 score_complexity 仍 >= 4，否则用例会以"没有 plan 事件"这种
# 看不出原因的姿势失败。
MULTI_STEP = "帮我做一份月度报告，然后整理成表格，再分别导出对比"

PLAN_JSON = '{"goal": "出一份月度报告", "steps": ["拉取数据", "整理成表格", "导出对比"]}'
REVISED_PLAN_JSON = (
    '{"goal": "出一份月度报告", "steps": ["拉取数据", "整理成表格", "画趋势图", "导出对比"]}'
)


async def _chat_with_decider(client, payload: dict, decider) -> list[tuple[str, dict]]:
    """跑一次单聊，并在每份"等待确认"的计划上调用 ``decider(plan, events)``。

    ``decider`` 收到的是**到那一刻为止**的全部事件 —— 「未确认之前有没有偷偷
    动过工具」这类断言只能在这个时点上做。
    """
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
    """计划只是提议：用户点头之前不做任何事。"""
    fake = FakeLLM(
        [
            LLMResponse(content=PLAN_JSON, finish_reason="stop"),
            LLMResponse(
                content="",
                # 三步一次性汇报完：顺带验证"全部收工后计划自己收尾"这条
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
        # 走到这里说明前端已经收到计划卡片 —— 而此刻必须一个工具都没跑过
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
    # 三步都收工后整份计划应当自己收尾（前端据此把徽章换成"已完成"）
    assert updates[-1]["state"] == "done"

    # 流式输出是逐字推的（见 engine 的 delta 事件），要拼起来再看
    text = "".join(data.get("text", "") for name, data in events if name == "delta")
    assert "已经出好" in text, text


@pytest.mark.asyncio
async def test_revision_regenerates_plan_with_feedback(runtime, client):
    """「改一下」：带着用户意见重拟，出新 id，旧卡片失效。"""
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

    # 用户的意见真的传到了规划请求里（否则"改一下"是个摆设）
    revise_request = fake.calls[1]
    assert "第 2 步换成画趋势图" in revise_request[-1].content


@pytest.mark.asyncio
async def test_abort_stops_without_running_tools(runtime, client):
    """「不用了」：一步都不做，但要留一句回应。"""
    # 只给规划那一条：一旦有工具被调用，FakeLLM 会用光剧本继续跑，用例就会露馅
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
    """步号写错：明确拒绝并给出可用步号，不假装成功。"""
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
    # 没有生效就不该有进度事件（否则卡片会跟着乱跳）
    assert not [name for name, _ in events if name == "plan_update"]


@pytest.mark.asyncio
async def test_simple_chat_gets_no_plan(runtime, client):
    """简单问答直接回答：不出计划卡片、也不多花一次规划调用。"""
    fake = FakeLLM([LLMResponse(content="你好呀，需要我做什么？", finish_reason="stop")])
    install_fake_model(runtime, fake)

    events = await read_sse(client, {"message": "你好", "model_id": "fake"})

    assert not _plans(events)
    assert len(fake.calls) == 1, "简单任务不该白白多跑一次规划"


@pytest.mark.asyncio
async def test_plan_is_persisted_with_the_message(runtime, client):
    """计划随消息存进会话：重开对话还能看到当时的分步与完成情况。"""
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
    # 落盘发生在响应生成器的 finally 里，与"读到流结束"不同步，必须轮询
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
