













from __future__ import annotations

import asyncio
import json

from my_agent.agent.group_discussion import build_group_agent as _build_group_agent
from my_agent.config.schemas import GroupProfile
from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM, tool_call

from .conftest import event_collector, install_fake_model, wait_for


def register_probe_skill(runtime, calls: list[str], *, name: str = "write_note") -> None:





    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name=name,
        display_name="写便签",
        description="写一条便签（测试用）",
        permission_level="confirm",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  
            calls.append(name)
            return "写入成功"

    runtime.skills.register(_Probe)


async def _create_group(client, *, name: str = "确认测试群") -> dict:
    created = await client.post(
        "/v1/groups",
        json={"name": name, "member_assistant_ids": ["soulmate", "LoveBuddy"]},
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _consume_discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:

    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", f"/v1/groups/{group_id}/discuss", json={"topic": topic}
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        event = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[len("data: ") :])))
    return events


async def test_group_discuss_asks_for_confirmation_and_continues(runtime, client):

    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "会议纪要"})],
                finish_reason="tool_calls",
            ),
            "便签写好了。\n[END_VOTE]",
            "同意结束。\n[AGREE]",
            "结论：便签已写好。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client)

    async with event_collector(client) as events:
        discuss = asyncio.create_task(_consume_discuss(client, group["id"], "帮我记一下"))

        asked = await wait_for(
            lambda: any(name == "permission_request" for name, _ in events), timeout=10
        )
        assert asked, f"群聊里没有弹出确认请求，收到的事件：{[n for n, _ in events]}"

        data = next(payload for name, payload in events if name == "permission_request")
        
        assert data["skill_name"] == "write_note"
        assert data["group_id"] == group["id"]
        assert data["assistant_id"] == "soulmate"

        await client.post(
            "/v1/confirm", json={"request_id": data["request_id"], "approved": True}
        )
        seen = await asyncio.wait_for(discuss, timeout=20)

    assert calls == ["write_note"], "批准之后技能应当真的执行了"
    kinds = [name for name, _ in seen]
    assert "summary" in kinds, f"讨论应当继续到总结：{kinds}"


async def test_group_discuss_denied_keeps_going(runtime, client):





    calls: list[str] = []
    register_probe_skill(runtime, calls, name="write_note")
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "x"})],
                finish_reason="tool_calls",
            ),
            "那我先不写了，我们继续讨论。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：先不动。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="拒绝测试群")

    async with event_collector(client) as events:
        discuss = asyncio.create_task(_consume_discuss(client, group["id"], "记一下"))
        assert await wait_for(
            lambda: any(name == "permission_request" for name, _ in events), timeout=10
        )
        data = next(payload for name, payload in events if name == "permission_request")
        await client.post(
            "/v1/confirm", json={"request_id": data["request_id"], "approved": False}
        )
        seen = await asyncio.wait_for(discuss, timeout=20)

    assert calls == [], "被拒绝的技能绝不能执行"
    assert "summary" in [name for name, _ in seen], "拒绝不等于讨论中断"


