"""短期记忆与上下文截断测试。"""

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
    """没超限时**一条都不少**。

    不能写成 ``ctx == memory.messages``：出站视图会在 content 前加时间前缀（而且是副本），
    两者本就不该相等 —— 要断言的是"条数没少、原文都在"。
    """
    memory = MemoryManager(max_context_tokens=10_000)
    _fill(memory, 3)
    ctx = memory.get_context()
    assert len(ctx) == len(memory.messages)
    for view, original in zip(ctx, memory.messages, strict=True):
        assert view.content.endswith(original.content)
        assert original.content  # 原文一个字都没被改


def test_context_prefixes_times_without_touching_messages():
    """时间维度：出站视图带时间前缀，**原始消息一个字都不改**。

    原始消息是用户看到的聊天记录、也是落盘内容与摘要的输入。前缀写进去的话，
    摘要会被时间噪声淹没、界面上的前缀越滚越长，而"原本说了什么"再也还原不出来。
    """
    memory = MemoryManager()
    memory.add_user("帮我看看")
    memory.add_assistant("好的")

    ctx = memory.get_context()

    # 没有更晚的用户消息时，"此刻"就挂在这一条上
    assert ctx[0].content.startswith("现在：")
    # 助手回复是历史消息 → 只带一个短前缀
    assert ctx[1].content.startswith("[")
    assert ctx[1].content.endswith("好的")
    # 原文必须干净
    assert memory.messages[0].content == "帮我看看"
    assert memory.messages[1].content == "好的"


def test_only_the_last_user_message_carries_now():
    """「现在」只挂在最后一条用户消息上：它代表此刻，且每轮都会重新渲染。"""
    memory = MemoryManager()
    memory.add_user("第一句")
    memory.add_assistant("嗯")
    memory.add_user("第二句")

    ctx = memory.get_context()

    assert ctx[0].content.startswith("[")
    assert ctx[2].content.startswith("现在：")


def test_unknown_time_gets_no_prefix():
    """时间不知道就不加前缀 —— 给一个假时间比没有时间糟糕得多。

    （老数据的时间戳被"整表重刷"刷坏了，读回来一律当不知道；system 与引擎合成的
    提示语也没有时间。）
    """
    memory = MemoryManager()
    memory.messages.append(Message(role="user", content="很久以前说的话"))
    ctx = memory.get_context()
    assert ctx[0].content == "很久以前说的话"


def test_tool_messages_keep_their_injection_boundary():
    """工具结果**不加**时间前缀：它必须以不可信边界的起始标记开头。

    在那之前插我们自己的文字会让模型分不清"数据区从哪开始时"，而那道边界是防注入的第三层。
    """
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
    """截断后首条非 system 消息不能是 tool，否则 OpenAI 协议报错。"""
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
    """人格为空时**不留** system 消息。

    兜底提示词退役后 ``Agent._system_prompt()`` 可能返回空串（用户把搭子的人格
    文件全清空，或遇到更早版本建出来、还没有归属搭子的会话）。这时宁可整条请求
    不带 system，也不要发一条空内容的 —— 空文本在部分厂商那里是非法请求。
    """
    memory = MemoryManager()
    memory.ensure_system("v1")
    memory.ensure_system("")
    assert [m for m in memory.messages if m.role == "system"] == []


def test_blank_system_prompt_does_not_insert_one():
    """本来就没人格时，也不该凭空插一条空的 system。"""
    memory = MemoryManager()
    memory.ensure_system("")
    memory.add_user("你好")
    assert [m for m in memory.messages if m.role == "system"] == []
    assert memory.get_context()[0].role == "user"


def test_clear_keeps_only_a_real_system_message():
    """清空时只认"第 0 位真的是 system"。

    提示词兜底退役后，搭子可能一条 system 都没有（人格文件全空）。这时盲取
    ``[:1]`` 会把**第一条用户消息**当成 system 留下 —— 用户看到的现象是
    "清空了，却还剩一句没清掉"。
    """
    memory = MemoryManager()
    memory.add_user("你好")
    memory.add_assistant("回复")
    memory.clear()
    assert memory.messages == []


def test_long_tool_result_is_kept_whole():
    """超长工具结果**原样保留**。

    曾经这里断言的是"被截断"（``len(content) < 500`` 且含"中间省略"）。
    那个行为本身就是 bug：4000 字符的头尾截断会**真的丢掉中间内容**，
    而紧挨着的注释还写着"完整内容已落产物目录" —— 对 http 取回、记忆检索、
    MCP 工具这些不产出文件的能力，那句话根本不成立。

    用户是拿着证据来的：服务端完整发了 23006 字节、``truncated: false``，
    模型却在正文里看到"中间省略 5745 字符"。他的要求是
    "不要做任何截断/省略，将所有内容完整给到 ai"。
    """
    memory = MemoryManager(max_context_tokens=200_000)
    payload = "x" * 500_000

    message = memory.add_tool("c1", "t", payload)

    assert payload in message.content
    assert "中间省略" not in message.content
    # 完整历史（界面回显与落库都用它）同样是完整的
    assert memory.messages[-1].content == message.content


def test_to_records_round_trip_shape():
    memory = MemoryManager()
    memory.add_user("你好")
    memory.add_assistant("hi", tool_calls=[ToolCall(id="c1", name="echo", raw_arguments='{"a":1}')])
    records = memory.to_records()
    assert records[0]["role"] == "user"
    assert records[1]["tool_calls"][0]["function"]["name"] == "echo"
