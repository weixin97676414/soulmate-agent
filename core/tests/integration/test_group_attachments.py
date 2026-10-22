







from __future__ import annotations

import json

from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM

from .conftest import install_fake_model


async def _upload(client, name: str, content: bytes, mime: str) -> str:
    response = await client.post(
        "/v1/files/upload",
        files={"file": (name, content, mime)},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _discuss(client, group_id: str, payload: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", f"/v1/groups/{group_id}/discuss", json=payload
    ) as response:
        assert response.status_code == 200, await response.aread()
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[len("data: ") :])))
    return events


async def _make_group(client, name: str = "附件测试群") -> dict:
    created = await client.post(
        "/v1/groups", json={"name": name, "member_assistant_ids": ["soulmate", "LoveBuddy"]}
    )
    assert created.status_code == 200, created.text
    return created.json()


def _seen_text(llm: FakeLLM) -> str:

    return "\n".join("".join(message.content for message in call) for call in llm.calls)


async def test_attachment_reaches_every_member(runtime, client):

    llm = FakeLLM(
        [
            "我看了附件，先说说结构。\n[END_VOTE]",
            "同意，附件里的数据我也看了。\n[AGREE]",
            "结论：附件已确认。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _make_group(client)
    file_id = await _upload(client, "需求说明.md", "# 需求\n要点一".encode(), "text/markdown")

    events = await _discuss(
        client, group["id"], {"topic": "按附件里的需求讨论", "attachments": [file_id]}
    )

    assert "topic" in [name for name, _ in events]
    
    topic = next(data for name, data in events if name == "topic")
    assert topic["content"] == "按附件里的需求讨论"
    assert "需求说明.md" not in topic["content"]

    seen = _seen_text(llm)
    assert "需求说明.md" in seen, "附件信息没有进入成员的上下文"


async def test_image_reaches_members(runtime, client):

    llm = FakeLLM(["图上有个错别字。\n[END_VOTE]", "同意。\n[AGREE]", "结论：已确认。"])
    install_fake_model(runtime, llm)
    group = await _make_group(client, "图片测试群")

    
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    file_id = await _upload(client, "截图.png", png, "image/png")

    await _discuss(client, group["id"], {"topic": "看图", "images": [file_id]})

    
    
    
    assert llm.calls, "带图讨论没有调用模型"


async def test_unknown_attachment_does_not_break_the_discussion(runtime, client):

    llm = FakeLLM(["我们直接聊。\n[END_VOTE]", "同意。\n[AGREE]", "结论：聊完了。"])
    install_fake_model(runtime, llm)
    group = await _make_group(client, "坏附件群")

    events = await _discuss(
        client, group["id"], {"topic": "聊聊", "attachments": ["不存在的文件id"]}
    )

    assert "done" in [name for name, _ in events]


async def test_summary_also_sees_the_attachments(runtime, client):

    llm = FakeLLM(
        [
            LLMResponse(content="先看附件。", finish_reason="stop"),
            "我同意结束。\n[AGREE]",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _make_group(client, "总结附件群")
    file_id = await _upload(client, "季度数据.csv", b"a,b\n1,2\n", "text/csv")

    await _discuss(
        client,
        group["id"],
        {"topic": "按季度数据总结", "attachments": [file_id]},
    )

    assert "季度数据.csv" in _seen_text(llm)
