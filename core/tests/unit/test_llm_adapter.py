





from __future__ import annotations

import json

import httpx
import pytest

from my_agent.errors import LLMAuthError, LLMError
from my_agent.llm.adapters.openai_compat import OpenAICompatAdapter, is_loopback_url
from my_agent.llm.base import Message, ToolCall, ToolSpec


def make_adapter(handler) -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model_name="test-model",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_message_and_tool_conversion():

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    adapter = make_adapter(handler)
    messages = [
        Message(role="system", content="你是助手"),
        Message(role="user", content="你好"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="c1", name="calc", raw_arguments='{"expression":"1+1"}')],
        ),
        Message(role="tool", content="2", tool_call_id="c1"),
    ]
    tools = [ToolSpec(name="calc", description="计算", parameters={"type": "object", "properties": {}})]

    resp = await adapter.chat(messages, tools=tools)
    await adapter.aclose()

    assert resp.content == "ok"
    assert resp.usage["prompt_tokens"] == 3

    sent = captured["messages"]
    assert sent[0]["role"] == "system"
    assert sent[2]["tool_calls"][0]["function"]["name"] == "calc"
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == '{"expression":"1+1"}'
    assert sent[3]["tool_call_id"] == "c1"
    assert captured["tools"][0]["function"]["name"] == "calc"
    assert captured["stream"] is False
    
    assert captured["model"] == "test-model"


@pytest.mark.asyncio
async def test_stream_accumulates_fragmented_tool_arguments():

    sse = (
        'data: {"choices":[{"delta":{"content":"我来算"},"index":0}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_a","function":{"name":"calc","arguments":"{\\"expr"}}]},"index":0}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ession\\": \\"1+2\\"}"}}]},"index":0}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls","index":0}],"usage":{"prompt_tokens":9,"completion_tokens":4}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    adapter = make_adapter(handler)
    chunks = [c async for c in adapter.stream([Message(role="user", content="算一下")])]
    await adapter.aclose()

    text = "".join(c.delta for c in chunks)
    assert text == "我来算"

    final = chunks[-1]
    assert final.finish_reason == "tool_calls"
    assert final.usage == {"prompt_tokens": 9, "completion_tokens": 4}
    assert final.tool_calls is not None
    assert len(final.tool_calls) == 1
    tc = final.tool_calls[0]
    assert tc.name == "calc"
    assert tc.arguments == {"expression": "1+2"}


@pytest.mark.asyncio
async def test_stream_handles_broken_json_chunk_gracefully():


    def handler(_: httpx.Request) -> httpx.Response:
        body = (
            'data: {"choices":[{"delta":{"content":"A"},"index":0}]}\n\n'
            "data: {这不是合法JSON}\n\n"
            'data: {"choices":[{"delta":{"content":"B"},"finish_reason":"stop","index":0}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode())

    adapter = make_adapter(handler)
    chunks = [c async for c in adapter.stream([Message(role="user", content="x")])]
    await adapter.aclose()
    assert "".join(c.delta for c in chunks) == "AB"


@pytest.mark.asyncio
async def test_auth_error_is_classified():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    adapter = make_adapter(handler)
    with pytest.raises(LLMAuthError):
        await adapter.chat([Message(role="user", content="hi")])
    await adapter.aclose()


@pytest.mark.asyncio
async def test_server_error_is_llm_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    adapter = make_adapter(handler)
    with pytest.raises(LLMError):
        await adapter.chat([Message(role="user", content="hi")])
    await adapter.aclose()


@pytest.mark.asyncio
async def test_retry_on_429_then_success():
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    adapter = OpenAICompatAdapter(
        base_url="https://api.example.com/v1",
        api_key="k",
        model_name="m",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    resp = await adapter.chat([Message(role="user", content="hi")])
    await adapter.aclose()
    assert resp.content == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200, json={"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}
        )

    adapter = make_adapter(handler)
    models = await adapter.list_models()
    await adapter.aclose()
    assert models == ["deepseek-chat", "deepseek-reasoner"]





@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:11434/v1", True),
        ("http://127.0.1.1:8080/v1", True),
        ("http://localhost:8000/v1", True),
        ("http://[::1]:1234/v1", True),
        ("https://api.deepseek.com/v1", False),
        ("http://192.168.1.5:11434/v1", False),
        ("", False),
    ],
)
def test_is_loopback_url(url, expected):
    assert is_loopback_url(url) is expected


def _adapter_for(base_url: str):
    return OpenAICompatAdapter(
        base_url=base_url, api_key="k", model_name="m", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )


def test_loopback_endpoint_bypasses_system_proxy():






    adapter = _adapter_for("http://127.0.0.1:11434/v1")
    assert adapter._client.trust_env is False  


def test_cloud_endpoint_bypasses_system_proxy_by_default():






    adapter = _adapter_for("https://api.deepseek.com/v1")
    assert adapter._client.trust_env is False  


def test_cloud_endpoint_can_opt_into_system_proxy():

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com/v1",
        api_key="k",
        model_name="m",
        use_system_proxy=True,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    assert adapter._client.trust_env is True  
