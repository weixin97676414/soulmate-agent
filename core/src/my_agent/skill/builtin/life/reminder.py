






from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill


_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日%H:%M",
)

_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H点%M分", "%H点%M", "%H点")

_DAY_PREFIXES = (
    ("大后天", 3),
    ("后天", 2),
    ("明天", 1),
    ("明日", 1),
    ("今天", 0),
    ("今日", 0),
)


def parse_when(text: str, *, now: datetime | None = None) -> datetime:

    moment = now or datetime.now()
    raw = (text or "").strip()
    if not raw:
        raise SkillExecutionError("请提供提醒时间。")

    
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    
    day_offset = 0
    
    
    explicit_day = False
    remainder = raw
    for prefix, offset in _DAY_PREFIXES:
        if remainder.startswith(prefix):
            day_offset = offset
            explicit_day = True
            remainder = remainder[len(prefix) :].strip()
            break

    for fmt in _TIME_FORMATS:
        try:
            parsed = datetime.strptime(remainder, fmt)
        except ValueError:
            continue
        base = (moment + timedelta(days=day_offset)).replace(
            hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
        )
        if base <= moment:
            
            
            
            
            
            if explicit_day:
                raise SkillExecutionError(
                    f"「{text}」对应的时间 {base:%Y-%m-%d %H:%M} 已经过去了。"
                    "如果是指明天，请说「明天 …」；如果想现在就被提醒，请直接说内容。"
                )
            base += timedelta(days=1)
        return base

    
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            parsed_date = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        base = parsed_date.replace(hour=9, minute=0, second=0, microsecond=0)
        if base <= moment:
            base = moment + timedelta(minutes=5)
        return base

    raise SkillExecutionError(
        f"无法识别时间「{text}」。请使用以下任一格式："
        "2026-09-20 14:30 / 明天 8:00 / 09:30 / 2026-09-20"
    )


class ReminderCreateParams(BaseModel):
    content: str = Field(..., description="提醒内容，例如「交周报」「给张总打电话」")
    remind_at: str | None = Field(
        None,
        description=(
            "提醒时间。支持：2026-09-20 14:30 / 明天 8:00 / 今天 18:00 / 09:30。"
            "与 in_minutes 二选一"
        ),
    )
    in_minutes: int | None = Field(
        None, gt=0, le=60 * 24 * 30, description="多少分钟后提醒（相对时间），与 remind_at 二选一"
    )
    advance_minutes: int = Field(
        0, ge=0, le=1440, description="提前多少分钟提醒，例如「提前 5 分钟」就填 5"
    )


@skill(
    name="reminder_create",
    display_name="创建提醒",
    description=(
        "创建一个定时提醒，到点后客户端会弹出通知。"
        "当用户说「明天 9 点提醒我交周报」「10 分钟后提醒我看火」「提前 5 分钟提醒我开会」时使用。"
        "绝对时间用 remind_at，相对时间用 in_minutes。创建后返回提醒时间，可向用户复述确认。"
    ),
    params_model=ReminderCreateParams,
    category="life",
    permission_level="safe",
    tags=["提醒", "日程"],
)
class ReminderCreateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReminderCreateParams(**params)
        repository = ctx.service("reminders")

        if not args.remind_at and not args.in_minutes:
            raise SkillExecutionError("请提供 remind_at（具体时间）或 in_minutes（多少分钟后）。")
        if args.remind_at and args.in_minutes:
            raise SkillExecutionError("remind_at 与 in_minutes 只能提供一个。")

        if args.in_minutes:
            base = datetime.now() + timedelta(minutes=args.in_minutes)
        else:
            base = parse_when(args.remind_at or "")

        base_ts = base.timestamp()
        remind_ts = base_ts - args.advance_minutes * 60
        now = time.time()
        if remind_ts <= now:
            
            remind_ts = now + 5

        record = await repository.create(
            content=args.content.strip(),
            remind_at=remind_ts,
            base_at=base_ts,
            advance_min=args.advance_minutes,
        )

        payload = record.to_dict()
        payload["summary"] = (
            f"已设置提醒：「{record.content}」"
            + (f"（提前 {record.advance_min} 分钟）" if record.advance_min else "")
            + f"，提醒时间 {payload['remind_at_text']}"
        )
        return payload


class ReminderListParams(BaseModel):
    status: Literal["pending", "fired", "cancelled", "all"] = Field(
        "pending", description="按状态筛选：pending 待触发 / fired 已触发 / cancelled 已取消 / all 全部"
    )
    limit: int = Field(20, ge=1, le=100, description="最多返回多少条")


@skill(
    name="reminder_list",
    display_name="查看提醒",
    description=(
        "列出已创建的提醒。当用户问「我有哪些提醒」「明天有什么安排」时使用。"
        "默认只返回待触发的提醒。"
    ),
    params_model=ReminderListParams,
    category="life",
    permission_level="safe",
    tags=["提醒", "日程"],
)
class ReminderListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReminderListParams(**params)
        repository = ctx.service("reminders")

        status = None if args.status == "all" else args.status
        records = await repository.list(status=status, limit=args.limit)
        return {
            "status": args.status,
            "count": len(records),
            "reminders": [record.to_dict() for record in records],
            "message": "暂无提醒。" if not records else None,
        }


class ReminderCancelParams(BaseModel):
    reminder_id: int = Field(..., description="要取消的提醒 id（可先用 reminder_list 查出）")


@skill(
    name="reminder_cancel",
    display_name="取消提醒",
    description=(
        "取消一个尚未触发的提醒。当用户说「取消那个提醒」「不用提醒我了」时使用。"
        "需要先用 reminder_list 拿到提醒 id。"
    ),
    params_model=ReminderCancelParams,
    category="life",
    permission_level="safe",
    tags=["提醒", "日程"],
)
class ReminderCancelSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReminderCancelParams(**params)
        repository = ctx.service("reminders")

        cancelled = await repository.cancel(args.reminder_id)
        if not cancelled:
            raise SkillExecutionError(
                f"提醒 {args.reminder_id} 不存在或不是待触发状态，无法取消。"
                f"可用 reminder_list 查看当前提醒。"
            )
        return {"id": args.reminder_id, "status": "cancelled", "message": "提醒已取消。"}
