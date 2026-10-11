"""审计留痕的**读写**接口（审计 L-01）。

## 与原路由的分工

路由只剩"收 Query 参数 → 把结果包成响应"；"数据库没连上怎么说"、
"日期怎么折算成时间范围"这些**判定**留在这里。

⚠️ 写入侧（`record` / `op`）**也在这个服务里**（第 101 批从 runtime 搬进来），
调用点已在第 102 批全部切过去，**runtime 上那两个转发方法已删除** ——
所以"审计"整条链路（读 + 写）现在以本服务为唯一入口
（`services/__init__.py` 里记着这条路是怎么一步步走过来的）。

## 一个容易搞错的差异（原样保留）

清空时**数据库不可用**的返回是 `ok=False`（审计），而用量那边是 `ok=True` ——
听起来像笔误，但两者语义确实不同：审计"没清成"是真没清（有持久化才谈得上清），
用量"没清"时也不该报错（本来就没有流水）。搬迁时逐字保留，没有统一它。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..security.audit import AuditEntry
from ..utils.timefmt import day_range

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from ..server.runtime import AppRuntime


class AuditService:
    """审计留痕的读接口 + 清空。"""

    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime

    @property
    def available(self) -> bool:
        return bool(self._runtime.db_ready)

    async def list(self, **filters: Any) -> dict[str, Any]:
        """查留痕。

        ``date_from`` / ``date_to`` 用**日期**而不是 epoch：界面上的筛选就是两个日期框，
        让前端把"当地时间的 00:00"算成 epoch 只会多一处容易算错的地方
        （结束日不含当天是最常见的那种错，所以 ``day_range`` 统一处理）。

        ⚠️ 这里只接受 `audit_repo.query` 认得的键；多传的参数会被**原样透传**并报错 ——
        这是有意的：路由与仓库的参数一旦对不上，宁可当场炸，也不要静默忽略一个筛选条件。
        """
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
        """清空留痕，返回删除条数。"""
        if not self.available:
            return 0
        return await self._runtime.audit_repo.clear()

    # ------------------------------------------------------------------ #
    # 写入侧（原先长在 AppRuntime 上，第 101 批搬进来）
    # ------------------------------------------------------------------ #
    async def record(self, entry: AuditEntry) -> None:
        """记一条留痕（技能调用与业务操作**共用这张表**）。

        ⚠️ 无数据库时直接跳过：留痕是锦上添花，内存模式下根本没有表可写 ——
        不该逼每个调用方自己去判数据库可用性。
        """
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
        """记一次**实体操作**（哪个搭子在什么时候对什么做了什么）。

        与 ``record`` 的分工：那个记技能/工具调用（带权限级别、参数、耗时），
        这个记"搭子/群/会话/任务被创建、修改、删除、开始、中断"这类业务动作。
        两类进同一张表 —— 用户要按时间顺序看它们（"任务失败前他先删了个会话"
        这种前后关系，分两张表就看不出来了）。

        **绝不往上抛**：留痕失败不该让用户的操作失败。但要留一行日志，
        否则"什么都没记下来"会一直没人发现。
        """
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
        except Exception as exc:  # noqa: BLE001 - 见 docstring
            logger.warning("操作留痕失败 kind=%s action=%s: %s", kind, action, exc)
