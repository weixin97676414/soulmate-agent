





from __future__ import annotations

import time

from my_agent.observability.tracer import Tracer


def test_nested_spans_do_not_inflate_total_duration():










    tracer = Tracer()
    with tracer.span("step:1"):
        time.sleep(0.05)
        with tracer.span("skill:chart_generate"):
            time.sleep(0.05)

    data = tracer.export()
    span_sum = sum(span["duration_ms"] for span in data["spans"])

    assert 85 <= data["total_duration_ms"] <= 160, data["total_duration_ms"]
    
    assert span_sum > data["total_duration_ms"] * 1.3


def test_trace_summary_reads_the_real_duration_key():







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

    tracer = Tracer()
    with tracer.span("step:1"):
        time.sleep(0.02)
        with tracer.span("skill:a"):
            time.sleep(0.02)
    with tracer.span("step:2"):
        time.sleep(0.01)

    spans = {span["name"]: span for span in tracer.export()["spans"]}

    
    assert spans["step:1"]["start_ms"] <= spans["skill:a"]["start_ms"]
    assert spans["skill:a"]["end_ms"] <= spans["step:1"]["end_ms"] + 1
    
    assert spans["step:2"]["start_ms"] >= spans["step:1"]["end_ms"] - 1
    
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





    tracer = Tracer(enabled=False)
    with tracer.span("step:1") as span:
        span.event("start", x=1)
        with tracer.span("skill:a"):
            pass

    data = tracer.export()
    
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
