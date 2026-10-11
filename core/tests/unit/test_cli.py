"""命令行接口。

重点测两处容易退化的地方：
- ``replay`` 的**层级还原**（span 的 parent_id 决定缩进，是"哪一步最慢"的答案）；
- ``replay`` 对**损坏行**的容忍（trace 文件常被人工编辑过，
  一行坏格式不该让整份读不了 —— 那对排查反而是阻碍）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_agent.server.cli import build_parser, main


class TestParser:
    def test_parses_skills(self):
        args = build_parser().parse_args(["skills", "list", "--all"])

        assert args.command == "skills"
        assert args.all is True

    def test_parses_run(self):
        args = build_parser().parse_args(["run", "帮我算一下", "--model", "m1", "--quiet"])

        assert args.prompt == "帮我算一下"
        assert args.model == "m1"
        assert args.quiet is True

    def test_requires_subcommand(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])


def real_trace_header() -> dict:
    """用 ``Tracer.export()`` 的**真实产物**当 trace 头，而不是手写一份。

    ⚠️ 原来这里写的是 `{"kind": "trace", "trace_id": "abc", "duration_ms": 12}` ——
    而 `export()` 产出的键叫 `total_duration_ms`。于是"回放能显示耗时"这条路径
    看着**被测过**，线上却永远打印 `耗时 Nonems`：**真缺陷被这份假数据盖住了**。
    """
    from my_agent.observability.tracer import Tracer

    tracer = Tracer()
    with tracer.span("agent"):
        pass
    payload = tracer.export()
    payload.pop("spans", None)  # 头行只放元信息，span 由用例自己给
    return {"kind": "trace", **payload}


def write_trace(path: Path, spans: list[dict], header: dict | None = None) -> None:
    lines = [json.dumps(header or real_trace_header())]
    lines += [json.dumps({"kind": "span", **span}) for span in spans]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestReplay:
    def test_renders_hierarchy(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        """子 span 要缩进 —— 平铺输出看不出"这一步属于哪个阶段"。"""
        target = tmp_path / "t.jsonl"
        write_trace(
            target,
            [
                {"span_id": "root", "name": "agent", "parent_id": None, "status": "ok"},
                {"span_id": "s1", "name": "step:1", "parent_id": "root", "status": "ok"},
                {"span_id": "s2", "name": "skill:calc", "parent_id": "s1", "status": "ok"},
            ],
        )

        assert main(["replay", str(target)]) == 0
        out = capsys.readouterr().out

        assert "共 3 个 span" in out
        # ⚠️ 耗时不许打成 `None`：头行用的就是 `Tracer.export()` 的真实产物，
        # 键名对不上时这里会露出 `耗时 Nonems`（以前正是这样，却被假数据盖住了）
        assert "耗时 None" not in out

        def indent_of(keyword: str) -> int:
            line = next(line for line in out.splitlines() if keyword in line)
            return len(line) - len(line.lstrip())

        # 三层缩进：root 无缩进，step:1 更深，skill:calc 更深
        assert indent_of("agent") < indent_of("step:1") < indent_of("skill:calc")

    def test_marks_errors(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        target = tmp_path / "t.jsonl"
        write_trace(
            target,
            [
                {
                    "span_id": "s1",
                    "name": "skill:broken",
                    "parent_id": None,
                    "status": "error",
                    "error": "boom",
                }
            ],
        )

        main(["replay", str(target)])
        out = capsys.readouterr().out

        assert "✗" in out
        assert "boom" in out

    def test_tolerates_broken_line(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        """一行坏格式不该让整份 trace 读不了。"""
        target = tmp_path / "t.jsonl"
        write_trace(target, [{"span_id": "s1", "name": "ok_span", "parent_id": None}])
        target.write_text(
            target.read_text(encoding="utf-8") + "{这不是 JSON\n", encoding="utf-8"
        )

        assert main(["replay", str(target)]) == 0
        captured = capsys.readouterr()

        assert "已跳过" in captured.err
        # 好行照样渲染出来
        assert "ok_span" in captured.out

    def test_missing_file_returns_error_code(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        assert main(["replay", str(tmp_path / "nope.jsonl")]) == 2
        assert "不存在" in capsys.readouterr().err

    def test_json_output_is_machine_readable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        target = tmp_path / "t.jsonl"
        write_trace(target, [{"span_id": "s1", "name": "a", "parent_id": None}])

        main(["replay", str(target), "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert isinstance(payload, list)
        assert payload[-1]["name"] == "a"
