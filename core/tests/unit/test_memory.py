

from __future__ import annotations

from my_agent.llm.base import Message, ToolCall
from my_agent.memory.short_term import MemoryManager


def _fill(memory: MemoryManager, rounds: int, text_len: int = 200) -> None:
    for i in range(rounds):
        memory.add_user("u" * text_len)
        memory.add_assistant(
            "a" * text_len,
            tool_calls=[ToolCall(id=f"c{i}", name="t", raw_arguments="{}")],
        )
        memory.add_tool(f"c{i}", "t", "r" * text_len)


def test_no_truncation_when_under_limit():





    memory = MemoryManager(max_context_tokens=10_000)
    _fill(memory, 3)
    ctx = memory.get_context()
    assert len(ctx) == len(memory.messages)
    for view, original in zip(ctx, memory.messages, strict=True):
        assert view.content.endswith(original.content)
        assert original.content  


def test_context_prefixes_times_without_touching_messages():





    memory = MemoryManager()
    memory.add_user("帮我看看")
    memory.add_assistant("好的")

    ctx = memory.get_context()

    
    assert ctx[0].content.startswith("现在：")
    
    assert ctx[1].content.startswith("[")
    assert ctx[1].content.endswith("好的")
    
    assert memory.messages[0].content == "帮我看看"
    assert memory.messages[1].content == "好的"


def test_only_the_last_user_message_carries_now():

    memory = MemoryManager()
    memory.add_user("第一句")
    memory.add_assistant("嗯")
    memory.add_user("第二句")

    ctx = memory.get_context()

    assert ctx[0].content.startswith("[")
    assert ctx[2].content.startswith("现在：")


def test_unknown_time_gets_no_prefix():





    memory = MemoryManager()
    memory.messages.append(Message(role="user", content="很久以前说的话"))
    ctx = memory.get_context()
    assert ctx[0].content == "很久以前说的话"


def test_tool_messages_keep_their_injection_boundary():




    memory = MemoryManager()
    memory.add_assistant("", tool_calls=[ToolCall(id="c1", name="t", raw_arguments="{}")])
    memory.add_tool("c1", "t", "结果")

    ctx = memory.get_context()

    assert ctx[-1].role == "tool"
    assert ctx[-1].content.startswith("<<<UNTRUSTED_TOOL_OUTPUT")


def test_truncation_keeps_system_first():
    memory = MemoryManager(max_context_tokens=600)
    memory.ensure_system("你是助手")
    _fill(memory, 10)

    ctx = memory.get_context()
    assert ctx[0].role == "system"
    assert ctx[0].content == "你是助手"
    assert len(ctx) < len(memory.messages)
    assert memory.estimated_tokens() > 0


def test_truncation_never_leaves_orphan_tool_message():

    memory = MemoryManager(max_context_tokens=500)
    memory.ensure_system("sys")
    _fill(memory, 10)

    ctx = memory.get_context()
    non_system = [m for m in ctx if m.role != "system"]
    assert non_system, "至少应保留一条消息"
    assert non_system[0].role != "tool"


def test_system_prompt_is_replaced_not_duplicated():
    memory = MemoryManager()
    memory.ensure_system("v1")
    memory.ensure_system("v2")
    assert len([m for m in memory.messages if m.role == "system"]) == 1
    assert memory.messages[0].content == "v2"


def test_blank_system_prompt_removes_the_message():






    memory = MemoryManager()
    memory.ensure_system("v1")
    memory.ensure_system("")
    assert [m for m in memory.messages if m.role == "system"] == []


def test_blank_system_prompt_does_not_insert_one():

    memory = MemoryManager()
    memory.ensure_system("")
    memory.add_user("你好")
    assert [m for m in memory.messages if m.role == "system"] == []
    assert memory.get_context()[0].role == "user"


def test_clear_keeps_only_a_real_system_message():






    memory = MemoryManager()
    memory.add_user("你好")
    memory.add_assistant("回复")
    memory.clear()
    assert memory.messages == []


def test_long_tool_result_is_kept_whole():











    memory = MemoryManager(max_context_tokens=200_000)
    payload = "x" * 500_000

    message = memory.add_tool("c1", "t", payload)

    assert payload in message.content
    assert "中间省略" not in message.content
    
    assert memory.messages[-1].content == message.content


def test_to_records_round_trip_shape():
    memory = MemoryManager()
    memory.add_user("你好")
    memory.add_assistant("hi", tool_calls=[ToolCall(id="c1", name="echo", raw_arguments='{"a":1}')])
    records = memory.to_records()
    assert records[0]["role"] == "user"
    assert records[1]["tool_calls"][0]["function"]["name"] == "echo"
