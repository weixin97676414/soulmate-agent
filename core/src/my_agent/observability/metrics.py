"""进程内指标（计数器 + 直方图）。

对应《智能体框架开发文档》11.4 节。

## 为什么是模块级单例

指标天生是"到处都要埋点"的东西。如果走依赖注入，从 ``runtime`` 一路传到
``SkillManager``、适配器、MCP 客户端……每个构造函数都要多一个参数，
而它们大多数本来与可观测性无关。``logging`` 就是这么做的，这里保持一致。

代价是**测试之间会互相污染**（计数累加）。所以提供了 ``reset()``，
并且测试里按需调用。

## 为什么自己写而不是引 prometheus_client

那个库会带来额外的打包体积，而我们只需要计数器、直方图和一个文本端点。
桌面客户端的指标是给**用户自己**看的（"这个月调了多少次模型"），
不是给集群监控抓的，用不上它的高级特性。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# 延迟直方图的桶（毫秒）。取值覆盖"本地模型几十毫秒"到"云端超时前几秒"。
LATENCY_BUCKETS_MS: tuple[float, ...] = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)


@dataclass
class Histogram:
    """极简直方图：只保留桶计数与总和。

    不保留原始样本 —— 那会让内存随请求量线性增长，而指标用途只需要分位数近似。
    """

    buckets: tuple[float, ...] = LATENCY_BUCKETS_MS
    # **各区间自己的计数**（不是累积值）。要输出成 Prometheus 的
    # ``_bucket{le=...}`` 必须先做前缀累加 —— 见 render_prometheus。
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            # 多一个 +Inf 桶，和 Prometheus 的约定一致
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.total += value
        self.count += 1
        for index, bound in enumerate(self.buckets):
            if value <= bound:
                self.counts[index] += 1
                return
        self.counts[-1] += 1


class Metrics:
    """计数器与直方图的容器。"""

    def __init__(self) -> None:
        # 用 defaultdict 而不是普通 dict + 判空：埋点代码应当保持一行，
        # 否则"顺手加个指标"这件事的成本会劝退后来的人
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], Histogram] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    @staticmethod
    def _labels(labels: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def inc(self, name: str, value: float = 1.0, **labels: Any) -> None:
        with self._lock:
            self._counters[(name, self._labels(labels))] += value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = (name, self._labels(labels))
        with self._lock:
            histogram = self._histograms.get(key)
            if histogram is None:
                histogram = Histogram()
                self._histograms[key] = histogram
        # observe 内部只改自己的列表，但为了简单仍然串行化
        with self._lock:
            histogram.observe(value)

    def reset(self) -> None:
        """清空所有指标（测试用）。"""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        """返回结构化快照（JSON 端点用）。"""
        with self._lock:
            counters = [
                {"name": name, "labels": dict(labels), "value": value}
                for (name, labels), value in sorted(self._counters.items())
            ]
            histograms = [
                {
                    "name": name,
                    "labels": dict(labels),
                    "count": histogram.count,
                    "sum_ms": round(histogram.total, 3),
                    "avg_ms": round(histogram.total / histogram.count, 3)
                    if histogram.count
                    else 0.0,
                    "buckets": {
                        str(bound): histogram.counts[index]
                        for index, bound in enumerate(histogram.buckets)
                    },
                }
                for (name, labels), histogram in sorted(self._histograms.items())
            ]
        return {"counters": counters, "histograms": histograms}

    def render_prometheus(self) -> str:
        """Prometheus 文本格式。

        自带直方图的 ``_bucket{le=...}`` / ``_sum`` / ``_count`` 三元组约定，
        这样即使用户拿它接真正的监控，也不需要我们再改一次格式。
        """
        lines: list[str] = []
        seen_types: set[str] = set()

        with self._lock:
            counters = sorted(self._counters.items())
            histograms = sorted(self._histograms.items())

        for (name, labels), value in counters:
            if name not in seen_types:
                lines.append(f"# TYPE {name} counter")
                seen_types.add(name)
            lines.append(f"{name}{_format_labels(labels)} {_format_value(value)}")

        for (name, labels), histogram in histograms:
            if name not in seen_types:
                lines.append(f"# TYPE {name} histogram")
                seen_types.add(name)
            # ``_bucket{le=x}`` 按约定必须是**累积**计数（≤ x 的总次数），
            # 而 ``counts`` 存的是各区间自己的计数（画直方图时更直观）。
            #
            # 把区间计数直接当累积值输出，会让 ``le`` 越大值反而越小 ——
            # 抓取端算出来的分位数全是错的，而且**不会报任何错**，
            # 只是看着有一张图而已。这里累加一次再输出。
            cumulative = 0
            for index, bound in enumerate(histogram.buckets):
                cumulative += histogram.counts[index]
                bucket_labels = (*labels, ("le", str(bound)))
                lines.append(f"{name}_bucket{_format_labels(bucket_labels)} {cumulative}")
            inf_labels = (*labels, ("le", "+Inf"))
            lines.append(f"{name}_bucket{_format_labels(inf_labels)} {histogram.count}")
            lines.append(f"{name}_sum{_format_labels(labels)} {_format_value(histogram.total)}")
            lines.append(f"{name}_count{_format_labels(labels)} {histogram.count}")

        return "\n".join(lines) + "\n" if lines else ""


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{key}="{_escape(value)}"' for key, value in labels)
    return "{" + inner + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_value(value: float) -> str:
    # 整数就不要带小数点，读起来清爽
    return str(int(value)) if float(value).is_integer() else str(value)


# 进程级单例。埋点处直接 ``METRICS.inc(...)``。
METRICS = Metrics()

__all__ = ["LATENCY_BUCKETS_MS", "METRICS", "Histogram", "Metrics"]
