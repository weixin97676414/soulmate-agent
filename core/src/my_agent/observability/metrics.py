



















from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


LATENCY_BUCKETS_MS: tuple[float, ...] = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)


@dataclass
class Histogram:





    buckets: tuple[float, ...] = LATENCY_BUCKETS_MS
    
    
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            
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


    def __init__(self) -> None:
        
        
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], Histogram] = {}
        self._lock = threading.Lock()

    
    
    
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
        
        with self._lock:
            histogram.observe(value)

    def reset(self) -> None:

        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    
    
    
    def snapshot(self) -> dict[str, Any]:

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
    
    return str(int(value)) if float(value).is_integer() else str(value)



METRICS = Metrics()

__all__ = ["LATENCY_BUCKETS_MS", "METRICS", "Histogram", "Metrics"]
