

import json

from my_agent.config.schemas import GroupProfile
from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM

from .conftest import install_fake_model


async def _read_discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:

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


async def test_group_discuss_votes_then_summary(runtime, client):

    llm = FakeLLM(
        [
            "我建议用方案 A，更稳妥。\n[END_VOTE]",  
            "同意结束，方案 A 可以。\n[AGREE]",  
            "结论：采用方案 A。理由是风险更低、落地更快。",  
        ]
    )
    install_fake_model(runtime, llm)

    created = await client.post(
        "/v1/groups",
        json={"name": "讨论组", "member_assistant_ids": ["soulmate", "LoveBuddy"]},
    )
    group = created.json()

    events = await _read_discuss(client, group["id"], "选哪个方案？")
    kinds = [name for name, _ in events]

    assert "topic" in kinds
    assert "speaker" in kinds
    assert "vote_request" in kinds
    assert "vote" in kinds
    assert "summary" in kinds
    assert kinds[-1] == "done"
    
    summary = next(data for name, data in events if name == "summary")
    assert summary["assistant_id"] == "soulmate"
    assert "方案 A" in summary["content"]


async def test_group_discuss_respects_speaking_order(runtime, client):

    llm = FakeLLM(["LoveBuddy 先发言\n[END_VOTE]", "同意\n[AGREE]", "总结：结束"])
    install_fake_model(runtime, llm)

    created = await client.post(
        "/v1/groups",
        json={
            "name": "排序组",
            "member_assistant_ids": ["soulmate", "LoveBuddy"],
            "speaking_order": ["LoveBuddy", "soulmate"],
        },
    )
    group = created.json()
    events = await _read_discuss(client, group["id"], "随便聊聊")
    first_speaker = next(data for name, data in events if name == "speaker")
    assert first_speaker["assistant_id"] == "LoveBuddy"


async def test_group_chat_round_robin(runtime, client):

    llm = FakeLLM(
        [
            LLMResponse(content="我是办公搭子的回复", finish_reason="stop"),
            LLMResponse(content="我是生活搭子的回复", finish_reason="stop"),
        ]
    )
    install_fake_model(runtime, llm)

    created = await client.post(
        "/v1/groups",
        json={"name": "测试群", "member_assistant_ids": ["soulmate", "LoveBuddy"]},
    )
    assert created.status_code == 200
    group = created.json()

    resp = await client.post(f"/v1/groups/{group['id']}/chat", json={"message": "你好"})
    assert resp.status_code == 200
    replies = resp.json()["replies"]

    assert [item["assistant_id"] for item in replies] == ["soulmate", "LoveBuddy"]
    assert replies[0]["content"] == "我是办公搭子的回复"
    assert replies[1]["content"] == "我是生活搭子的回复"

    
    second_call = llm.calls[1]
    second_prompt = "".join(msg.content for msg in second_call)
    assert "我是办公搭子的回复" in second_prompt


async def test_group_wake_words_seed_and_update(runtime, client):

    created = await client.post(
        "/v1/groups", json={"name": "学习计划讨论组", "member_assistant_ids": ["soulmate"]}
    )
    assert created.status_code == 200
    group = created.json()

    
    assert group["wake_words"] == ["你好学习计划讨论组"]

    
    renamed = await client.patch(
        f"/v1/groups/{group['id']}", json={"wake_words": [" 学习组 ", "学习组", ""]}
    )
    assert renamed.status_code == 200
    assert renamed.json()["wake_words"] == ["学习组"]

    
    untouched = await client.patch(f"/v1/groups/{group['id']}", json={"name": "改个名"})
    assert untouched.json()["wake_words"] == ["学习组"]

    
    
    cleared = await client.patch(f"/v1/groups/{group['id']}", json={"wake_words": []})
    assert cleared.json()["wake_words"] == []


def test_group_wake_words_backfill_for_existing_config():






    profile = GroupProfile(id="g1", name="产品讨论组")

    assert profile.wake_words == ["你好产品讨论组"]


async def test_group_create_rejects_unknown_member(runtime, client):
    resp = await client.post(
        "/v1/groups", json={"name": "坏群", "member_assistant_ids": ["不存在的搭子"]}
    )
    assert resp.status_code == 400


async def test_group_list_and_delete(runtime, client):
    created = await client.post(
        "/v1/groups", json={"name": "临时群", "member_assistant_ids": ["soulmate"]}
    )
    assert created.status_code == 200
    group = created.json()

    listed = await client.get("/v1/groups")
    assert any(item["id"] == group["id"] for item in listed.json()["groups"])

    deleted = await client.delete(f"/v1/groups/{group['id']}")
    assert deleted.status_code == 200

    again = await client.get("/v1/groups")
    assert all(item["id"] != group["id"] for item in again.json()["groups"])
