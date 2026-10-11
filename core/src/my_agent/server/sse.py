"""SSE 帧的转发别名（实现在 `my_agent/protocol.py`）。

## 为什么只剩下两行

它原先住在这里，但帧格式是**对外协议**、不是传输实现：`agent/group_domain.py`
（领域层，负责"边转发边落库"）也要用它 —— 放在 `server/` 下会逼领域层 import `server.*`，
正是审计 H-06 要消灭的那种反向依赖（只是绕开了 `routes` 而已）。

所以实现上提到包顶层的 `protocol.py`，这里留着 **import 别名**：
`routes/chat.py` / `routes/groups.py` / `routes/events.py` 的历史 import 路径因此**一行都不用改**
（搬运与改 import 分成两件事，回归时能一眼看出是哪一件引起的）。
"""

from __future__ import annotations

from ..protocol import format_sse, parse_sse

__all__ = ["format_sse", "parse_sse"]
