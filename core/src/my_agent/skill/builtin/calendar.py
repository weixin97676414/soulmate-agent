"""日历技能：查看、新建、修改、删除日程。

## 时间怎么理解

**复用提醒技能那套宽松解析**（`life/reminder.py::parse_when`）：用户会说
「明天早上 8 点」「2026-09-25 14:30」「下周三不行，那就周四」，模型转述时格式
也不统一。让日历自己再写一套时间解析，两边迟早会出现"提醒听得懂、日历听不懂"
这种莫名其妙的差异。

## 默认用哪个日历

由 ``settings.calendar.mode`` 决定（auto = 配了 CalDAV 就用在线，没配就用本地
`.ics` 文件）。技能只认 ``ctx.service("calendar")`` 这个门面，不自己判断 ——
返回值里会带上"这次写进了哪个日历"，避免用户以为写进了手机日历其实只落在本机。

## 已知限制（如实说明，不假装支持）

- **不展开重复日程**：带 RRULE 的日程（每周例会）在列表里只出现一条，
  读取时会带 `repeats` 字段告诉模型"这条是重复的"；
- 非 UTC 时区的日程按本机时间对待。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ...calendar.ics import CalendarEvent, date_range
from ...calendar.service import CalendarError
from ...errors import SkillExecutionError
from ..base import BaseSkill, SkillContext
from ..decorator import skill
from .life.reminder import parse_when

logger = logging.getLogger(__name__)


def _to_skill_error(exc: CalendarError) -> SkillExecutionError:
    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)


def _parse_day(value: str, *, fallback: date) -> date:
    """解析 ``2026-09-25`` 这类日期；解析不了就返回兜底值。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return fallback


class CalendarListParams(BaseModel):
    start_date: str | None = Field(
        None, description="起始日期，如 2026-09-25；留空表示从今天开始"
    )
    end_date: str | None = Field(None, description="结束日期；留空表示按 days_ahead 推算")
    days_ahead: int = Field(
        7, ge=1, le=365, description="从起始日期往后看几天（未给 end_date 时生效）"
    )
    limit: int = Field(30, ge=1, le=200, description="最多返回多少条")


@skill(
    name="calendar_list",
    display_name="查看日程",
    description=(
        "查看某段时间里的日程安排。当用户问「我今天有什么安排」「这周有什么会」"
        "「下周三有安排吗」时使用。返回每条日程的标题、起止时间、地点与备注。"
        "重复日程（每周例会）只出现一条，会标注它是重复的。"
    ),
    params_model=CalendarListParams,
    category="life",
    permission_level="safe",
    tags=["日历", "日程"],
)
class CalendarListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalendarListParams(**params)
        service = ctx.service("calendar")

        today = datetime.now().date()
        start_day = _parse_day(args.start_date or "", fallback=today)
        end_day = (
            _parse_day(args.end_date, fallback=start_day + timedelta(days=args.days_ahead - 1))
            if args.end_date
            else start_day + timedelta(days=args.days_ahead - 1)
        )
        if end_day < start_day:
            end_day = start_day

        start_at, end_at = date_range(start_day, end_day)
        try:
            events = await service.list_events(start_at, end_at)
        except CalendarError as exc:
            raise _to_skill_error(exc) from exc

        items = [event.to_dict() for event in events[: args.limit]]
        return {
            "backend": service.describe_backend(),
            "range": f"{start_day:%Y-%m-%d} ~ {end_day:%Y-%m-%d}",
            "count": len(items),
            "events": items,
            "message": "这段时间没有日程安排。" if not items else None,
        }


class CalendarCreateParams(BaseModel):
    summary: str = Field(..., min_length=1, description="日程标题，例如「和产品过需求」")
    start: str = Field(
        ...,
        description=(
            "开始时间。支持：2026-09-25 14:30 / 明天 8:00 / 今天 18:00 / 09:30（今天，已过则顺延到明天）"
        ),
    )
    end: str | None = Field(None, description="结束时间；留空则按 duration_minutes 推算")
    duration_minutes: int | None = Field(
        None, ge=5, le=24 * 60, description="没给结束时间时持续多久，留空用设置里的默认值"
    )
    location: str = Field("", description="地点，例如「三楼会议室」")
    description: str = Field("", description="备注")
    all_day: bool = Field(False, description="是否全天日程")


