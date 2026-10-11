"""OpenAI 兼容适配器的协议转换与流式解析测试。

用 ``httpx.MockTransport`` 模拟厂商响应，不依赖网络与真实 API Key。
重点覆盖最容易出错的地方：**流式工具调用参数的碎片拼接**。
"""

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
    """框架内部结构 -> OpenAI 结构，字段必须完全对齐。"""
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
    # 同一套配置即可覆盖 DeepSeek / Ollama 等，验证走的是标准 OpenAI 路径
    assert captured["model"] == "test-model"


@pytest.mark.asyncio
async def test_stream_accumulates_fragmented_tool_arguments():
    """流式下工具参数会按分片到达，必须拼成合法 JSON。"""
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
    """单个损坏分片不应中断整个流。"""

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


# --------------------------------------------------------------------------- #
# 系统代理处理
# --------------------------------------------------------------------------- #
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
    """本机端点必须绕过系统代理。

    Windows 上 httpx 通过读**注册表**拿到系统代理，且对 127.0.0.1 不做豁免。
    企业网络里配代理很常见，一旦被代理接管，本地 Ollama 就会收到代理返回的
    502——报错完全指不到"代理"这个真正的原因上。
    """
    adapter = _adapter_for("http://127.0.0.1:11434/v1")
    assert adapter._client.trust_env is False  # noqa: SLF001


def test_cloud_endpoint_bypasses_system_proxy_by_default():
    """云端**默认也不走系统代理**。

    实测：用户机器的系统代理会把国内厂商（硅基流动/百炼）的请求拖成
    连接超时，直连都在 300ms 内。需要代理访问 OpenAI/Anthropic 的用户，
    按模型打开 ``use_system_proxy``。
    """
    adapter = _adapter_for("https://api.deepseek.com/v1")
    assert adapter._client.trust_env is False  # noqa: SLF001


def test_cloud_endpoint_can_opt_into_system_proxy():
    """显式打开 use_system_proxy 时，云端请求走系统代理。"""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com/v1",
        api_key="k",
        model_name="m",
        use_system_proxy=True,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    assert adapter._client.trust_env is True  # noqa: SLF001
