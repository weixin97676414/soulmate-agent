"""Trace 导出格式的单元测试。

重点盯住"总耗时"的口径：span 是嵌套的，求和会把子 span 的时间重复计一遍，
界面上的总耗时会虚高好几倍，用户拿它判断性能会被彻底带偏。
"""

from __future__ import annotations

import time

from my_agent.observability.tracer import Tracer


def test_nested_spans_do_not_inflate_total_duration():
    """嵌套 span 下，总耗时必须是墙钟而不是求和。

    构造：``step`` 总共约 100ms（先睡 50ms，再在 ``skill`` 里睡 50ms），
    其中 ``skill`` 占 50ms。两者是**串行**的，所以：
    - 真实墙钟 ≈ 100ms；
    - 朴素求和 ≈ 150ms，把子 span 的 50ms 重复算了一遍。

    这个 50% 的虚高就是被修掉的问题：界面上的"总耗时"看起来比实际慢得多，
    用户会去优化一个根本不存在的瓶颈。
    """
    tracer = Tracer()
    with tracer.span("step:1"):
        time.sleep(0.05)
        with tracer.span("skill:chart_generate"):
            time.sleep(0.05)

    data = tracer.export()
    span_sum = sum(span["duration_ms"] for span in data["spans"])

    assert 85 <= data["total_duration_ms"] <= 160, data["total_duration_ms"]
    # 求和明显虚高，这正是被修掉的问题
    assert span_sum > data["total_duration_ms"] * 1.3


def test_trace_summary_reads_the_real_duration_key():
    """`GET /v1/traces` 列表里的耗时**不能是 null**（契约不一致的回归钉）。

    ⚠️ `Tracer.export()` 产出的键叫 `total_duration_ms`，而 `TraceStore._summary`
    以前读的是 `payload.get("duration_ms")` —— 键名对不上，于是"最近几次执行"的
    耗时**永远是 null**，而底层其实已经采到了这个数。界面上那一列会整列空白，
    让人合理地以为性能数据坏了。
    """
    from my_agent.observability.trace_store import TraceStore

    tracer = Tracer()
    with tracer.span("agent"):
        pass

    store = TraceStore()
    store.put(tracer.trace_id, tracer.export())
    summary = store.recent(limit=1)[0]

    assert summary["trace_id"] == tracer.trace_id
    assert summary["duration_ms"] is not None, "摘要耗时不许是 null —— 键名要对上 export()"
    assert summary["spans"] == 1


def test_spans_carry_timeline_offsets():
    """前端画时间线靠 start_ms/end_ms，光有 duration 排不出先后与嵌套。"""
    tracer = Tracer()
    with tracer.span("step:1"):
        time.sleep(0.02)
        with tracer.span("skill:a"):
            time.sleep(0.02)
    with tracer.span("step:2"):
        time.sleep(0.01)

    spans = {span["name"]: span for span in tracer.export()["spans"]}

    # 子 span 必须落在父 span 的区间内
    assert spans["step:1"]["start_ms"] <= spans["skill:a"]["start_ms"]
    assert spans["skill:a"]["end_ms"] <= spans["step:1"]["end_ms"] + 1
    # 第二个 step 在第一个之后开始
    assert spans["step:2"]["start_ms"] >= spans["step:1"]["end_ms"] - 1
    # 所有偏移以 trace 起点为基准
    assert min(span["start_ms"] for span in spans.values()) >= 0


def test_parent_child_relationship_is_exported():
    tracer = Tracer()
    with tracer.span("step:1"):
        with tracer.span("skill:a"):
            pass

    spans = {span["name"]: span for span in tracer.export()["spans"]}
    assert "parent_id" not in spans["step:1"]
    assert spans["skill:a"]["parent_id"] == spans["step:1"]["span_id"]


def test_duration_covers_the_whole_task():
    """总耗时不能小于任何一个 span——否则时间线上的条形会画出边界外。"""
    tracer = Tracer()
    with tracer.span("step:1"):
        time.sleep(0.03)

    data = tracer.export()
    longest = max(span["duration_ms"] for span in data["spans"])
    assert data["total_duration_ms"] >= longest


def test_empty_trace_exports_zero_duration():
    data = Tracer().export()
    assert data["total_duration_ms"] == 0
    assert data["spans"] == []


def test_disabled_tracer_is_safe_to_use():
    """关闭追踪时，span 与 event 调用都必须是安全的空操作。

    重点是"调用方不需要写分支"，而不是"关闭后还能导出 span"——
    关闭时**不记录** span 是有意的：省内存，也不该假装有链路数据。
    """
    tracer = Tracer(enabled=False)
    with tracer.span("step:1") as span:
        span.event("start", x=1)
        with tracer.span("skill:a"):
            pass

    data = tracer.export()
    # 导出结构仍保持完整，前端不必为"追踪已关闭"写特例
    assert data["spans"] == []
    assert data["total_duration_ms"] == 0
    assert set(data) >= {"trace_id", "started_at", "total_tokens", "prompt_tokens", "completion_tokens"}


def test_usage_accumulates():
    tracer = Tracer()
    tracer.add_usage({"prompt_tokens": 10, "completion_tokens": 5})
    tracer.add_usage({"prompt_tokens": 3, "completion_tokens": 2})
    tracer.add_usage(None)

    data = tracer.export()
    assert data["prompt_tokens"] == 13
    assert data["completion_tokens"] == 7
    assert data["total_tokens"] == 20
