"""SSE 帧格式的单元测试（第 86 批 B 组）。

## 为什么值得单独钉

帧格式以前在**四个**地方各写一遍（`routes/chat.py`、`routes/groups.py`、
`routes/events.py`、`server/events.py::Event.to_sse`），而且**已经漂移**：
`chat` / `events` 那两份带 `default=str`，`groups` 那份漏了 —— 同一个对外协议
两种行为，遇到 `Decimal` / `datetime` 这类非 JSON 原生值时会一个正常、
一个抛 `TypeError`（表现是"这一条事件没发出去"，而用户看到的是界面停在半路）。

现在只有 `server/sse.py` 一份实现，这里把三条性质钉住：
① 往返可解析；② 非 JSON 原生类型不会炸；③ 旁路解析失败返回 None 而不是抛。
"""

from __future__ import annotations

from decimal import Decimal

from my_agent.server.sse import format_sse, parse_sse


def test_frame_round_trips():
    frame = format_sse("delta", {"text": "你好", "n": 1})
    assert frame == 'event: delta\ndata: {"text": "你好", "n": 1}\n\n'
    assert parse_sse(frame) == ("delta", {"text": "你好", "n": 1})


def test_non_json_native_values_do_not_break_the_frame():
    """`default=str` 是必须的：span / 摘要里会混进 Decimal、datetime。

    这条正是当初两个实现**分叉**的地方 —— 少了它整帧序列化会抛 `TypeError`。
    """
    frame = format_sse("usage", {"cost": Decimal("1.20")})
    assert parse_sse(frame) == ("usage", {"cost": "1.20"})


def test_parse_tolerates_garbage():
    """旁路解析失败要返回 None，**不能**把主链路炸掉（边转发边落库那条路）。"""
    # 心跳注释帧
    assert parse_sse(": ping\n\n") is None
    # data 不是合法 JSON
    assert parse_sse("event: x\ndata: {bad json\n\n") is None
    # data 不是对象：按空 dict 处理（沿用原实现的行为，别改）
    assert parse_sse("event: x\ndata: [1,2]\n\n") == ("x", {})
