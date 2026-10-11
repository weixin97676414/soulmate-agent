"""审计日志仓储。

对应《智能体框架开发文档》10.5 节：高危操作必须能回答
「谁、何时、做了什么、是否被批准」。参数在**写入前**统一脱敏，
避免密钥或个人信息落进审计表。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..security.audit import AuditEntry
from ..security.redact import redact_obj
from .db import Database

logger = logging.getLogger(__name__)

INSERT_AUDIT = """
INSERT INTO audit_log
    (ts, session_id, skill_name, permission_level, params, status, duration_ms, detail,
     kind, actor_id, action, target)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, entry: AuditEntry) -> None:
        params = (
            json.dumps(redact_obj(entry.params), ensure_ascii=False)
            if entry.params
            else None
        )
        detail = entry.detail
        if detail:
            redacted = redact_obj(detail)
            detail = redacted if isinstance(redacted, str) else str(redacted)

        await self._db.execute(
            INSERT_AUDIT,
            (
                entry.ts,
                entry.session_id,
                entry.skill_name,
                entry.permission_level,
                params,
                entry.status,
                entry.duration_ms,
                detail,
                entry.kind,
                entry.actor_id,
                entry.action,
                entry.target,
            ),
        )

    async def query(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        session_id: str | None = None,
        skill_name: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        actor_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[dict[str, Any]]:
        """按条件查留痕。

        ``since`` / ``until`` 是 epoch 秒（含端点）。时间范围是**必须能筛的**：
        用户问的是"九点半那会儿出了什么事"，只能翻列表的话，一次失败就得从头翻到尾。
        """
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if skill_name:
            clauses.append("skill_name = ?")
            params.append(skill_name)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([max(1, min(limit, 500)), max(0, offset)])
        rows = await self._db.fetch_all(
            f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            params,
        )
        for row in rows:
            raw = row.pop("params", None)
            if raw:
                try:
                    row["params"] = json.loads(raw)
                except json.JSONDecodeError:
                    row["params"] = {"_raw": raw}
        return rows

    async def stats(self) -> dict[str, Any]:
        total = await self._db.fetch_one("SELECT COUNT(*) AS n FROM audit_log")
        by_status = await self._db.fetch_all(
            "SELECT status, COUNT(*) AS n FROM audit_log GROUP BY status"
        )
        # 实体操作的 skill_name 是空串（见 SCHEMA_V10）：它们不是技能调用，
        # 混进「最常调用的技能」榜里会让那张榜失去意义
        by_skill = await self._db.fetch_all(
            """
            SELECT skill_name, COUNT(*) AS n
            FROM audit_log
            WHERE skill_name != ''
            GROUP BY skill_name
            ORDER BY n DESC
            LIMIT 10
            """
        )
        by_kind = await self._db.fetch_all(
            "SELECT kind, COUNT(*) AS n FROM audit_log GROUP BY kind"
        )
        return {
            "total": int(total["n"]) if total else 0,
            "by_status": {row["status"]: int(row["n"]) for row in by_status},
            "by_kind": {row["kind"]: int(row["n"]) for row in by_kind},
            "top_skills": [
                {"skill_name": row["skill_name"], "count": int(row["n"])} for row in by_skill
            ],
        }

    async def purge_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM audit_log WHERE ts < ?", (cutoff,)
        )
        count = int(row["n"]) if row else 0
        if count:
            await self._db.execute("DELETE FROM audit_log WHERE ts < ?", (cutoff,))
            logger.info("已清理 %s 条过期审计记录（保留 %s 天）", count, days)
        return count

    async def clear(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM audit_log")
        count = int(row["n"]) if row else 0
        await self._db.execute("DELETE FROM audit_log")
        return count
