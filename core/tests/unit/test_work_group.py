







from __future__ import annotations

import pytest

from my_agent.agent.group_domain import parse_control, parse_dispatch
from my_agent.agent.work_discussion import (
    MAX_WORK_ROUNDS,
    _coordinator_context,
    _merge_outputs,
    _review_context,
    _worker_context,
)





def test_optimize_marker_carries_the_suggestion() -> None:
    clean, kind, reason = parse_control("这版还行，但开头太啰嗦。[OPTIMIZE] 把第一段压到两句以内")
    assert kind == "optimize"
    assert "两句以内" in reason
    assert "OPTIMIZE" not in clean


def test_no_optimize_wins_over_optimize() -> None:

    _, kind, _ = parse_control("没什么要改的。[NO_OPTIMIZE]")
    assert kind == "no_optimize"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("可以。[ACCEPT_OPT]", "accept_opt"),
        ("不用了。[DECLINE_OPT]", "decline_opt"),
        ("重做。[REDO]", "redo"),
        ("就这样交付。[FINAL]", "final"),
        ("能用了。[PASS]", "pass"),
    ],
)
def test_decision_markers(text: str, expected: str) -> None:
    _, kind, _ = parse_control(text)
    assert kind == expected


def test_reject_still_carries_reason() -> None:
    _, kind, reason = parse_control("不行。[REJECT] 少了价格对比")
    assert kind == "reject"
    assert "价格对比" in reason





def test_dispatch_parses_plain_json() -> None:
    text = '[DISPATCH]\n{"soulmate": "写登录页", "LoveBuddy": "写支付页"}\n[/DISPATCH]'
    assert parse_dispatch(text) == {"soulmate": "写登录页", "LoveBuddy": "写支付页"}


def test_dispatch_tolerates_code_fence_and_chatter() -> None:
    text = (
        "好的，分派如下：\n[DISPATCH]\n```json\n"
        '{"a": "任务A"}\n'
        "```\n[/DISPATCH]\n请各位开始。"
    )
    assert parse_dispatch(text) == {"a": "任务A"}


def test_dispatch_flattens_nested_object() -> None:

    text = '[DISPATCH]{"a": {"任务": "写稿", "要求": "800 字"}}[/DISPATCH]'
    parsed = parse_dispatch(text)
    assert parsed is not None
    assert "写稿" in parsed["a"] and "800 字" in parsed["a"]


@pytest.mark.parametrize(
    "text",
    ["没有分发块", "[DISPATCH]\n不是 JSON\n[/DISPATCH]", "[DISPATCH]{坏的}[/DISPATCH]", ""],
)
def test_dispatch_returns_none_on_bad_format(text: str) -> None:

    assert parse_dispatch(text) is None





def test_worker_context_has_task_and_previous_but_nothing_else() -> None:
    ctx = _worker_context(
        "写一份新品介绍",
        "你只负责开头 200 字",
        "上一轮写的开头（旧版）",
        "开头太啰嗦",
        "这次要改的地方",
    )
    assert "写一份新品介绍" in ctx
    assert "你只负责开头 200 字" in ctx
    assert "上一轮写的开头（旧版）" in ctx
    assert "开头太啰嗦" in ctx


def test_worker_context_first_round_has_no_previous_block() -> None:
    ctx = _worker_context("需求", "任务", "", "", "")
    assert "上一轮" not in ctx
    assert "这次要改" not in ctx


def test_review_context_is_only_topic_plus_deliverable() -> None:
    ctx = _review_context("需求", "交付物正文")
    assert "需求" in ctx and "交付物正文" in ctx
    
    assert "执行者" not in ctx


def test_coordinator_context_includes_previous_deliverable_on_rework() -> None:
    ctx = _coordinator_context("需求", "上一版交付物", "开头要压短", "优化员提出的改进要求")
    assert "上一版交付物" in ctx
    assert "开头要压短" in ctx
    assert "优化员提出的改进要求" in ctx


def test_merge_outputs_marks_each_worker() -> None:
    class _W:
        def __init__(self, i: str, n: str) -> None:
            self.id = i
            self.name = n

    merged = _merge_outputs([_W("a", "甲"), _W("b", "乙")], {"a": "A 的产出", "b": ""})
    assert "## 甲" in merged and "A 的产出" in merged
    assert "## 乙" in merged and "没有产出" in merged


def test_round_limit_is_three() -> None:

    assert MAX_WORK_ROUNDS == 3
