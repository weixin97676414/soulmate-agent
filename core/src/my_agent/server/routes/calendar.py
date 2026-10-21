









from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...calendar.service import CalDavBackend, CalendarError
from ...config.schemas import CalendarSettings
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"], prefix="/v1/calendar")


class CalendarTestRequest(BaseModel):






    caldav_url: str | None = Field(None, description="留空用当前设置里的地址")
    caldav_username: str | None = Field(None, description="留空用当前设置里的账号")
    caldav_password: str | None = Field(None, description="留空用当前设置里的密码")


@router.post("/test")
async def test_calendar(payload: CalendarTestRequest, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings.calendar
    candidate = CalendarSettings(
        mode="caldav",
        caldav_url=(payload.caldav_url or current.caldav_url).strip(),
        caldav_username=(payload.caldav_username or current.caldav_username).strip(),
        
        caldav_password=payload.caldav_password or current.caldav_password,
    )

    if not candidate.caldav_url:
        raise HTTPException(status_code=400, detail="请先填写 CalDAV 地址。")

    try:
        now_start, now_end = _window()
        events = await CalDavBackend(candidate).list_events(now_start, now_end)
    except CalendarError as exc:
        
        
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return {
        "ok": True,
        "upcoming": len(events),
        "sample": [item.to_dict() for item in events[:3]],
        "message": f"连接成功，接下来 30 天里有 {len(events)} 条日程。",
    }


def _window() -> tuple[datetime, datetime]:





    now = datetime.now()
    return now, now + timedelta(days=30)
