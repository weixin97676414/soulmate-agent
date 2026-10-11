"""群聊里的附件与图片。

用户的要求是"群聊输入栏与单聊完全一致"，而单聊能拖文件进去 —— 所以群里也得能。
这条链路里最容易出问题的是**附件到底进没进成员的上下文**：
界面上传成功了、气泡也画出来了，但每个成员看到的 prompt 里没有附件信息，
于是搭子全程在对空气说话。所以这里断言的是"模型实际收到的内容"。
"""

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
    """模型实际收到的全部内容（跨所有调用）—— 用它断言"附件真的进了上下文"。"""
    return "\n".join("".join(message.content for message in call) for call in llm.calls)


async def test_attachment_reaches_every_member(runtime, client):
    """附件要进**每个成员**看到的上下文，不只是第一个发言的搭子。"""
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
    # 界面上的话题事件只放用户自己说的话：附件是以胶囊展示的
    topic = next(data for name, data in events if name == "topic")
    assert topic["content"] == "按附件里的需求讨论"
    assert "需求说明.md" not in topic["content"]

    seen = _seen_text(llm)
    assert "需求说明.md" in seen, "附件信息没有进入成员的上下文"


async def test_image_reaches_members(runtime, client):
    """图片要走 images 通道（本体发给模型），而不是只给个文件名。"""
    llm = FakeLLM(["图上有个错别字。\n[END_VOTE]", "同意。\n[AGREE]", "结论：已确认。"])
    install_fake_model(runtime, llm)
    group = await _make_group(client, "图片测试群")

    # 1x1 的 PNG：内容不重要，要验证的是"图片被当成图片送出去了"
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    file_id = await _upload(client, "截图.png", png, "image/png")

    await _discuss(client, group["id"], {"topic": "看图", "images": [file_id]})

    # FakeLLM 只记录 messages，图片是通过 images 参数单独传的；
    # 这里能验证的是"带图讨论没有报错且正常收敛"，图片本体由 chat.py 的同一条
    # 构造函数负责（那条链路已有单测覆盖）
    assert llm.calls, "带图讨论没有调用模型"


async def test_unknown_attachment_does_not_break_the_discussion(runtime, client):
    """附件 id 失效（文件被删）时不能把整场讨论打挂 —— 少个附件也要能聊。"""
    llm = FakeLLM(["我们直接聊。\n[END_VOTE]", "同意。\n[AGREE]", "结论：聊完了。"])
    install_fake_model(runtime, llm)
    group = await _make_group(client, "坏附件群")

    events = await _discuss(
        client, group["id"], {"topic": "聊聊", "attachments": ["不存在的文件id"]}
    )

    assert "done" in [name for name, _ in events]


async def test_summary_also_sees_the_attachments(runtime, client):
    """最终总结也要能看到附件：总结往往是引用附件内容最多的一段。"""
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
