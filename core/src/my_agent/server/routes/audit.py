









from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ..deps import get_runtime

router = APIRouter(tags=["audit"], prefix="/v1/audit")


@router.get("")
async def list_audit(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session_id: str | None = None,
    skill_name: str | None = None,
    status: str | None = Query(None, description="ok / error / denied / timeout"),
    kind: str | None = Query(
        None, description="skill / assistant / group / session / task / permission"
    ),
    actor_id: str | None = Query(None, description="按搭子筛：它做过什么"),
    date_from: str | None = Query(None, description="起始日期 YYYY-MM-DD（含当天）"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD（含当天）"),
) -> dict[str, Any]:

    return await get_runtime(request).audit.list(
        limit=limit,
        offset=offset,
        session_id=session_id,
        skill_name=skill_name,
        status=status,
        kind=kind,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/stats")
async def audit_stats(request: Request) -> dict[str, Any]:
    return await get_runtime(request).audit.stats()


@router.delete("")
async def clear_audit(request: Request) -> dict[str, Any]:
    service = get_runtime(request).audit
    if not service.available:
        
        
        return {"ok": False, "removed": 0}
    return {"ok": True, "removed": await service.clear()}
