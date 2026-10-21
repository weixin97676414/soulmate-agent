









from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


PALETTE = [
    "#2563EB",
    "#16A34A",
    "#D97706",
    "#DC2626",
    "#7C3AED",
    "#0891B2",
    "#DB2777",
    "#65A30D",
]
INK = "#1F2329"
INK_SOFT = "#646A73"
INK_FAINT = "#8F959E"
LINE = "#E5E7EB"

FONT = "'Microsoft YaHei UI', 'Segoe UI', system-ui, sans-serif"

DEFAULT_WIDTH = 760
DEFAULT_HEIGHT = 440


def _escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _is_finite(value: Any) -> bool:







    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(
        float(value)
    )


def _finite(value: Any, default: float = 0.0) -> float:

    return float(value) if _is_finite(value) else default


def _nice_ceil(value: float) -> float:





    if not _is_finite(value) or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10.0**exponent
    fraction = value / base
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if fraction <= step:
            return step * base
    return 10 * base


def _nice_floor(value: float) -> float:
    if not _is_finite(value) or value >= 0:
        return 0.0
    return -_nice_ceil(-value)


def _format_number(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value / 10000:.1f}万"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _truncate(text: str, limit: int = 10) -> str:
    text = str(text)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


class _Frame:


    def __init__(self, title: str, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.title = title
        self.parts: list[str] = []
        self.legend: list[tuple[str, str]] = []

    def render(self) -> str:
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
            f'font-family="{FONT}">',
            f'<rect width="{self.width}" height="{self.height}" fill="#FFFFFF"/>',
        ]
        if self.title:
            head.append(
                f'<text x="{self.width / 2}" y="30" text-anchor="middle" '
                f'font-size="16" font-weight="600" fill="{INK}">{_escape(self.title)}</text>'
            )
        legend = self._render_legend()
        return "\n".join([*head, *self.parts, *legend, "</svg>"])

    def _render_legend(self) -> list[str]:
        if not self.legend:
            return []
        
        item_width = 110
        total = len(self.legend) * item_width
        start = (self.width - total) / 2
        out: list[str] = []
        for index, (label, color) in enumerate(self.legend):
            x = start + index * item_width
            out.append(
                f'<rect x="{x:.1f}" y="46" width="10" height="10" rx="2" fill="{color}"/>'
                f'<text x="{x + 15:.1f}" y="55" font-size="12" fill="{INK_SOFT}">'
                f"{_escape(_truncate(label, 8))}</text>"
            )
        return out


def _axes(
    frame: _Frame,
    *,
    left: float,
    right: float,
    top: float,
    bottom: float,
    y_min: float,
    y_max: float,
    ticks: int = 5,
) -> tuple[float, float]:

    height = bottom - top
    for index in range(ticks + 1):
        ratio = index / ticks
        value = y_min + (y_max - y_min) * ratio
        y = bottom - height * ratio
        frame.parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
            f'stroke="{LINE}" stroke-width="1"/>'
        )
        frame.parts.append(
            f'<text x="{left - 10:.1f}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{INK_FAINT}">{_escape(_format_number(value))}</text>'
        )
    
    frame.parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="{LINE}"/>'
    )
    return height


def _empty_state(frame: _Frame, message: str) -> str:
    frame.parts.append(
        f'<text x="{frame.width / 2}" y="{frame.height / 2}" text-anchor="middle" '
        f'font-size="13" fill="{INK_FAINT}">{_escape(message)}</text>'
    )
    return frame.render()





