







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






    from my_agent.observability.tracer import Tracer

    tracer = Tracer()
    with tracer.span("agent"):
        pass
    payload = tracer.export()
    payload.pop("spans", None)  
    return {"kind": "trace", **payload}


def write_trace(path: Path, spans: list[dict], header: dict | None = None) -> None:
    lines = [json.dumps(header or real_trace_header())]
    lines += [json.dumps({"kind": "span", **span}) for span in spans]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestReplay:
    def test_renders_hierarchy(self, tmp_path: Path, capsys: pytest.CaptureFixture):

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
        
        
        assert "耗时 None" not in out

        def indent_of(keyword: str) -> int:
            line = next(line for line in out.splitlines() if keyword in line)
            return len(line) - len(line.lstrip())

        
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

        target = tmp_path / "t.jsonl"
        write_trace(target, [{"span_id": "s1", "name": "ok_span", "parent_id": None}])
        target.write_text(
            target.read_text(encoding="utf-8") + "{这不是 JSON\n", encoding="utf-8"
        )

        assert main(["replay", str(target)]) == 0
        captured = capsys.readouterr()

        assert "已跳过" in captured.err
        
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
