"""日历能力：本地 `.ics` 与 CalDAV 双后端。

只暴露技能与路由需要的三样东西 —— 外面的代码不该直接摸到 ICS 细节。
"""

from .ics import CalendarEvent, build_ics, date_range, events_in_range, parse_events
from .service import CalDavBackend, CalendarError, CalendarService, LocalIcsBackend

__all__ = [
    "CalendarError",
    "CalendarEvent",
    "CalendarService",
    "CalDavBackend",
    "LocalIcsBackend",
    "build_ics",
    "date_range",
    "events_in_range",
    "parse_events",
]
