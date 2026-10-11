"""Trace 追踪。

对应《智能体框架开发文档》第 11.3 节。一次任务产出一个 Trace，
包含若干 Span（每轮模型调用、每次工具执行各一个），最终由
``export()`` 输出给客户端右侧抽屉展示。

相比文档原始设计，这里做了两点改动：
1. ``span()`` 返回上下文管理器，语法更轻（``with tracer.span("x"):``）；
2. Span 支持嵌套，导出时保留父子关系，前端可直接渲染成树/时间线。
"""

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
    """一段被追踪的执行区间。"""

    name: str
    span_id: str
    parent_id: str | None = None
    start: float = field(default_factory=time.perf_counter)
    end: float | None = None
    status: str = "running"  # running / ok / error
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
        """``base`` 是 trace 的起始 perf_counter，用来算相对偏移。

        前端要画的是时间线（谁先谁后、多长、有没有重叠），只给 duration
        是不够的——那样所有 span 只能并排堆着，看不出并发与嵌套。
        """
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
    """一次任务的完整链路记录。"""

    def __init__(self, *, enabled: bool = True) -> None:
        self.trace_id = uuid.uuid4().hex[:16]
        self.enabled = enabled
        self.spans: list[Span] = []
        self._stack: list[Span] = []
        # 完整用量（含缓存命中）。prompt_tokens / completion_tokens 保留为
        # 扁平属性，因为它们已经被 export() 与 done 事件用着，改签名会波及前端。
        self.usage = Usage()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        # 墙钟时间，给用户看；_t0 是单调时钟，用来算耗时（不受系统时间调整影响）
        self.started_at = time.time()
        self._t0 = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Span 管理
    # ------------------------------------------------------------------ #
    @contextmanager
    def span(self, name: str, **meta: Any) -> Iterator[Span]:
        if not self.enabled:
            # 关闭追踪时给一个不落库的哑对象，调用方代码无需分支
            yield Span(name=name, span_id="", meta=meta)
            return

        parent_id = self._stack[-1].span_id if self._stack else None
        span = Span(name=name, span_id=uuid.uuid4().hex[:8], parent_id=parent_id, meta=meta)
        self.spans.append(span)
        self._stack.append(span)
        try:
            yield span
        except asyncio.CancelledError:
            # CancelledError 是 BaseException，**不会**被下面的 ``except Exception``
            # 接住。不显式处理的话，被用户中断的 span 状态会永远停在 "running"——
            # 在追踪视图里看起来像"这一步还在跑"，而任务其实早就没了。
            # （``end`` 由 finally 赋值，所以耗时统计一直是准的，错的只是状态。）
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

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def add_usage(self, usage: dict[str, Any] | None) -> None:
        """累加一次模型调用的用量。

        走 :func:`normalize_usage` 而不是直接 ``usage.get("prompt_tokens")``：
        各家的字段名不同（``input_tokens`` / ``output_tokens`` / ``prompt_cache_hit_tokens``…），
        而且**缓存命中的 token 必须单独记下来**——它的单价可能只有未命中的十分之一，
        混在总量里会让费用估算高出一个数量级。

        原实现只取两个字段，其余全部丢弃，于是「缓存到底省了多少」永远算不出来。
        """
        parsed = normalize_usage(usage)
        if parsed.is_empty:
            return
        self.usage.add(parsed)
        self.prompt_tokens = self.usage.prompt_tokens
        self.completion_tokens = self.usage.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    # ------------------------------------------------------------------ #
    # 导出
    # ------------------------------------------------------------------ #
    def export(self) -> dict[str, Any]:
        """导出给客户端。

        **总耗时取墙钟而不是各 span 之和。** span 是嵌套的
        （``step:N`` 里套着 ``skill:x``），求和会把子 span 的时间重复计一遍，
        界面上的"总耗时"会比真实值大出好几倍，用户拿它排查性能问题会被带偏。
        """
        ended = [s.end for s in self.spans if s.end is not None]
        total = round((max(ended) - self._t0) * 1000, 2) if ended else 0.0

        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "total_duration_ms": total,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            # 缓存命中量与命中率：这是验证「前缀缓存优化是否生效」的唯一手段
            "usage": self.usage.to_dict(),
            "spans": [s.to_dict(base=self._t0) for s in self.spans],
        }
