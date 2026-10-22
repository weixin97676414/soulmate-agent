











from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ..deps import get_runtime

router = APIRouter(tags=["usage"], prefix="/v1/usage")


@router.get("/summary")
async def summary(request: Request, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return await get_runtime(request).usage.summary(days)


@router.get("/session/{session_id}")
async def session_usage(session_id: str, request: Request) -> dict[str, Any]:

    return await get_runtime(request).usage.session(session_id)


@router.delete("")
async def clear_usage(request: Request) -> dict[str, Any]:

    return {"ok": True, "removed": await get_runtime(request).usage.clear()}
