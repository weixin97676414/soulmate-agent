


















from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..security.audit import AuditEntry
from ..utils.timefmt import day_range

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  
    from ..server.runtime import AppRuntime


class AuditService:


    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime

    @property
    def available(self) -> bool:
        return bool(self._runtime.db_ready)

    async def list(self, **filters: Any) -> dict[str, Any]:









        if not self.available:
            return {"entries": [], "available": False, "reason": "当前为内存模式，未启用审计持久化"}
        since, until = day_range(filters.pop("date_from", None), filters.pop("date_to", None))
        entries = await self._runtime.audit_repo.query(since=since, until=until, **filters)
        return {"entries": entries, "available": True}

    async def stats(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "total": 0, "by_status": {}, "top_skills": []}
        return {"available": True, **await self._runtime.audit_repo.stats()}

    async def clear(self) -> int:

        if not self.available:
            return 0
        return await self._runtime.audit_repo.clear()

    
    
    
    async def record(self, entry: AuditEntry) -> None:





        if not self.available:
            logger.debug("审计跳过（无数据库）: %s %s", entry.skill_name, entry.status)
            return
        await self._runtime.audit_repo.record(entry)

    async def op(
        self,
        *,
        kind: str,
        action: str,
        actor_id: str | None = None,
        target: str = "",
        session_id: str | None = None,
        detail: str = "",
        status: str = "ok",
    ) -> None:










        try:
            await self.record(
                AuditEntry(
                    skill_name="",
                    status=status,
                    kind=kind,
                    actor_id=actor_id,
                    action=action,
                    target=target,
                    session_id=session_id,
                    detail=detail or None,
                )
            )
        except Exception as exc:  
            logger.warning("操作留痕失败 kind=%s action=%s: %s", kind, action, exc)
