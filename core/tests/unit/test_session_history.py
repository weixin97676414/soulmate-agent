














from __future__ import annotations

from my_agent.agent.session import Session
from my_agent.llm.base import ToolCall


def test_只有思考的助手消息必须回读():







    session = Session(id="s1")
    session.memory.add_user("帮我看一下这个方案")
    session.memory.add_assistant("", reasoning_content="先想清楚从哪儿下手…")

    history = session.history()

    assert len(history) == 2
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == ""
    
    assert history[1]["reasoning"] == "先想清楚从哪儿下手…"


def test_什么都没有的助手消息仍然丢弃():





    session = Session(id="s1")
    session.memory.add_user("在吗")
    session.memory.add_assistant("")

    history = session.history()

    assert len(history) == 1
    assert history[0]["role"] == "user"


def test_带计划或工具调用的助手消息也放行():





    session = Session(id="s1")
    session.memory.add_user("帮我订一下明天的会议室")
    session.memory.add_assistant("", plan={"id": "p1", "steps": []})
    session.memory.add_assistant(
        "", tool_calls=[ToolCall(id="t1", name="calc", arguments={"expr": "1+1"})]
    )

    history = session.history()

    assert len(history) == 3
    assert history[1]["plan"] == {"id": "p1", "steps": []}
    assert history[2]["tool_calls"][0]["name"] == "calc"
    assert history[2]["tool_calls"][0]["arguments"] == {"expr": "1+1"}
