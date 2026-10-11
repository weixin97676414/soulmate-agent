"""Token 用量与费用流水。

对应《智能体框架开发文档》FR-13 / 4.6 / 16.2。三个设计要点：

1. **按「次」记，不按「条消息」记**。一次用户提问可能触发多轮模型调用
   （每轮工具调用各一次），用量是这些调用的**累计**，不是某条消息的属性。
2. **缓存命中单独一列**。命中价可能只有未命中的 1/10，混在总量里既算不准费用，
   也失去了「验证前缀缓存优化是否生效」的唯一手段。
3. **费用允许为空**。用户没填模型单价时 ``cost`` 存 NULL，界面如实显示
   「未配置价格」，而不是拿一个猜出来的数字糊弄人——用户看到金额就会当真。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..llm.usage import Usage
from .db import Database

logger = logging.getLogger(__name__)

INSERT_USAGE = """
INSERT INTO usage_log
    (session_id, trace_id, model_id, provider, prompt_tokens, completion_tokens,
     cached_tokens, cache_write_tokens, reasoning_tokens, cost, currency,
     duration_ms, iterations, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# 汇总时反复用到的表达式，抽成常量避免各处写法不一致
_SUM_TOKENS = """
    COALESCE(SUM(prompt_tokens), 0)      AS prompt_tokens,
    COALESCE(SUM(completion_tokens), 0)  AS completion_tokens,
    COALESCE(SUM(cached_tokens), 0)      AS cached_tokens,
    COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(SUM(reasoning_tokens), 0)   AS reasoning_tokens,
    COUNT(*)                             AS calls
"""


@dataclass
class UsageRecord:
    """一次对话（可能含多轮模型调用）的用量快照。"""

    session_id: str | None = None
    trace_id: str | None = None
    model_id: str = ""
    provider: str = ""
    usage: Usage = field(default_factory=Usage)
    # 没配价格时为 None，落库也是 NULL，前端据此显示"未配置价格"
    cost: float | None = None
    currency: str = "CNY"
    duration_ms: float | None = None
    iterations: int = 0
    created_at: float = field(default_factory=time.time)


def _hit_rate(cached: int, prompt: int) -> float | None:
    if prompt <= 0:
        return None
    return round(cached / prompt, 4)


def _shape(row: Any) -> dict[str, Any]:
    """把聚合行整理成前端好用的形状（含命中率）。"""
    prompt = int(row["prompt_tokens"] or 0)
    completion = int(row["completion_tokens"] or 0)
    cached = int(row["cached_tokens"] or 0)
    data: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "cache_write_tokens": int(row["cache_write_tokens"] or 0),
        "reasoning_tokens": int(row["reasoning_tokens"] or 0),
        "total_tokens": prompt + completion,
        "calls": int(row["calls"] or 0),
        "cache_hit_rate": _hit_rate(cached, prompt),
    }
    # cost 可能整列为 NULL（用户没配价格）。区分"没配"与"确实是 0 元"，
    # 否则界面会把"未配置价格"显示成"¥0.00"，用户以为免费。
    cost = row["cost"] if "cost" in row.keys() else None
    data["cost"] = round(float(cost), 6) if cost is not None else None
    return data


class UsageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def record(self, entry: UsageRecord) -> None:
        usage = entry.usage
        if usage.is_empty and entry.cost is None:
            # 一点信息都没有就不必留一行（例如模型压根没返回 usage）
            return
        await self._db.execute(
            INSERT_USAGE,
            (
                entry.session_id,
                entry.trace_id,
                entry.model_id,
                entry.provider,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.cached_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
                entry.cost,
                entry.currency,
                entry.duration_ms,
                entry.iterations,
                entry.created_at,
            ),
        )

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    async def totals(self, *, since: float | None = None) -> dict[str, Any]:
        # ⚠️ ``cost`` **刻意不套 COALESCE**（和上面那些 token 求和不一样）。
        #
        # ``SUM`` 在全为 NULL 时返回 NULL，正好等于"用户一个单价都没配"；
        # 套上 ``COALESCE(..., 0)`` 之后它就永远是数字，``_shape`` 里那条
        # NULL 分支变成死代码，界面会把"未配置价格"显示成 **¥0.00** ——
        # 而这个应用明确不希望用户把"不知道"读成"免费"（见 _shape 的注释）。
        where, params = ("WHERE created_at >= ?", (since,)) if since else ("", ())
        row = await self._db.fetch_one(
            f"SELECT {_SUM_TOKENS}, SUM(cost) AS cost FROM usage_log {where}",
            params,
        )
        if row is None:
            return _shape(
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "calls": 0,
                    "cost": None,
                }
            )
        return _shape(row)

    async def by_model(
        self, *, since: float | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        where, params = ("WHERE created_at >= ?", [since]) if since else ("", [])
        params.append(max(1, min(limit, 200)))
        rows = await self._db.fetch_all(
            f"""
            SELECT model_id, {_SUM_TOKENS}, SUM(cost) AS cost
            FROM usage_log {where}
            GROUP BY model_id
            ORDER BY (SUM(prompt_tokens) + SUM(completion_tokens)) DESC
            LIMIT ?
            """,
            params,
        )
        return [{"model_id": row["model_id"] or "（未知）", **_shape(row)} for row in rows]

    async def by_day(self, *, days: int = 30) -> list[dict[str, Any]]:
        """按天汇总。按**本地时区**分日，否则用户看到的"今天"会错位。"""
        cutoff = time.time() - max(1, days) * 86400
        rows = await self._db.fetch_all(
            f"""
            SELECT date(created_at, 'unixepoch', 'localtime') AS day,
                   {_SUM_TOKENS},
                   SUM(cost) AS cost
            FROM usage_log
            WHERE created_at >= ?
            GROUP BY day
            ORDER BY day DESC
            """,
            (cutoff,),
        )
        return [{"day": row["day"], **_shape(row)} for row in rows]

    async def by_session(self, session_id: str) -> dict[str, Any]:
        where, params = "WHERE session_id = ?", (session_id,)
        row = await self._db.fetch_one(
            f"SELECT {_SUM_TOKENS}, SUM(cost) AS cost FROM usage_log {where}",
            params,
        )
        if row is None:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return _shape(row)

    async def today(self) -> dict[str, Any]:
        """今天的用量（本地时区），用于预算提示。"""
        start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        return await self.totals(since=start)

    async def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._db.fetch_all(
            """
            SELECT created_at, session_id, trace_id, model_id,
                   prompt_tokens, completion_tokens, cached_tokens, cost, iterations
            FROM usage_log
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        )
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # 清理
    # ------------------------------------------------------------------ #
    async def purge_older_than(self, days: int) -> int:
        """清理过期流水。

        默认保留期远长于审计（用量要做月度对比），由调用方传入。
        ``days <= 0`` 表示**永久保留**，不清理。
        """
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM usage_log WHERE created_at < ?", (cutoff,)
        )
        count = int(row["n"]) if row else 0
        if count:
            await self._db.execute("DELETE FROM usage_log WHERE created_at < ?", (cutoff,))
            logger.info("已清理 %s 条过期用量记录（保留 %s 天）", count, days)
        return count

    async def clear(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM usage_log")
        count = int(row["n"]) if row else 0
        await self._db.execute("DELETE FROM usage_log")
        return count
