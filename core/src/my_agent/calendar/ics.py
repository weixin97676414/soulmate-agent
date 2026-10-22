






















from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any



_FOLD_BYTES = 75

_DT_FORMATS = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M")
_ESC = {"\\": "\\\\", ";": "\\;", ",": "\\,", "\n": "\\n", "\r": ""}


@dataclass
class CalendarEvent:


    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str = ""
    description: str = ""
    all_day: bool = False
    
    recurrence: str = ""
    
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:

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




















    patch = {key: value for key, value in changes.items() if value is not None}
    start = patch.get("start", event.start)
    if "end" in patch:
        end = patch["end"]
    elif "start" in patch:
        
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
            
            moment = moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)
        return moment, False
    raise ValueError(f"无法识别的时间格式：{value}")


def _split_line(line: str) -> tuple[str, dict[str, str], str]:

    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for item in parts[1:]:
        key, _, raw = item.partition("=")
        params[key.upper()] = raw.strip('"')
    return name, params, value


def _unfold(text: str) -> list[str]:

    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_events(text: str) -> list[CalendarEvent]:

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
            
            current_extra[name] = value

    return events


def _build_event(fields: dict[str, object], extra: dict[str, str]) -> CalendarEvent:
    start = fields.get("start")
    if not isinstance(start, datetime):
        raise ValueError("VEVENT 缺少 DTSTART")
    end = fields.get("end")
    if not isinstance(end, datetime):
        
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





def _escape(value: str) -> str:
    out = []
    for char in value or "":
        out.append(_ESC.get(char, char))
    return "".join(out)


def _fold(line: str) -> str:






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
            limit = _FOLD_BYTES - 1  
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

    picked = [item for item in events if item.start < end and item.end > start]
    return sorted(picked, key=lambda item: item.start)


def date_range(start: date, end: date) -> tuple[datetime, datetime]:

    return datetime.combine(start, datetime.min.time()), datetime.combine(
        end + timedelta(days=1), datetime.min.time()
    )
