

















from __future__ import annotations

from datetime import UTC, datetime

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def format_message_time(ts: float) -> str:

    local = datetime.fromtimestamp(ts)
    return f"{local:%m-%d %H:%M}"


def format_now(ts: float) -> str:

    local = datetime.fromtimestamp(ts)
    return f"{local:%Y-%m-%d %H:%M}（{_WEEKDAYS[local.weekday()]}）"


def format_day(ts: float) -> str:

    return f"{datetime.fromtimestamp(ts):%Y-%m-%d}"


def format_stamp(ts: float | None) -> str:





    return f"[{format_message_time(ts)}] " if ts is not None else ""


def now_iso() -> str:





    return datetime.now(UTC).isoformat()


def parse_iso(text: str | None) -> float | None:

    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def parse_day(text: str | None) -> float | None:





    raw = (text or "").strip().replace("/", "-")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").timestamp()
    except ValueError:
        return None


def day_range(start: str | None, end: str | None) -> tuple[float | None, float | None]:






    since = parse_day(start)
    until = parse_day(end)
    return since, (until + 86_399.999 if until is not None else None)