@skill(
    name="calendar_create",
    display_name="新建日程",
    description=(
        "在日历里新建一条日程。当用户说「明天下午三点记个会」「周五上午留出写周报的时间」"
        "「下周一提醒我出差」时使用。开始时间支持宽松写法（明天 8:00 / 2026-09-25 14:30），"
        "没给结束时间会按默认时长排。"
    ),
    params_model=CalendarCreateParams,
    category="life",
    permission_level="confirm",
    tags=["日历", "日程"],
)
class CalendarCreateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalendarCreateParams(**params)
        service = ctx.service("calendar")

        start_at = parse_when(args.start)
        if args.all_day:
            start_at = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
            end_at = start_at + timedelta(days=1)
        elif args.end:
            end_at = parse_when(args.end)
        else:
            minutes = args.duration_minutes or int(service.default_duration.total_seconds() // 60)
            end_at = start_at + timedelta(minutes=minutes)

        if end_at <= start_at:
            raise SkillExecutionError("结束时间必须晚于开始时间。")

        event = CalendarEvent(
            uid=uuid.uuid4().hex,
            summary=args.summary.strip(),
            start=start_at,
            end=end_at,
            location=args.location.strip(),
            description=args.description.strip(),
            all_day=args.all_day,
        )
        try:
            created = await service.create_event(event)
        except CalendarError as exc:
            raise _to_skill_error(exc) from exc

        payload = created.to_dict()
        payload["backend"] = service.describe_backend()
        payload["message"] = f"已加入日程：{payload['text']}"
        return payload


class CalendarUpdateParams(BaseModel):
    uid: str = Field(..., description="要修改的日程 id（先用 calendar_list 查）")
    summary: str | None = Field(None, description="新的标题")
    start: str | None = Field(None, description="新的开始时间（支持宽松写法）")
    end: str | None = Field(None, description="新的结束时间")
    location: str | None = Field(None, description="新的地点")
    description: str | None = Field(None, description="新的备注")


@skill(
    name="calendar_update",
    display_name="修改日程",
    description=(
        "修改已有日程的时间、标题、地点或备注；只改传进来的字段。"
        "**只给 start 而不给 end 时，结束时间会按原时长自动顺延** —— 例如把"
        "10:00–10:30 的会改到 15:00，结果就是 15:00–15:30，不需要你再补 end。"
        "只有想**改变时长**时才显式给 end。"
        "当用户说「那个会改到三点」「会议地点换到 5 楼」时使用。"
        "需要先用 calendar_list 拿到日程 id（uid）。"
    ),
    params_model=CalendarUpdateParams,
    category="life",
    permission_level="confirm",
    tags=["日历", "日程"],
)
class CalendarUpdateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalendarUpdateParams(**params)
        service = ctx.service("calendar")

        changes: dict[str, Any] = {}
        if args.summary is not None:
            changes["summary"] = args.summary.strip()
        if args.start is not None:
            changes["start"] = parse_when(args.start)
        if args.end is not None:
            changes["end"] = parse_when(args.end)
        if args.location is not None:
            changes["location"] = args.location.strip()
        if args.description is not None:
            changes["description"] = args.description.strip()
        if not changes:
            raise SkillExecutionError("没有要修改的内容：请至少给一个字段。")

        try:
            updated = await service.update_event(args.uid, changes)
        except CalendarError as exc:
            raise _to_skill_error(exc) from exc

        payload = updated.to_dict()
        payload["backend"] = service.describe_backend()
        payload["changed"] = sorted(changes)
        payload["message"] = f"已更新日程：{payload['text']}"
        return payload


class CalendarDeleteParams(BaseModel):
    uid: str = Field(..., description="要删除的日程 id（先用 calendar_list 查）")


@skill(
    name="calendar_delete",
    display_name="删除日程",
    description=(
        "删除一条日程。当用户说「那个会取消了」「把周五的安排删掉」时使用。"
        "删除前请复述日程标题与时间，避免删错。"
    ),
    params_model=CalendarDeleteParams,
    category="life",
    permission_level="confirm",
    tags=["日历", "日程"],
)
class CalendarDeleteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalendarDeleteParams(**params)
        service = ctx.service("calendar")
        try:
            removed = await service.delete_event(args.uid)
        except CalendarError as exc:
            raise _to_skill_error(exc) from exc

        if not removed:
            raise SkillExecutionError(
                f"没有找到日程 {args.uid}，它可能已经被删掉了。可用 calendar_list 重新确认。"
            )
        return {
            "uid": args.uid,
            "backend": service.describe_backend(),
            "message": "日程已删除。",
        }
