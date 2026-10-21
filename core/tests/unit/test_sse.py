













from __future__ import annotations

from decimal import Decimal

from my_agent.server.sse import format_sse, parse_sse


def test_frame_round_trips():
    frame = format_sse("delta", {"text": "你好", "n": 1})
    assert frame == 'event: delta\ndata: {"text": "你好", "n": 1}\n\n'
    assert parse_sse(frame) == ("delta", {"text": "你好", "n": 1})


def test_non_json_native_values_do_not_break_the_frame():




    frame = format_sse("usage", {"cost": Decimal("1.20")})
    assert parse_sse(frame) == ("usage", {"cost": "1.20"})


def test_parse_tolerates_garbage():

    
    assert parse_sse(": ping\n\n") is None
    
    assert parse_sse("event: x\ndata: {bad json\n\n") is None
    
    assert parse_sse("event: x\ndata: [1,2]\n\n") == ("x", {})
