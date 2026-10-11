"""最小 iCalendar 读写（只覆盖 VEVENT）。

## 为什么自己写，而不是引 `icalendar` / `caldav`

本项目的需求很窄：列出某段时间的日程、新建、修改、删除。对应的 iCalendar 语法
也就 VEVENT 的七八个字段。而那两个库会连带引入 `requests` / `recurring-ical-events`
等一串依赖，冻结产物已经 918 MB，每加一个包都要同时改打包脚本、并承担 onedir 下
原生依赖的风险。

## 明确不支持的（如实写在这里，也写进技能说明与文档）

- **不展开 RRULE 重复事件**：带 `RRULE` 的日程会原样保留规则（读写都不丢），
  但不会展开成一条条实例 —— 所以"每周例会"在列表里只出现一条。
- `TZID=...` 的时间按**本机时间**处理（`Z` 结尾的 UTC 是正确的）；
  跨时区团队用这个功能时要自己换算。

## 时间用什么表示

对外统一是**本地时间（naive datetime）**：用户在界面上说"九点开会"，
他指的就是本机九点。序列化时写成浮动时间（不带 `Z`、不带 `TZID`），
避免"我明明设的九点，怎么变成了八点"这种时区困惑。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

#: iCalendar 的折行规则是"75 个八位组"，不是 75 个字符 ——
#: 中文一个字占 3 个字节，按字符折行会让某些严格解析器读不出内容。
_FOLD_BYTES = 75

_DT_FORMATS = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M")
_ESC = {"\\": "\\\\", ";": "\\;", ",": "\\,", "\n": "\\n", "\r": ""}


@dataclass
class CalendarEvent:
    """一条日程。``start`` / ``end`` 是**本地时间**。"""

    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str = ""
    description: str = ""
    all_day: bool = False
    #: 原始 RRULE（不展开，只原样保留），空串表示不重复
    recurrence: str = ""
    #: 其它不认识的属性（原样保留，避免我们改写文件时把别人的字段吃掉）
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """给技能返回值用的表示（ISO 字符串 + 人话）。"""
        duration_minutes = int((self.end - self.start).total_seconds() // 60)
        return {
            "uid": self.uid,
            "summary": self.summary,
            "start": self.start.isoformat(timespec="minutes"),
            "end": self.end.isoformat(timespec="minutes"),
            "all_day": self.all_day,
            "location": self.location,
            "description": self.description,
            "duration_minutes": duration_minutes,
            "repeats": self.recurrence or None,
            "text": f"{self.summary}（{_human_range(self) }）",
        }


def _human_range(event: CalendarEvent) -> str:
    if event.all_day:
        return f"{event.start:%Y-%m-%d} 全天"
    if event.start.date() == event.end.date():
        return f"{event.start:%Y-%m-%d %H:%M}–{event.end:%H:%M}"
    return f"{event.start:%Y-%m-%d %H:%M} – {event.end:%m-%d %H:%M}"


def apply_changes(
    event: CalendarEvent,
    changes: dict[str, Any],
    *,
    default_duration: timedelta = timedelta(minutes=60),
) -> CalendarEvent:
    """把一次「修改日程」的字段合并到旧事件上，返回新事件。

    ## 为什么单独抽这一个纯函数

    本地 .ics 与 CalDAV 两个后端各写一遍合并逻辑，迟早会分叉 —— 而这里的规则
    **不是"照抄传进来的字段"**：

    **只改开始时间时，结束时间要按原时长顺延。** 否则把 10:00–10:30 改到 15:00
    会得到 15:00–10:30（时长为负），而这条数据会被原样写回 .ics / CalDAV，
    并作为结果回给模型 —— 属于"不报错、只是时间变得莫名其妙"的那种错。

    ## 规则

    - 只给 ``start``：``end = start + 原时长``（原时长 ≤0 时用 ``default_duration`` 兜底）
    - 同时给 ``start`` 与 ``end``：以显式 ``end`` 为准，不顺延
    - 只给 ``end``：只改 end（保持既有行为，不反向推 start）
    - 结果一律校验 ``end > start``，否则抛 ``ValueError``（与「新建」路径的校验一致）

    值为 ``None`` 的字段表示"这次不动它" —— 沿用后端原先的过滤语义。
    """
    patch = {key: value for key, value in changes.items() if value is not None}
    start = patch.get("start", event.start)
    if "end" in patch:
        end = patch["end"]
    elif "start" in patch:
        # 只挪了开始时间：按原时长顺延，否则会凭空产生负数时长
        duration = event.end - event.start
        if duration <= timedelta(0):
            duration = default_duration
        end = start + duration
        patch["end"] = end
    else:
        end = event.end

    if end <= start:
        raise ValueError("结束时间必须晚于开始时间。")

    return replace(event, **patch)


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def _unescape(value: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            out.append({"n": "\n", "N": "\n"}.get(nxt, nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _parse_datetime(value: str, params: dict[str, str]) -> tuple[datetime, bool]:
    """解析 ``DTSTART`` / ``DTEND`` 的值，返回 ``(本地时间, 是否全天)``。"""
    raw = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", raw):
        parsed_date = datetime.strptime(raw, "%Y%m%d")
        return parsed_date, True

    is_utc = raw.endswith("Z")
    if is_utc:
        raw = raw[:-1]
    for fmt in _DT_FORMATS:
        try:
            moment = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if is_utc:
            # UTC 要换成本机时间再对外表示，否则用户会看到差 8 小时的时间
            moment = moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)
        return moment, False
    raise ValueError(f"无法识别的时间格式：{value}")


def _split_line(line: str) -> tuple[str, dict[str, str], str]:
    """把 ``DTSTART;TZID=Asia/Shanghai:20260923T090000`` 拆成三段。"""
    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for item in parts[1:]:
        key, _, raw = item.partition("=")
        params[key.upper()] = raw.strip('"')
    return name, params, value


def _unfold(text: str) -> list[str]:
    """把折行还原成逻辑行（iCalendar 用 CRLF + 一个空格表示"这行是上行的续行"）。"""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_events(text: str) -> list[CalendarEvent]:
    """从 iCalendar 文本里取出所有 VEVENT。解析不出来的整条跳过。"""
    events: list[CalendarEvent] = []
    current: dict[str, object] | None = None
    current_extra: dict[str, str] = {}

    for line in _unfold(text or ""):
        if not line.strip():
            continue
        name, params, value = _split_line(line)
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            current, current_extra = {}, {}
            continue
        if name == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                events.append(_build_event(current, current_extra))
            current, current_extra = None, {}
            continue
        if current is None:
            continue

        if name == "DTSTART":
            current["start"], current["all_day"] = _parse_datetime(value, params)
        elif name == "DTEND":
            current["end"], _ = _parse_datetime(value, params)
        elif name in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID", "RRULE"):
            current[name.lower()] = _unescape(value) if name != "RRULE" else value.strip()
        else:
            # 其它字段原样留着，改写文件时再写回去
            current_extra[name] = value

    return events


def _build_event(fields: dict[str, object], extra: dict[str, str]) -> CalendarEvent:
    start = fields.get("start")
    if not isinstance(start, datetime):
        raise ValueError("VEVENT 缺少 DTSTART")
    end = fields.get("end")
    if not isinstance(end, datetime):
        # 没有结束时间：全天事件算一天，其余按一小时（写回时会补上 DTEND）
        end = start + timedelta(days=1) if fields.get("all_day") else start + timedelta(hours=1)

    return CalendarEvent(
        uid=str(fields.get("uid") or uuid.uuid4().hex),
        summary=str(fields.get("summary") or "(无标题)"),
        start=start,
        end=end,
        location=str(fields.get("location") or ""),
        description=str(fields.get("description") or ""),
        all_day=bool(fields.get("all_day")),
        recurrence=str(fields.get("rrule") or ""),
        extra=dict(extra),
    )


# --------------------------------------------------------------------------- #
# 序列化
# --------------------------------------------------------------------------- #
def _escape(value: str) -> str:
    out = []
    for char in value or "":
        out.append(_ESC.get(char, char))
    return "".join(out)


def _fold(line: str) -> str:
    """按**字节**折行（中文一个字 3 字节，按字符折会超长）。

    ⚠️ 续行前面那个空格**算在 75 字节里** —— 所以续行本身最多只能放 74 字节。
    按 75 字节切而不管这个空格，结果就是"每条续行都超 1 字节"，
    严格解析器（Google/苹果的日历导入）会直接拒收整份文件。
    """
    if len(line.encode("utf-8")) <= _FOLD_BYTES:
        return line

    chunks: list[bytes] = []
    current = b""
    limit = _FOLD_BYTES
    for char in line:
        piece = char.encode("utf-8")
        if len(current) + len(piece) > limit:
            chunks.append(current)
            current = piece
            limit = _FOLD_BYTES - 1  # 续行以空格开头
        else:
            current += piece
    if current:
        chunks.append(current)
    head, *rest = chunks
    return "\r\n ".join([head.decode("utf-8")] + [chunk.decode("utf-8") for chunk in rest])


def _format_datetime(moment: datetime, all_day: bool) -> tuple[str, dict[str, str]]:
    if all_day:
        return moment.strftime("%Y%m%d"), {"VALUE": "DATE"}
    return moment.strftime("%Y%m%dT%H%M%S"), {}


def build_ics(events: list[CalendarEvent], *, calendar_name: str = "我的日程") -> str:
    """把日程序列化成一整份 iCalendar 文本。"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Soulmate Agent//Calendar//CN",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    for event in events:
        start_value, start_params = _format_datetime(event.start, event.all_day)
        end_value, end_params = _format_datetime(event.end, event.all_day)
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{event.uid}")
        lines.append(f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}")
        lines.append(_with_params("DTSTART", start_params, start_value))
        lines.append(_with_params("DTEND", end_params, end_value))
        lines.append(f"SUMMARY:{_escape(event.summary)}")
        if event.location:
            lines.append(f"LOCATION:{_escape(event.location)}")
        if event.description:
            lines.append(f"DESCRIPTION:{_escape(event.description)}")
        if event.recurrence:
            lines.append(f"RRULE:{event.recurrence}")
        for key, value in event.extra.items():
            if key not in {"DTSTAMP", "DTSTART", "DTEND"}:
                lines.append(f"{key}:{value}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _with_params(name: str, params: dict[str, str], value: str) -> str:
    if not params:
        return f"{name}:{value}"
    rendered = ";".join(f"{key}={val}" for key, val in params.items())
    return f"{name};{rendered}:{value}"


def events_in_range(
    events: list[CalendarEvent], start: datetime, end: datetime
) -> list[CalendarEvent]:
    """筛出与 ``[start, end)`` 有交集的日程，按开始时间排序。"""
    picked = [item for item in events if item.start < end and item.end > start]
    return sorted(picked, key=lambda item: item.start)


def date_range(start: date, end: date) -> tuple[datetime, datetime]:
    """把"日期"扩成"时刻区间"：``[当天 00:00, 结束日次日 00:00)``。"""
    return datetime.combine(start, datetime.min.time()), datetime.combine(
        end + timedelta(days=1), datetime.min.time()
    )
