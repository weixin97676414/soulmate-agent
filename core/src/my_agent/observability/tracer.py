










from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from ..llm.usage import Usage, normalize_usage
from ..security.redact import redact, redact_obj


@dataclass
class Span:


    name: str
    span_id: str
    parent_id: str | None = None
    start: float = field(default_factory=time.perf_counter)
    end: float | None = None
    status: str = "running"  
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        end = self.end if self.end is not None else time.perf_counter()
        return round((end - self.start) * 1000, 2)

    def event(self, name: str, **payload: Any) -> None:
        self.events.append({"name": name, "ts_ms": self.duration_ms, **payload})

    def to_dict(self, base: float | None = None) -> dict[str, Any]:





        data: dict[str, Any] = {
            "span_id": self.span_id,
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "meta": redact_obj(self.meta),
            "events": redact_obj(self.events),
        }
        if base is not None:
            data["start_ms"] = round((self.start - base) * 1000, 2)
            end = self.end if self.end is not None else time.perf_counter()
            data["end_ms"] = round((end - base) * 1000, 2)
        if self.parent_id:
            data["parent_id"] = self.parent_id
        if self.error:
            data["error"] = redact(self.error)
        return data


class Tracer:


    def __init__(self, *, enabled: bool = True) -> None:
        self.trace_id = uuid.uuid4().hex[:16]
        self.enabled = enabled
        self.spans: list[Span] = []
        self._stack: list[Span] = []
        
        
        self.usage = Usage()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        
        self.started_at = time.time()
        self._t0 = time.perf_counter()

    
    
    
    @contextmanager
    def span(self, name: str, **meta: Any) -> Iterator[Span]:
        if not self.enabled:
            
            yield Span(name=name, span_id="", meta=meta)
            return

        parent_id = self._stack[-1].span_id if self._stack else None
        span = Span(name=name, span_id=uuid.uuid4().hex[:8], parent_id=parent_id, meta=meta)
        self.spans.append(span)
        self._stack.append(span)
        try:
            yield span
        except asyncio.CancelledError:
            
            
            
            
            span.status = "cancelled"
            raise
        except Exception as exc:
            span.status = "error"
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        else:
            span.status = "ok"
        finally:
            span.end = time.perf_counter()
            self._stack.pop()

    
    
    
    def add_usage(self, usage: dict[str, Any] | None) -> None:









        parsed = normalize_usage(usage)
        if parsed.is_empty:
            return
        self.usage.add(parsed)
        self.prompt_tokens = self.usage.prompt_tokens
        self.completion_tokens = self.usage.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    
    
    
    def export(self) -> dict[str, Any]:






        ended = [s.end for s in self.spans if s.end is not None]
        total = round((max(ended) - self._t0) * 1000, 2) if ended else 0.0

        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "total_duration_ms": total,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            
            "usage": self.usage.to_dict(),
            "spans": [s.to_dict(base=self._t0) for s in self.spans],
        }
