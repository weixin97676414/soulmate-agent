"""生活数据接口：提醒与记账。

供界面直接查看/管理，不必绕道让模型调用技能。技能写进去的数据
在这里能看到，两边共用同一套仓储。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["life"])


def _require_db(runtime: AppRuntime) -> None:
    if not runtime.db_ready:
        raise HTTPException(
            status_code=503,
            detail="当前为内存模式（数据库不可用），提醒与记账功能不可用。",
        )


# --------------------------------------------------------------------------- #
# 提醒
# --------------------------------------------------------------------------- #
@router.get("/v1/reminders")
async def list_reminders(
    request: Request,
    status: str | None = Query(None, description="pending / fired / cancelled，留空返回全部"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_db(runtime)
    records = await runtime.reminder_repo.list(status=status, limit=limit)
    return {
        "reminders": [record.to_dict() for record in records],
        "pending": len(await runtime.reminder_repo.upcoming(limit=200)),
    }


@router.delete("/v1/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_db(runtime)
    removed = await runtime.reminder_repo.delete(reminder_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"提醒 {reminder_id} 不存在")
    return {"ok": True}


@router.post("/v1/reminders/check")
async def check_reminders(request: Request) -> dict[str, Any]:
    """立即检查一次到点提醒，用于调试与手动触发。"""
    runtime: AppRuntime = get_runtime(request)
    _require_db(runtime)
    fired = await runtime.reminder_scheduler.check_once()
    return {"ok": True, "fired": fired}


# --------------------------------------------------------------------------- #
# 记账
# --------------------------------------------------------------------------- #
@router.get("/v1/expenses")
async def list_expenses(
    request: Request,
    period: str = Query("month", description="today / week / month / year / all …"),
    category: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_db(runtime)
    try:
        summary = await runtime.expense_repo.summary(period=period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    records = await runtime.expense_repo.list(period=period, category=category, limit=limit)
    return {
        "summary": summary,
        "expenses": [record.to_dict() for record in records],
        "categories": await runtime.expense_repo.categories(),
    }


@router.delete("/v1/expenses/{expense_id}")
async def delete_expense(expense_id: int, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_db(runtime)
    removed = await runtime.expense_repo.delete(expense_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"记账记录 {expense_id} 不存在")
    return {"ok": True}
