






from __future__ import annotations

import pytest

from my_agent.llm.base import ToolCall
from my_agent.memory.short_term import MemoryManager
from my_agent.observability.metrics import METRICS, Histogram
from my_agent.utils.chart import render_chart, render_pie





class TestCompressionBoundaryAlignment:







    @staticmethod
    def _conversation(tool_pairs: int, tail: int) -> MemoryManager:

        memory = MemoryManager()
        memory.ensure_system("你是助手")
        for index in range(tool_pairs):
            memory.add_assistant("", tool_calls=[ToolCall(id=f"c{index}", name="t", arguments={})])
            memory.add_tool(f"c{index}", "t", f"结果 {index}")
        for index in range(tail):
            memory.add_assistant(f"普通回答 {index}")
        return memory

    def test_boundary_never_lands_on_a_tool_message(self):
        memory = self._conversation(tool_pairs=6, tail=0)

        for keep_recent in range(0, 14):
            start, end = memory.compressible_range(keep_recent=keep_recent)
            if start < end < len(memory.messages):
                assert memory.messages[end].role != "tool", (
                    f"keep_recent={keep_recent} 时边界落在 tool 消息上，"
                    "摘要会把它的 assistant 吃掉"
                )

    @pytest.mark.parametrize("keep_recent", [1, 2, 3])
    def test_context_never_starts_with_orphan_tool(self, keep_recent):

        memory = self._conversation(tool_pairs=8, tail=1)
        start, end = memory.compressible_range(keep_recent=keep_recent)
        
        memory.set_summary("（早期对话摘要）", end)

        context = memory.get_context()

        assert context, "不该返回空上下文"
        assert context[0].role == "system"
        
        non_system = [m for m in context if m.role != "system"]
        assert non_system[0].role != "tool"

    def test_all_tool_pairs_survive_when_boundary_retreats(self):

        memory = self._conversation(tool_pairs=5, tail=0)

        start, end = memory.compressible_range(keep_recent=2)

        
        memory.set_summary("摘要", end)
        context = memory.get_context()
        roles = [m.role for m in context]

        for index, role in enumerate(roles):
            if role == "tool":
                assert index > 0 and roles[index - 1] in ("assistant", "tool"), (
                    "tool 消息前面没有 assistant(tool_calls)"
                )





class TestHistogramCumulativeBuckets:
    def test_bucket_counts_are_monotonic_in_prometheus_output(self):





        name = "test_sweep_histogram"
        for value in (5, 15, 15, 60, 300):
            METRICS.observe(name, value)

        lines = [
            line
            for line in METRICS.render_prometheus().splitlines()
            if line.startswith(f"{name}_bucket")
        ]
        counts = [int(line.rsplit(" ", 1)[1]) for line in lines]

        assert counts == sorted(counts), f"桶计数非单调：{counts}"
        
        assert counts[-1] == 5

    def test_internal_counts_stay_per_bucket(self):




        histogram = Histogram(buckets=[10.0, 100.0])
        for value in (5, 15, 15):
            histogram.observe(value)

        assert histogram.counts[:3] == [1, 2, 0]
        assert histogram.count == 3





class TestChartLengthValidation:
    def test_mismatched_length_raises(self):





        with pytest.raises(ValueError, match="数量必须一致"):
            render_chart(
                "bar",
                "测试",
                ["一", "二", "三"],
                [{"name": "系列", "values": [1.0, 2.0]}],
            )

    def test_extra_values_also_raise(self):
        with pytest.raises(ValueError, match="数量必须一致"):
            render_chart(
                "pie",
                "测试",
                ["一"],
                [{"name": "系列", "values": [1.0, 2.0, 3.0]}],
            )

    def test_error_names_the_series(self):

        with pytest.raises(ValueError, match="销售"):
            render_chart("bar", "t", ["a", "b"], [{"name": "销售", "values": [1.0]}])

    def test_matching_length_still_works(self):
        svg = render_chart(
            "bar", "测试", ["一", "二"], [{"name": "系列", "values": [1.0, 2.0]}]
        )

        assert svg.startswith("<svg") or "<svg" in svg

    def test_render_pie_guards_direct_callers(self):

        with pytest.raises(ValueError):
            render_pie("测试", ["一", "二", "三"], [1.0])





class TestImageTokenEstimate:
    def test_images_count_toward_context_usage(self):





        plain = MemoryManager()
        plain.add_user("看这张图")
        baseline = plain.context_tokens()

        with_image = MemoryManager()
        with_image.add_user("看这张图")
        from my_agent.llm.base import ImagePart

        with_image.add_user(
            "看这张图",
            images=[ImagePart(mime="image/png", data_url="data:image/png;base64,AAAA")],
        )
        
        assert with_image.context_tokens() > baseline

    def test_estimate_is_per_image_not_per_byte(self):

        from my_agent.llm.base import ImagePart

        memory = MemoryManager()
        memory.add_user(
            "x",
            images=[
                ImagePart(mime="image/png", data_url="data:image/png;base64," + "A" * 500_000)
            ],
        )

        
        assert memory.context_tokens() < 5000
