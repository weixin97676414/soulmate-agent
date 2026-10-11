"""SSE 帧的**唯一一份**实现（对外协议编解码）。

## 为什么在中立位置、而不是 `server/` 下

它原先住 `server/sse.py`。但帧格式**不是**传输实现、而是**对外协议**：
`parse_sse` 是"边转发边落库"那条旁路的解析器，`agent/group_domain.py`（领域层）
也要用它。放在 `server/` 下会逼着领域层去 import `server.*` ——
正是审计 H-06 要消灭的那种反向依赖（只是绕开了 `routes` 而已）。

所以它上提到包的顶层：**不依赖任何一层**，谁都能用。

## 为什么只此一份

帧格式以前在**四个**地方各写了一遍（`routes/chat.py`、`routes/groups.py`、
`routes/events.py`、以及 `server/events.py` 的 `Event.to_sse()`），而且**已经漂移**：
`chat` / `events` 那两份带 `default=str`（非 JSON 原生类型兜底），`groups` 那份**漏了** ——
遇到 `Decimal` / `datetime` 时一个正常、一个直接抛 `TypeError`。

`server/sse.py` 现在只是这里的转发别名（历史 import 路径仍可用）。
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["format_sse", "parse_sse"]


def format_sse(event: str, data: dict[str, Any]) -> str:
    """把一个事件拼成一帧 SSE。

    ``default=str`` 是**必须的**：span / 会话摘要里偶尔会混进 ``Decimal``、
    ``datetime`` 这类非 JSON 原生类型。缺了它整帧序列化会抛 ``TypeError``，
    表现为"这一条事件没发出去"—— 而用户看到的是界面**停在半路**。
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def parse_sse(chunk: str) -> tuple[str, dict[str, Any]] | None:
    """从 :func:`format_sse` 生成的文本里取回 ``(event, data)``。

    群聊转发时用它"顺手落库"：比把讨论流里二十多处 ``yield`` 全部改成
    "先落库再 yield"要稳妥得多（漏一处就**静默丢一段历史**）。

    解析不出来时返回 ``None``（调用方跳过即可），**不要抛** ——
    这是"边转发边落库"的旁路，旁路失败不该把主链路炸掉。
    """
    if not chunk.startswith("event: "):
        return None
    lines = chunk.split("\n")
    event = lines[0][len("event: ") :].strip()
    data_line = next((line for line in lines if line.startswith("data: ")), "")
    try:
        payload = json.loads(data_line[len("data: ") :] or "{}")
    except ValueError:
        return None
    return event, payload if isinstance(payload, dict) else {}
