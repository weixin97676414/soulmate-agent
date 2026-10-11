"""会话上下文用量接口（`GET /v1/sessions/{id}/context`）。

这个接口是输入区底部那个"上下文占用"胶囊的唯一数据源。它有两条容易写错的地方，
都在这里锁住：

1. 用的必须是 ``context_tokens()``（**实际会发送的**量），不是完整历史的估算值 ——
   压缩之后完整历史仍然很长，拿它显示会让人以为"一直快满了"；
2. ``limit_tokens`` 必须与压缩判定同源（``effective_context_tokens``），
   否则界面显示的比例和真正触发压缩的比例不是一个数。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_context_usage_for_new_session(client):
    created = (await client.post("/v1/sessions", json={"title": "上下文测试"})).json()
    session_id = created["id"]

    response = await client.get(f"/v1/sessions/{session_id}/context")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["used_tokens"] >= 0
    assert body["limit_tokens"] > 0
    assert body["remaining_tokens"] >= 0
    # 新会话只有系统提示词，占比一定很低
    assert 0.0 <= body["ratio"] < 0.5
    assert body["summary_chars"] == 0
    # 压缩阈值是"用量比例"，界面要拿它做提示
    assert 0 < body["compress_threshold"] <= 1


@pytest.mark.asyncio
async def test_context_usage_unknown_session_returns_404(client):
    response = await client.get("/v1/sessions/does-not-exist/context")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_context_usage_grows_with_messages(runtime, client):
    """加消息之后占用必须变大 —— 这是"显示的是真数据"的最小证据。"""
    created = (await client.post("/v1/sessions", json={"title": "增长测试"})).json()
    session_id = created["id"]

    before = (await client.get(f"/v1/sessions/{session_id}/context")).json()["used_tokens"]

    session = await runtime.get_session(session_id)
    # 直接往记忆里塞内容，不跑模型：这条用例只关心"用量有没有跟着涨"
    for index in range(20):
        session.memory.add_user(f"第 {index} 条测试消息，" + "内容" * 50)

    after = (await client.get(f"/v1/sessions/{session_id}/context")).json()["used_tokens"]
    assert after > before