async def test_group_auto_approve_skips_the_dialog(runtime, client):

    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "y"})],
                finish_reason="tool_calls",
            ),
            "写好了。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：写好了。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="自动批准群")

    patched = await client.patch(
        f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["confirm_mode"] == "auto_approve"

    async with event_collector(client) as events:
        await _consume_discuss(client, group["id"], "记一下")

    assert calls == ["write_note"], "一律批准时技能应当直接执行"
    assert not [name for name, _ in events if name == "permission_request"], "不该再弹窗"


async def test_group_confirm_does_not_bypass_admin_level(runtime, client):





    calls: list[str] = []

    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="danger_delete",
        display_name="删除全部数据",
        description="测试用的高危技能",
        permission_level="admin",
    )
    class _Danger(BaseSkill):
        async def run(self, ctx, **params):  
            calls.append("danger_delete")
            return "已删除"

    runtime.skills.register(_Danger)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("danger_delete", {})],
                finish_reason="tool_calls",
            ),
            "好。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：没做。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="高危群")
    await client.patch(f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"})

    async with event_collector(client) as events:
        await _consume_discuss(client, group["id"], "清空数据")

    assert calls == [], "admin 级绝不能因为群级开关而免确认"
    assert not [name for name, _ in events if name == "permission_request"], (
        "当前实现里 admin 级在未开启该能力时直接拒绝，也不会弹窗"
    )


def test_group_level_settings_override_members(runtime):

    
    install_fake_model(runtime, FakeLLM([]))
    group = make_group("覆盖测试群")
    member = runtime.assistants.get("soulmate")
    assert member is not None

    
    member = member.model_copy(update={"reasoning_effort": "high"})
    scoped = group.model_copy(update={"reasoning_effort": "low"})

    agent = _build_group_agent(runtime, scoped, member, history=[])
    assert agent.config.reasoning_effort == "low"

    
    
    
    
    
    
    cleared = group.model_copy(update={"reasoning_effort": None})
    fallback = _build_group_agent(runtime, cleared, member, history=[])
    assert fallback.config.reasoning_effort == "high"


def test_group_agent_has_confirm_channel(runtime):

    install_fake_model(runtime, FakeLLM([]))
    group = make_group("通道测试群")
    member = runtime.assistants.get("soulmate")
    assert member is not None

    agent = _build_group_agent(runtime, group, member, history=[])
    assert agent.ctx.has_confirm_channel is True

    scoped = group.model_copy(update={"confirm_mode": "auto_approve"})
    scoped_agent = _build_group_agent(runtime, scoped, member, history=[])
    
    
    
    assert runtime.skills.guard.effective_mode(scoped_agent.ctx) == "auto_approve"


async def test_group_patch_supports_partial_updates(client):

    group = await _create_group(client, name="补丁群")

    first = await client.patch(
        f"/v1/groups/{group['id']}",
        json={"reasoning_effort": "high", "confirm_mode": "auto_approve"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["reasoning_effort"] == "high"
    assert first.json()["confirm_mode"] == "auto_approve"
    
    assert first.json()["name"] == "补丁群"

    second = await client.patch(
        f"/v1/groups/{group['id']}", json={"reasoning_effort": ""}
    )
    assert second.json()["reasoning_effort"] is None, "空串应当清回「跟随成员」"
    assert second.json()["confirm_mode"] == "auto_approve", "没传的字段不能被顺手清掉"

    unknown = await client.patch("/v1/groups/nope", json={"name": "x"})
    assert unknown.status_code == 404


async def test_cancelled_discussion_leaves_no_pending_confirm(runtime, client):





    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "z"})],
                finish_reason="tool_calls",
            ),
            "写好了",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="取消测试群")

    async with event_collector(client) as events:
        async with client.stream(
            "POST", f"/v1/groups/{group['id']}/discuss", json={"topic": "记一下"}
        ) as resp:
            assert resp.status_code == 200
            assert await wait_for(
                lambda: any(name == "permission_request" for name, _ in events), timeout=10
            )
            assert runtime.pending_confirms, "此刻应当有一个等待中的确认"
            
            await resp.aclose()

        assert await wait_for(lambda: not runtime.pending_confirms, timeout=10), (
            "讨论被叫停后，挂起的确认必须被收起"
        )

    assert calls == [], "被叫停的讨论不该把技能跑完"


def make_group(name: str) -> GroupProfile:





    return GroupProfile(id="g-test", name=name, member_assistant_ids=["soulmate", "LoveBuddy"])





async def test_群权限设置不会影响单聊(runtime, client):















    before = runtime.assistant_confirm_mode("soulmate")

    group = await _create_group(client, name="权限隔离测试群")
    
    patched = await client.patch(
        f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["confirm_mode"] == "auto_approve"

    
    after = runtime.assistant_confirm_mode("soulmate")
    assert after == before, (
        "群级权限设置泄漏到单聊了 —— 单聊读的应当是搭子档案 / 全局，不能读群"
    )
    assert after != "auto_approve", "单聊这边的取值不可能是群刚才设的那个"


async def test_群思考强度默认是中(runtime, client):






    group = await _create_group(client, name="思考强度默认值测试群")
    assert group["reasoning_effort"] == "medium"

    
    cleared = await client.patch(
        f"/v1/groups/{group['id']}", json={"reasoning_effort": ""}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["reasoning_effort"] is None
