"""已完成 Trace 的短期留存。

对应《智能体框架开发文档》12.2 节的 ``GET /v1/traces/{trace_id}``。

## 为什么是内存里的有界环形表

Trace 的用途是"刚刚那次出了什么问题"，用户会顺着界面上的 trace_id 去查。
它不是审计记录（那是 ``audit_log`` 表的职责），所以：

- **不落库**：一次几十个 span，落库会给每轮对话加一笔写放大；
- **有界**：只留最近 ``MAX_TRACES`` 次。无界增长在长跑的桌面客户端上
  就是内存泄漏，而且用户从来不会去查 500 次之前的那一轮。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

# 保留最近多少次。100 次足够覆盖"我刚才那次报错了"这个场景。
MAX_TRACES = 100


class TraceStore:
    """按 trace_id 保存已结束的 Trace 快照。"""

    def __init__(self, *, max_entries: int = MAX_TRACES) -> None:
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max = max(1, max_entries)

    def put(self, trace_id: str, payload: dict[str, Any]) -> None:
        if not trace_id:
            return
        self._entries[trace_id] = payload
        # 超出上限时淘汰最旧的（OrderedDict 的插入序就是时间序）
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def get(self, trace_id: str) -> dict[str, Any] | None:
        return self._entries.get(trace_id)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近若干条摘要，供界面列出"最近几次执行"。

        只给摘要不给完整 span：列表里塞几十份完整 trace 会让响应膨胀到
        几百 KB，而用户要的只是挑一条点进去。
        """
        items = list(self._entries.items())[-max(1, limit) :]
        return [self._summary(trace_id, payload) for trace_id, payload in reversed(items)]

    @staticmethod
    def _summary(trace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """摘要里的耗时**必须从 `total_duration_ms` 取**。

        ⚠️ 这里以前读的是 `payload.get("duration_ms")` —— 而 `Tracer.export()`
        产出的键叫 `total_duration_ms`（见 `tracer.py` 的 `export`，也是前端
        `DetailDrawer` 读的那个）。键名对不上，于是 `GET /v1/traces` 列表里
        每一次执行的耗时**永远是 null**，而底层其实**已经采到**这个数
        （metrics 里的 `turn_duration_ms` 有值）。
        `duration_ms` 这个**输出**键名保持不变（它是对外响应字段，改动属于破坏性变更）；
        只把取值来源修正过来。
        """
        spans = payload.get("spans") or []
        return {
            "trace_id": trace_id,
            "started_at": payload.get("started_at"),
            "duration_ms": payload.get("total_duration_ms"),
            "spans": len(spans),
            "errors": sum(1 for span in spans if span.get("status") == "error"),
        }

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
