
















from __future__ import annotations

import json

from tests.conftest import FakeLLM

from .conftest import install_fake_model


async def _create_group(client, *, name: str, members: list[str]) -> dict:
    created = await client.post(
        "/v1/groups",
        json={"name": name, "member_assistant_ids": members},
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", f"/v1/groups/{group_id}/discuss", json={"topic": topic}
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((current, json.loads(line[len("data: ") :])))
    return events


async def test_summary_goes_to_first_speaker_not_vote_initiator(runtime, client):





    install_fake_model(
        runtime,
        FakeLLM(
            [
                "总管先说：这事分两步做。",  
                "我补充一点数据。",  
                "差不多可以收尾了。\n[END_VOTE]",  
                "同意收尾。\n[AGREE]",  
                "结论：按两步做，数据以补充的那份为准。",  
            ]
        ),
    )
    group = await _create_group(
        client, name="总结人判据群", members=["RelationBuddy", "soulmate", "LoveBuddy"]
    )

    events = await _discuss(client, group["id"], "商量一下这周的安排")
    kinds = [name for name, _ in events]

    
    assert "vote_result" in kinds, f"应当出现投票结果：{kinds}"
    result = next(data for name, data in events if name == "vote_result")
    assert result["passed"] is True

    
    summaries = [data for name, data in events if name == "summary"]
    assert summaries, f"应当产出最终总结：{kinds}"
    assert summaries[0]["assistant_id"] == "RelationBuddy", (
        "总结必须由首位发言者（会话发起人）做；"
        f"而不是发起结束投票的人（拿到的是 {summaries[0]['assistant_id']}）"
    )

    
    assert result["summary_by"]["assistant_id"] == "RelationBuddy"
    assert result["summary_by"]["name"]


async def test_speaker_event_no_longer_flags_the_summary(runtime, client):






    install_fake_model(
        runtime,
        FakeLLM(
            [
                "我来安排。",
                "同意，没问题。",
                "收尾吧。\n[END_VOTE]",
                "同意。\n[AGREE]",
                "结论：完成。",
            ]
        ),
    )
    group = await _create_group(
        client, name="标识时机群", members=["RelationBuddy", "soulmate", "LoveBuddy"]
    )

    events = await _discuss(client, group["id"], "随便聊两句")

    speakers = [data for name, data in events if name == "speaker"]
    assert speakers, "应当有发言人事件"
    assert not any(item.get("summary") for item in speakers), (
        "`speaker` 不该再带 summary 标志 —— 标识要等真的产出总结（`summary` 事件）才打"
    )
    assert any(name == "summary" for name, _ in events), "总结本身照旧要有"


async def test_review_pass_ends_discussion_and_summarizes(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                "我来安排：两步。",  
                "我做完了第一步。",  
                "可以了，验收通过。\n[PASS]",  
                "结论：完成，两步都过了。",  
            ]
        ),
    )
    group = await _create_group(
        client, name="验收通过即收尾群", members=["RelationBuddy", "soulmate", "LoveBuddy"]
    )

    events = await _discuss(client, group["id"], "做一份材料")
    kinds = [name for name, _ in events]

    reviews = [data for name, data in events if name == "review"]
    assert reviews, f"审核结论要作为事件给出：{kinds}"
    assert reviews[0]["passed"] is True
    
    assert reviews[0]["summary_by"]["assistant_id"] == "RelationBuddy"

    review_at = kinds.index("review")
    after = kinds[review_at + 1 :]
    
    speakers_after = [
        data["assistant_id"] for name, data in events[review_at + 1 :] if name == "speaker"
    ]
    assert speakers_after == ["RelationBuddy"], (
        f"验收通过后只应轮到总结人说话，实际：{speakers_after}"
    )
    
    assert "summary" in after, f"验收通过后应当直接产出总结：{after}"
    done = next(data for name, data in events if name == "done")
    assert done["reason"] == "review_passed", (
        "结束原因不能复用 `max_rounds` —— 后台群聊用它判'没跑完'"
    )