def render_bar(
    title: str,
    categories: Sequence[str],
    series: Sequence[dict[str, Any]],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    frame = _Frame(title, width, height)
    if not categories or not series:
        return _empty_state(frame, "没有可绘制的数据")

    values = [float(v) for item in series for v in item.get("values", [])]
    if not values:
        return _empty_state(frame, "没有可绘制的数据")

    left, right = 64.0, width - 24.0
    top, bottom = 76.0, height - 56.0
    y_min = _nice_floor(min(0.0, min(values)))
    y_max = _nice_ceil(max(values))
    if y_max == y_min:
        y_max = y_min + 1

    for index, item in enumerate(series):
        frame.legend.append((str(item.get("name") or f"系列{index + 1}"), PALETTE[index % len(PALETTE)]))

    plot_height = _axes(frame, left=left, right=right, top=top, bottom=bottom, y_min=y_min, y_max=y_max)

    slot = (right - left) / len(categories)
    group_width = slot * 0.66
    bar_width = group_width / max(len(series), 1)

    for group_index, category in enumerate(categories):
        group_x = left + slot * group_index + (slot - group_width) / 2
        for series_index, item in enumerate(series):
            raw = item.get("values") or []
            value = float(raw[group_index]) if group_index < len(raw) else 0.0
            bar_height = abs(value) / (y_max - y_min) * plot_height
            x = group_x + series_index * bar_width
            y = bottom - bar_height if value >= 0 else bottom
            color = PALETTE[series_index % len(PALETTE)]
            frame.parts.append(
                f'<rect x="{x + 1:.1f}" y="{y:.1f}" width="{max(bar_width - 2, 1):.1f}" '
                f'height="{max(bar_height, 0):.1f}" rx="3" fill="{color}"/>'
            )
            if len(categories) <= 14:
                frame.parts.append(
                    f'<text x="{x + bar_width / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                    f'font-size="10.5" fill="{INK_SOFT}">{_escape(_format_number(value))}</text>'
                )
        frame.parts.append(
            f'<text x="{group_x + group_width / 2:.1f}" y="{bottom + 20:.1f}" '
            f'text-anchor="middle" font-size="11.5" fill="{INK_SOFT}">'
            f"{_escape(_truncate(str(category)))}</text>"
        )
    return frame.render()





def render_line(
    title: str,
    categories: Sequence[str],
    series: Sequence[dict[str, Any]],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    frame = _Frame(title, width, height)
    if not categories or not series:
        return _empty_state(frame, "没有可绘制的数据")

    values = [float(v) for item in series for v in item.get("values", [])]
    if not values:
        return _empty_state(frame, "没有可绘制的数据")

    left, right = 64.0, width - 24.0
    top, bottom = 76.0, height - 56.0
    y_min = _nice_floor(min(0.0, min(values)))
    y_max = _nice_ceil(max(values))
    if y_max == y_min:
        y_max = y_min + 1

    for index, item in enumerate(series):
        frame.legend.append((str(item.get("name") or f"系列{index + 1}"), PALETTE[index % len(PALETTE)]))

    plot_height = _axes(frame, left=left, right=right, top=top, bottom=bottom, y_min=y_min, y_max=y_max)

    step = (right - left) / max(len(categories) - 1, 1)
    for series_index, item in enumerate(series):
        raw = item.get("values") or []
        color = PALETTE[series_index % len(PALETTE)]
        points: list[tuple[float, float]] = []
        for index in range(len(categories)):
            value = float(raw[index]) if index < len(raw) else 0.0
            x = left + step * index
            y = bottom - (value - y_min) / (y_max - y_min) * plot_height
            points.append((x, y))
        if not points:
            continue
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        frame.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x, y in points:
            frame.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    
    stride = max(1, len(categories) // 12)
    for index, category in enumerate(categories):
        if index % stride:
            continue
        x = left + step * index
        frame.parts.append(
            f'<text x="{x:.1f}" y="{bottom + 20:.1f}" text-anchor="middle" '
            f'font-size="11.5" fill="{INK_SOFT}">{_escape(_truncate(str(category)))}</text>'
        )
    return frame.render()





def render_pie(
    title: str,
    categories: Sequence[str],
    values: Sequence[float],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    frame = _Frame(title, width, height)
    
    
    
    data = [(str(c), float(v)) for c, v in zip(categories, values, strict=True) if float(v) > 0]
    if not data:
        return _empty_state(frame, "没有可绘制的数据")

    total = sum(v for _, v in data)
    center_x = width * 0.36
    center_y = height / 2 + 6
    radius = min(width * 0.28, height * 0.34)

    angle = -math.pi / 2  
    
    for index, (_category, value) in enumerate(data):
        ratio = value / total
        sweep = ratio * 2 * math.pi
        end = angle + sweep
        large_arc = 1 if sweep > math.pi else 0
        x1 = center_x + radius * math.cos(angle)
        y1 = center_y + radius * math.sin(angle)
        x2 = center_x + radius * math.cos(end)
        y2 = center_y + radius * math.sin(end)
        color = PALETTE[index % len(PALETTE)]

        
        if len(data) == 1:
            frame.parts.append(
                f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{radius:.1f}" fill="{color}"/>'
            )
        else:
            path = (
                f'<path d="M {center_x:.1f} {center_y:.1f} '
                f'L {x1:.1f} {y1:.1f} '
                f'A {radius:.1f} {radius:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} Z" '
                f'fill="{color}"/>'
            )
            frame.parts.append(path)
        angle = end

    
    legend_x = center_x + radius + 44
    legend_y = center_y - len(data) * 11
    for index, (category, value) in enumerate(data):
        color = PALETTE[index % len(PALETTE)]
        y = legend_y + index * 24
        frame.parts.append(
            f'<rect x="{legend_x:.1f}" y="{y - 9:.1f}" width="10" height="10" rx="2" fill="{color}"/>'
        )
        frame.parts.append(
            f'<text x="{legend_x + 16:.1f}" y="{y:.1f}" font-size="12" fill="{INK}">'
            f"{_escape(_truncate(category, 8))}</text>"
        )
        frame.parts.append(
            f'<text x="{legend_x + 130:.1f}" y="{y:.1f}" font-size="12" fill="{INK_SOFT}">'
            f"{_escape(_format_number(value))}（{value / total * 100:.1f}%）</text>"
        )
    return frame.render()





CHART_TYPES = ("bar", "line", "pie")


def render_chart(
    chart_type: str,
    title: str,
    categories: Sequence[str],
    series: Sequence[dict[str, Any]],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:













    normalized = (chart_type or "bar").strip().lower()
    if normalized not in CHART_TYPES:
        raise ValueError(f"不支持的图表类型「{chart_type}」，可用值：{', '.join(CHART_TYPES)}")

    expected = len(categories)
    for index, item in enumerate(series):
        values = item.get("values") or []
        if len(values) != expected:
            name = str(item.get("name") or f"系列{index + 1}")
            raise ValueError(
                f"categories 有 {expected} 项，但「{name}」的 values 有 {len(values)} 项，"
                "两者数量必须一致。请补齐缺失的值（没有数据的位置填 0），不要省略。"
            )

    if normalized == "pie":
        first = series[0] if series else {"values": []}
        return render_pie(title, categories, first.get("values") or [], width=width, height=height)
    if normalized == "line":
        return render_line(title, categories, series, width=width, height=height)
    return render_bar(title, categories, series, width=width, height=height)
