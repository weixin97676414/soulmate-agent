










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
    
    assert 0.0 <= body["ratio"] < 0.5
    assert body["summary_chars"] == 0
    
    assert 0 < body["compress_threshold"] <= 1


@pytest.mark.asyncio
async def test_context_usage_unknown_session_returns_404(client):
    response = await client.get("/v1/sessions/does-not-exist/context")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_context_usage_grows_with_messages(runtime, client):

    created = (await client.post("/v1/sessions", json={"title": "增长测试"})).json()
    session_id = created["id"]

    before = (await client.get(f"/v1/sessions/{session_id}/context")).json()["used_tokens"]

    session = await runtime.get_session(session_id)
    
    for index in range(20):
        session.memory.add_user(f"第 {index} 条测试消息，" + "内容" * 50)

    after = (await client.get(f"/v1/sessions/{session_id}/context")).json()["used_tokens"]
    assert after > before
