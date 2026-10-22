










from __future__ import annotations

import json

from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM, tool_call

from .conftest import install_fake_model


async def _create_group(client, *, name: str, members: list[str] | None = None) -> dict:
    created = await client.post(
        "/v1/groups",
        json={
            "name": name,
            "member_assistant_ids": members or ["RelationBuddy", "soulmate", "LoveBuddy"],
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", f"/v1/groups/{group_id}/discuss", json={"topic": topic}) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((current, json.loads(line[len("data: ") :])))
    return events


async def test_only_initiator_or_last_speaker_can_end_vote(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                "总管先说：这活分给第二位。",  
                "我也来收个尾。\n[END_VOTE]",  
                "同意收尾。\n[AGREE]",  
                "结论：按上面的来。",
            ]
        ),
    )
    group = await _create_group(client, name="投票权限群")

    events = await _discuss(client, group["id"], "商量一下这周的安排")

    kinds = [name for name, _ in events]
    denied = [data for name, data in events if name == "vote_denied"]
    assert denied, f"中间那位越权发起应当被明确拒绝：{kinds}"
    assert "末序发言者" in denied[0]["reason"]
    assert "vote_request" not in kinds, "被拒的那次不该真的发起投票"


async def test_reviewer_can_reject_and_discussion_continues(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                "总管：交付内容我安排给别人了。",  
                "我做完了这部分。",  
                "交付不完整，缺依据。\n[REJECT] 请补上数据来源。",  
                "收到，我重新安排并补上来源。",  
                "补齐了。",
                "这份可以了。\n[PASS]",
                "结论：已补齐并验收通过。",
            ]
        ),
    )
    group = await _create_group(client, name="审核打回群")

    events = await _discuss(client, group["id"], "做一份材料")

    reviews = [data for name, data in events if name == "review"]
    assert reviews, f"审核结论应当作为事件给出：{[n for n, _ in events]}"
    assert reviews[0]["passed"] is False
    assert "数据来源" in reviews[0]["reason"], "打回理由要带上，总管才有得照着改"
    
    assert any(name == "message" for name, _ in events[3:]), "打回后应当继续讨论"


async def test_out_of_scope_is_visible(runtime, client):

    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="only_reviewer_tool",
        display_name="只有审核员该用的工具",
        description="测试用",
        permission_level="safe",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  
            return "ok"

    runtime.skills.register(_Probe)
    
    
    
    runtime.skills.get("only_reviewer_tool").meta.source = "custom"

    install_fake_model(
        runtime,
        FakeLLM(
            [
                
                "我来安排。",
                
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("only_reviewer_tool", {})],
                    finish_reason="tool_calls",
                ),
                "顺手做了。",
                "我看看。\n[PASS]",
                "结论：完成。",
            ]
        ),
    )
    
    
    
    created = await client.post(
        "/v1/assistants",
        json={"id": "probe", "name": "越权探针", "enabled_skills": ["kb_search"]},
    )
    assert created.status_code == 200, created.text
    group = await _create_group(
        client, name="越权群", members=["RelationBuddy", "probe", "LoveBuddy"]
    )

    events = await _discuss(client, group["id"], "随便做点什么")

    flagged = [data for name, data in events if name == "out_of_scope"]
    assert flagged, f"越权调用应当被标出来：{[name for name, _ in events]}"
    assert flagged[0]["skill"] == "only_reviewer_tool"
    assert flagged[0]["name"], "要说清是谁越的界"
    
    assert "owners" in flagged[0]
