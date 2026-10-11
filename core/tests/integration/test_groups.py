"""AI 群的集成测试：建群 + 群聊轮转接话 + 自主讨论投票收敛。"""

import json

from my_agent.config.schemas import GroupProfile
from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM

from .conftest import install_fake_model


async def _read_discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:
    """消费一次群讨论的 SSE 流，返回 [(event, data), ...]。"""
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
    """搭子自主讨论：一方发起结束投票、另一方同意 → 发起者做总结。"""
    llm = FakeLLM(
        [
            "我建议用方案 A，更稳妥。\n[END_VOTE]",  # soulmate 发起结束投票
            "同意结束，方案 A 可以。\n[AGREE]",  # LoveBuddy 投票同意
            "结论：采用方案 A。理由是风险更低、落地更快。",  # soulmate 总结
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
    # 总结内容来自发起投票的那个搭子
    summary = next(data for name, data in events if name == "summary")
    assert summary["assistant_id"] == "soulmate"
    assert "方案 A" in summary["content"]


async def test_group_discuss_respects_speaking_order(runtime, client):
    """发言顺序可按 speaking_order 设置（LoveBuddy 先于 soulmate）。"""
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
    """两个搭子按加入顺序轮流接话：后发言者能看到前文。"""
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

    # 第二个搭子生成回复时，上下文里应包含第一个搭子的发言（轮转接话的关键）
    second_call = llm.calls[1]
    second_prompt = "".join(msg.content for msg in second_call)
    assert "我是办公搭子的回复" in second_prompt


async def test_group_wake_words_seed_and_update(runtime, client):
    """群的语音唤醒词：建群零配置就能喊，之后可改、可清空。"""
    created = await client.post(
        "/v1/groups", json={"name": "学习计划讨论组", "member_assistant_ids": ["soulmate"]}
    )
    assert created.status_code == 200
    group = created.json()

    # ① 建群零配置就能喊：出厂哨兵值被换成「你好 + 群名」
    assert group["wake_words"] == ["你好学习计划讨论组"]

    # ② 用户改成自己的说法：去空白、去重、丢掉空串
    renamed = await client.patch(
        f"/v1/groups/{group['id']}", json={"wake_words": [" 学习组 ", "学习组", ""]}
    )
    assert renamed.status_code == 200
    assert renamed.json()["wake_words"] == ["学习组"]

    # ③ 不传 = 不动（与其它字段同一套 model_fields_set 判据）
    untouched = await client.patch(f"/v1/groups/{group['id']}", json={"name": "改个名"})
    assert untouched.json()["wake_words"] == ["学习组"]

    # ④ 空列表 = **明确不要唤醒词**，不是"清回默认"
    #    （这条是刻意的语义：用户把词删光的意思不可能是"帮我再生成一个吧"）
    cleared = await client.patch(f"/v1/groups/{group['id']}", json={"wake_words": []})
    assert cleared.json()["wake_words"] == []


def test_group_wake_words_backfill_for_existing_config():
    """老配置（`groups.json` 里还没有 wake_words 这个键）也要能喊。

    ⚠️ 这是本次改动最容易出事的一处：如果只给**新建**的群补词，用户升级后所有
    老群会停在出厂哨兵值「你好群聊」上 —— 喊一句会随机落进其中一个，而"进错了
    群"和"没反应"用户都无从排查。所以补词必须挂在 model 层（读配置就过一遍）。
    """
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
