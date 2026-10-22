













from __future__ import annotations

from collections import OrderedDict
from typing import Any


MAX_TRACES = 100


class TraceStore:


    def __init__(self, *, max_entries: int = MAX_TRACES) -> None:
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max = max(1, max_entries)

    def put(self, trace_id: str, payload: dict[str, Any]) -> None:
        if not trace_id:
            return
        self._entries[trace_id] = payload
        
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def get(self, trace_id: str) -> dict[str, Any] | None:
        return self._entries.get(trace_id)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:





        items = list(self._entries.items())[-max(1, limit) :]
        return [self._summary(trace_id, payload) for trace_id, payload in reversed(items)]

    @staticmethod
    def _summary(trace_id: str, payload: dict[str, Any]) -> dict[str, Any]:










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
