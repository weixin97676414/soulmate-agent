"""审计日志查询接口（设置中心「安全」页签使用）。

对应开发文档 10.5 节：高危操作必须可追溯。参数在写入时已脱敏，这里直接返回即可。

⚠️ 这一层现在只剩"收 Query 参数 → 交给 `runtime.audit` → 返回"（审计 L-01）：
"数据库没连上怎么说"、"日期怎么折算成时间范围"都在 `services/audit.py` 里。
那里还有一条**看起来像笔误、其实不是**的差异（清空时不可用返回 `ok=False`，
而用量那边是 `ok=True`）—— 动它之前先读那段说明。
"""

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
    """查留痕（筛选参数的口径见 `services/audit.py::AuditService.list`）。"""
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
        # ⚠️ 这里是 `ok=False`（用量那边是 `ok=True`）：审计"没清成"是真没清 ——
        # 没有持久化就谈不上清空。逐字保留原行为，理由见 services/audit.py。
        return {"ok": False, "removed": 0}
    return {"ok": True, "removed": await service.clear()}
