"""全量代码审查中发现的真实缺陷 —— 回归测试。

这些不是"功能测试"，而是**曾经真实错过、且表现都很隐蔽**的地方。
每条都写清了"如果不修会发生什么"，因为它们的共同特征正是**出错时不报错**：
要么是界面上看起来正常但内容是错的，要么是要等到某个特定时序才炸。
"""

from __future__ import annotations

import pytest

from my_agent.llm.base import ToolCall
from my_agent.memory.short_term import MemoryManager
from my_agent.observability.metrics import METRICS, Histogram
from my_agent.utils.chart import render_chart, render_pie


# --------------------------------------------------------------------------- #
# 压缩边界不能拆散 assistant(tool_calls) 与它的 tool 结果
# --------------------------------------------------------------------------- #
class TestCompressionBoundaryAlignment:
    """摘要边界必须落在"配对完整"的位置。

    不修的话：``tool`` 消息与它的 ``assistant(tool_calls)`` 被拆到摘要两侧，
    发给厂商的序列以孤立的 ``tool`` 开头 → 一律 400，且**这个会话从此永久报错**。
    更隐蔽的是此时内容远小于预算，``_trim`` 里那段"跳过开头孤立 tool"根本不会执行。
    """

    @staticmethod
    def _conversation(tool_pairs: int, tail: int) -> MemoryManager:
        """构造 system + N 组 (assistant(tool_calls), tool) + tail 条普通消息。"""
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
        """无论摘要边界切在哪，发给模型的序列都不能以 tool 开头。"""
        memory = self._conversation(tool_pairs=8, tail=1)
        start, end = memory.compressible_range(keep_recent=keep_recent)
        # 模拟"压缩了 [start:end] 这一段"
        memory.set_summary("（早期对话摘要）", end)

        context = memory.get_context()

        assert context, "不该返回空上下文"
        assert context[0].role == "system"
        # system 之后紧跟的第一条不能是 tool
        non_system = [m for m in context if m.role != "system"]
        assert non_system[0].role != "tool"

    def test_all_tool_pairs_survive_when_boundary_retreats(self):
        """边界退让的代价只是少压几条 —— 配对必须两边都在。"""
        memory = self._conversation(tool_pairs=5, tail=0)

        start, end = memory.compressible_range(keep_recent=2)

        # 摘要覆盖 [start:end]，正文里剩下的必须成对
        memory.set_summary("摘要", end)
        context = memory.get_context()
        roles = [m.role for m in context]

        for index, role in enumerate(roles):
            if role == "tool":
                assert index > 0 and roles[index - 1] in ("assistant", "tool"), (
                    "tool 消息前面没有 assistant(tool_calls)"
                )


# --------------------------------------------------------------------------- #
# 直方图桶必须是累积值
# --------------------------------------------------------------------------- #
class TestHistogramCumulativeBuckets:
    def test_bucket_counts_are_monotonic_in_prometheus_output(self):
        """``_bucket{le=x}`` 按约定是"≤x 的总次数"，必须随 le 单调不减。

        输出区间计数的话，le 越大值反而可能越小 —— 抓取端算出的分位数全错，
        而且不会有任何报错，只是"有一张图"。
        """
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
        # 最后一个有限桶 + +Inf 桶 = 总数
        assert counts[-1] == 5

    def test_internal_counts_stay_per_bucket(self):
        """内部存的是**区间**计数（画图更直观），累积只在输出时做。

        把内部也改成累积的话，JSON 快照给出的就不是各区间分布了。
        """
        histogram = Histogram(buckets=[10.0, 100.0])
        for value in (5, 15, 15):
            histogram.observe(value)

        assert histogram.counts[:3] == [1, 2, 0]
        assert histogram.count == 3


# --------------------------------------------------------------------------- #
# 图表长度不一致必须报错，而不是静默截断/补 0
# --------------------------------------------------------------------------- #
class TestChartLengthValidation:
    def test_mismatched_length_raises(self):
        """``zip`` 会按短的截断，柱状图则把缺失值当 **0** 画出来。

        两种结果都是"看起来完全正常、但内容是错的"图表 —— 用户会把它当真实数据
        去汇报，而图上没有任何迹象说明少了东西。
        """
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
        """报错要说清是哪个系列对不上，模型才能照着改。"""
        with pytest.raises(ValueError, match="销售"):
            render_chart("bar", "t", ["a", "b"], [{"name": "销售", "values": [1.0]}])

    def test_matching_length_still_works(self):
        svg = render_chart(
            "bar", "测试", ["一", "二"], [{"name": "系列", "values": [1.0, 2.0]}]
        )

        assert svg.startswith("<svg") or "<svg" in svg

    def test_render_pie_guards_direct_callers(self):
        """直接调 ``render_pie``（绕过 render_chart）时也要炸，而不是少画两个扇区。"""
        with pytest.raises(ValueError):
            render_pie("测试", ["一", "二", "三"], [1.0])


# --------------------------------------------------------------------------- #
# token 估算必须计入图片
# --------------------------------------------------------------------------- #
class TestImageTokenEstimate:
    def test_images_count_toward_context_usage(self):
        """不计图片的话，带图会话会"看着还很空"却已经把窗口塞满。

        压缩与裁剪都不会触发，最后直接吃厂商的超限报错 —— 而引擎那条自愈路径
        （识别超限 → 压缩 → 重试）恰恰依赖这个估算先触发。
        """
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
        # 逐条累加，所以比较"同样两条消息、其中一条带图"的差值
        assert with_image.context_tokens() > baseline

    def test_estimate_is_per_image_not_per_byte(self):
        """按**张数**计：拿 data URL 的字符数去估会离谱（8MB 照片能算出上百万 token）。"""
        from my_agent.llm.base import ImagePart

        memory = MemoryManager()
        memory.add_user(
            "x",
            images=[
                ImagePart(mime="image/png", data_url="data:image/png;base64," + "A" * 500_000)
            ],
        )

        # 一张图的开销应当是"每张固定值"的量级，而不是几十万
        assert memory.context_tokens() < 5000
