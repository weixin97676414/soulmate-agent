"""日历接口：目前只有「测试连接」。

日历本身由技能读写（`calendar_list/create/update/delete`），这里只补一件事：
设置页在**保存之前**要能验证"地址、账号、密码"填对没有 —— 没有这个入口，
用户只能填完保存、再去对话里让搭子读一次日程，才知道自己配错了。

（配置项本身随 settings.json 走 `GET/PUT /v1/settings`，不另开一套接口：
日历参数是配置的一部分，两套接口迟早会出现"改了没生效"的不一致。）
"""

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
    """测试连接的入参。

    三个字段都可选：不传就用当前设置里的值。这样界面上既能"改完直接测"，
    也能"不改配置只测现有配置能不能用"。
    """

    caldav_url: str | None = Field(None, description="留空用当前设置里的地址")
    caldav_username: str | None = Field(None, description="留空用当前设置里的账号")
    caldav_password: str | None = Field(None, description="留空用当前设置里的密码")


@router.post("/test")
async def test_calendar(payload: CalendarTestRequest, request: Request) -> dict[str, Any]:
    """按给定（或用当前）的 CalDAV 配置试一次只读请求。"""
    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings.calendar
    candidate = CalendarSettings(
        mode="caldav",
        caldav_url=(payload.caldav_url or current.caldav_url).strip(),
        caldav_username=(payload.caldav_username or current.caldav_username).strip(),
        # 密码留空 = 用已经存在内存里的那份（密码永远不从界面回显）
        caldav_password=payload.caldav_password or current.caldav_password,
    )

    if not candidate.caldav_url:
        raise HTTPException(status_code=400, detail="请先填写 CalDAV 地址。")

    try:
        now_start, now_end = _window()
        events = await CalDavBackend(candidate).list_events(now_start, now_end)
    except CalendarError as exc:
        # 400 而不是 500：这是"填的参数不对"，用户改一下就好，
        # 报 500 会让人以为服务坏了
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return {
        "ok": True,
        "upcoming": len(events),
        "sample": [item.to_dict() for item in events[:3]],
        "message": f"连接成功，接下来 30 天里有 {len(events)} 条日程。",
    }


def _window() -> tuple[datetime, datetime]:
    """测试连接要看的时间窗：往后 30 天。

    取"未来"而不是"过去"：用户想确认的是"我的日程读得到吗"，
    而他日历里未来一定比过去更有内容（过去的会开完就没人在意了）。
    """
    now = datetime.now()
    return now, now + timedelta(days=30)
