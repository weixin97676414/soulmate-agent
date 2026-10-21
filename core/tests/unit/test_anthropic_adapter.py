











from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from my_agent.llm.adapters.anthropic import CACHE_CONTROL, AnthropicAdapter
from my_agent.llm.base import Message, ToolCall, ToolSpec


def build(handler: Any = None, **kwargs: Any) -> AnthropicAdapter:
    return AnthropicAdapter(
        base_url="https://api.anthropic.com",
        api_key="sk-ant-test",
        model_name="claude-test",
        transport=httpx.MockTransport(handler) if handler else None,
        **kwargs,
    )


def tool(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name} 的描述", parameters={"type": "object"})





def test_system_is_extracted_to_top_level():

    system, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="system", content="你是助手"),
            Message(role="user", content="你好"),
        ]
    )
    assert system == "你是助手"
    assert [m["role"] for m in messages] == ["user"]
    assert all(m["role"] != "system" for m in messages)


def test_assistant_tool_calls_become_tool_use_blocks():
    _, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="user", content="算一下"),
            Message(
                role="assistant",
                content="我来算",
                tool_calls=[ToolCall(id="toolu_1", name="calc", arguments={"expression": "1+2"})],
            ),
            Message(role="tool", content="3", tool_call_id="toolu_1", name="calc"),
        ]
    )
    assistant = messages[1]
    assert [block["type"] for block in assistant["content"]] == ["text", "tool_use"]
    tool_use = assistant["content"][1]
    assert tool_use["id"] == "toolu_1"
    assert tool_use["input"] == {"expression": "1+2"}


def test_consecutive_tool_results_merge_into_one_user_message():





    _, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="user", content="跑两个工具"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="t1", name="a", arguments={}),
                    ToolCall(id="t2", name="b", arguments={}),
                ],
            ),
            Message(role="tool", content="结果A", tool_call_id="t1", name="a"),
            Message(role="tool", content="结果B", tool_call_id="t2", name="b"),
        ]
    )
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    blocks = messages[2]["content"]
    assert [block["type"] for block in blocks] == ["tool_result", "tool_result"]
    assert [block["tool_use_id"] for block in blocks] == ["t1", "t2"]


def test_consecutive_same_role_messages_are_merged():





    _, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="user", content="第一句"),
            Message(role="user", content="第二句"),
        ]
    )
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert len(messages[0]["content"]) == 2


def test_empty_assistant_is_skipped_not_emitted():

    _, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="user", content="你好"),
            Message(role="assistant", content=""),
            Message(role="user", content="在吗"),
        ]
    )
    assert [m["role"] for m in messages] == ["user"]
    assert len(messages[0]["content"]) == 2





def test_payload_places_cache_breakpoints():

    adapter = build()
    payload = adapter._build_payload(
        [Message(role="system", content="系统提示"), Message(role="user", content="你好")],
        [tool("t1"), tool("t2")],
        0.7,
        None,
        stream=False,
    )
    
    assert payload["system"][0]["cache_control"] == CACHE_CONTROL
    
    assert payload["tools"][-1]["cache_control"] == CACHE_CONTROL
    assert "cache_control" not in payload["tools"][0]
    
    assert payload["messages"][-1]["content"][-1]["cache_control"] == CACHE_CONTROL


def test_payload_omits_cache_when_disabled():
    adapter = build(cache_enabled=False)
    payload = adapter._build_payload(
        [Message(role="system", content="系统提示"), Message(role="user", content="你好")],
        [tool("t1")],
        0.7,
        None,
        stream=False,
    )
    
    assert payload["system"] == "系统提示"
    assert "cache_control" not in payload["tools"][0]
    assert "cache_control" not in payload["messages"][-1]["content"][-1]


def test_payload_always_has_max_tokens():

    adapter = build()
    payload = adapter._build_payload([Message(role="user", content="hi")], None, 0.7, None, stream=False)
    assert payload["max_tokens"] == 4096


def test_payload_omits_system_when_absent():
    adapter = build()
    payload = adapter._build_payload([Message(role="user", content="hi")], None, 0.7, None, stream=False)
    assert "system" not in payload
    assert "tools" not in payload





@pytest.mark.asyncio
async def test_chat_parses_text_response():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "你好呀"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 80,
                },
            },
        )

    adapter = build(handler)
    response = await adapter.chat([Message(role="user", content="hi")])

    assert response.content == "你好呀"
    
    assert response.finish_reason == "stop"
    assert response.usage["cache_read_input_tokens"] == 80
    
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    await adapter.aclose()


@pytest.mark.asyncio
async def test_chat_parses_tool_use():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "calc",
                        "input": {"expression": "1+2"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    adapter = build(handler)
    response = await adapter.chat([Message(role="user", content="算一下")])

    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calc"
    assert response.tool_calls[0].arguments == {"expression": "1+2"}
    await adapter.aclose()


@pytest.mark.asyncio
async def test_auth_error_is_classified():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    from my_agent.errors import LLMAuthError

    adapter = build(handler)
    with pytest.raises(LLMAuthError):
        await adapter.chat([Message(role="user", content="hi")])
    await adapter.aclose()





def payload_with_effort(effort: str | None, max_tokens: int | None = None) -> dict[str, Any]:


    return build()._build_payload(
        [Message(role="user", content="hi")],
        None,
        0.7,
        max_tokens,
        stream=False,
        reasoning_effort=effort,
    )


def test_nothing_sent_when_unset():

    payload = payload_with_effort(None)

    assert "thinking" not in payload
    
    assert payload["temperature"] == 0.7


def test_effort_maps_to_thinking_budget():

    payload = payload_with_effort("high", max_tokens=32768)

    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 16384}


def test_effort_drops_temperature():




    payload = payload_with_effort("low")

    assert "temperature" not in payload


def test_budget_is_clamped_when_there_is_not_enough_room():






    payload = payload_with_effort("high")  

    assert payload["thinking"]["budget_tokens"] == 4096 - 1024


def test_skipped_only_when_there_is_no_room_at_all():

    payload = payload_with_effort("high", max_tokens=1024)

    assert "thinking" not in payload
    
    assert payload["temperature"] == 0.7


def test_skipped_when_model_declares_no_support():
    adapter = build()
    adapter.supports_reasoning = False

    payload = adapter._build_payload(
        [Message(role="user", content="hi")],
        None,
        0.7,
        None,
        stream=False,
        reasoning_effort="high",
    )

    assert "thinking" not in payload
