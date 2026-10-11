"""Anthropic 原生适配器的格式转换与缓存断点。

这些用例覆盖的都是**不联网也能验、但写错了必然 400** 的地方：

- system 必须是顶层参数，塞进 messages 会被拒；
- 连续的工具结果必须合并进**同一条** user 消息，拆开算"角色不交替"；
- 同角色的相邻消息必须合并（内部记忆里真的会出现连续两条 user）；
- ``max_tokens`` 必填，不给就 400；
- ``cache_control`` 断点要打在对的位置，否则**完全没有缓存**
  （Anthropic 是显式缓存，这点和 DeepSeek / OpenAI 的自动前缀缓存根本不同）。
"""

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


# --------------------------------------------------------------------------- #
# 消息转换
# --------------------------------------------------------------------------- #
def test_system_is_extracted_to_top_level():
    """system 必须从 messages 里拿出去，变成顶层参数。"""
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
    """多个工具结果必须合并成**一条** user 消息。

    拆成多条会被判为"角色不交替"而 400 —— 而且只有当模型一轮调用多个工具时
    才触发，属于那种平时测不到、一上线就报错的坑。
    """
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
    """同角色的相邻消息要合并。

    内部记忆里真的会出现连续两条 user（"空回复催促"会合成一条 user 消息，
    而它前面那条空 assistant 不产生任何内容块），不合并就会偶发 400。
    """
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
    """既不说话也不调工具的 assistant 不该产生空 content 块。"""
    _, messages = AnthropicAdapter._to_anthropic_messages(
        [
            Message(role="user", content="你好"),
            Message(role="assistant", content=""),
            Message(role="user", content="在吗"),
        ]
    )
    assert [m["role"] for m in messages] == ["user"]
    assert len(messages[0]["content"]) == 2


# --------------------------------------------------------------------------- #
# 请求体与缓存断点
# --------------------------------------------------------------------------- #
def test_payload_places_cache_breakpoints():
    """三个断点：最后一个工具、system、最后一条消息。"""
    adapter = build()
    payload = adapter._build_payload(
        [Message(role="system", content="系统提示"), Message(role="user", content="你好")],
        [tool("t1"), tool("t2")],
        0.7,
        None,
        stream=False,
    )
    # system 断点：缓存层级是 tools → system → messages，这一个把两者都覆盖
    assert payload["system"][0]["cache_control"] == CACHE_CONTROL
    # 断点打在第**最后**一个工具上，缓存住整个工具列表
    assert payload["tools"][-1]["cache_control"] == CACHE_CONTROL
    assert "cache_control" not in payload["tools"][0]
    # 历史断点：下一次对话能命中整段历史
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
    # 关掉后 system 退回成裸字符串，工具与消息上都不带断点
    assert payload["system"] == "系统提示"
    assert "cache_control" not in payload["tools"][0]
    assert "cache_control" not in payload["messages"][-1]["content"][-1]


def test_payload_always_has_max_tokens():
    """max_tokens 是 Anthropic 的必填项，不给会直接 400。"""
    adapter = build()
    payload = adapter._build_payload([Message(role="user", content="hi")], None, 0.7, None, stream=False)
    assert payload["max_tokens"] == 4096


def test_payload_omits_system_when_absent():
    adapter = build()
    payload = adapter._build_payload([Message(role="user", content="hi")], None, 0.7, None, stream=False)
    assert "system" not in payload
    assert "tools" not in payload


# --------------------------------------------------------------------------- #
# 真实请求/响应往返（MockTransport，不联网）
# --------------------------------------------------------------------------- #
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
    # end_turn 要归一到内部的 stop 口径
    assert response.finish_reason == "stop"
    assert response.usage["cache_read_input_tokens"] == 80
    # 鉴权走 x-api-key 而不是 Bearer
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


# --------------------------------------------------------------------------- #
# 思考强度 -> 扩展思考预算
# --------------------------------------------------------------------------- #
def payload_with_effort(effort: str | None, max_tokens: int | None = None) -> dict[str, Any]:
    """注意必须走 **chat() 的同一条组装路径**，而不是直接调 _build_payload ——
    "参数有没有从 chat 传进去"是独立的失败点，直接调内部函数会把它绕过去。"""
    return build()._build_payload(
        [Message(role="user", content="hi")],
        None,
        0.7,
        max_tokens,
        stream=False,
        reasoning_effort=effort,
    )


def test_nothing_sent_when_unset():
    """没选档位时一个字段都不发 —— 这是绝大多数用户的默认状态。"""
    payload = payload_with_effort(None)

    assert "thinking" not in payload
    # temperature 也不该被动过：没有被要求开启扩展思考，就没有理由丢掉它
    assert payload["temperature"] == 0.7


def test_effort_maps_to_thinking_budget():
    """额度够时按档位给足预算。"""
    payload = payload_with_effort("high", max_tokens=32768)

    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 16384}


def test_effort_drops_temperature():
    """开着扩展思考时 temperature 只能是 1，否则整条请求被拒。

    与其把它悄悄改成 1（用户之后会发现"温度没生效"），不如整个不发。
    """
    payload = payload_with_effort("low")

    assert "temperature" not in payload


def test_budget_is_clamped_when_there_is_not_enough_room():
    """额度不够时**按上限缩减**，而不是干脆不生效。

    直接放弃会让用户觉得"我明明调了高却没变化"，而归因不到"输出上限太小"
    —— 那是典型的"配置了但不起作用"。默认 max_tokens 是 4096，
    「高」档的 16384 在默认设置下**永远**装不下，所以这条分支是常态而非边缘。
    """
    payload = payload_with_effort("high")  # max_tokens 走默认的 4096

    assert payload["thinking"]["budget_tokens"] == 4096 - 1024


def test_skipped_only_when_there_is_no_room_at_all():
    """连最低预算都装不下时才不发（那种情况 Anthropic 本来也不接受）。"""
    payload = payload_with_effort("high", max_tokens=1024)

    assert "thinking" not in payload
    # 没有启用扩展思考，temperature 就该照常保留
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
