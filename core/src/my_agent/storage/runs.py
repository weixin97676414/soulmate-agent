





















from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .db import Database

logger = logging.getLogger(__name__)

INSERT_RUN = """
INSERT INTO runs (id, kind, ref_id, session_id, status, step, last_action, error,
                  created_at, updated_at)
VALUES (?, ?, ?, ?, 'running', 0, '', '', ?, ?)
"""


@dataclass
class RunRecord:


    id: str
    kind: str  
    ref_id: str = ""  
    session_id: str = ""
    status: str = "running"
    step: int = 0
    last_action: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "ref_id": self.ref_id,
            "session_id": self.session_id,
            "status": self.status,
            "step": self.step,
            "last_action": self.last_action,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RunStore:






    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def ready(self) -> bool:
        return self._db.connected

    async def start(self, *, kind: str, ref_id: str = "", session_id: str = "") -> str:

        if not self.ready:
            return ""
        run_id = uuid.uuid4().hex[:12]
        now = time.time()
        try:
            await self._db.execute(INSERT_RUN, (run_id, kind, ref_id, session_id, now, now))
        except Exception as exc:  
            logger.warning("运行记录写入失败 kind=%s ref=%s: %s", kind, ref_id, exc)
            return ""
        return run_id

    async def attach_session(self, run_id: str, session_id: str) -> None:





        if not self.ready or not run_id or not session_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, time.time(), run_id),
            )
        except Exception as exc:  
            logger.warning("运行记录补会话失败 run=%s: %s", run_id, exc)

    async def progress(self, run_id: str, *, step: int, last_action: str = "") -> None:

        if not self.ready or not run_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET step = ?, last_action = ?, updated_at = ? WHERE id = ?",
                (step, last_action, time.time(), run_id),
            )
        except Exception as exc:  
            logger.warning("运行进度写入失败 run=%s: %s", run_id, exc)

    async def finish(self, run_id: str) -> None:

        if not self.ready or not run_id:
            return
        try:
            await self._db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        except Exception as exc:  
            logger.warning("运行记录清理失败 run=%s: %s", run_id, exc)

    async def interrupt(
        self,
        run_id: str,
        *,
        status: str,
        step: int = 0,
        last_action: str = "",
        error: str = "",
    ) -> None:









        if not self.ready or not run_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET status = ?, step = ?, last_action = ?, error = ?, "
                "updated_at = ? WHERE id = ?",
                (status, step, last_action, error, time.time(), run_id),
            )
        except Exception as exc:  
            logger.warning("运行记录落盘失败 run=%s: %s", run_id, exc)

    async def get(self, run_id: str) -> RunRecord | None:
        if not self.ready:
            return None
        row = await self._db.fetch_one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _row_to_record(row) if row else None

    async def list_pending(self, *, kind: str | None = None) -> list[RunRecord]:

        if not self.ready:
            return []
        if kind:
            rows = await self._db.fetch_all(
                "SELECT * FROM runs WHERE status != 'running' AND kind = ? "
                "ORDER BY updated_at DESC",
                (kind,),
            )
        else:
            rows = await self._db.fetch_all(
                "SELECT * FROM runs WHERE status != 'running' ORDER BY updated_at DESC"
            )
        return [_row_to_record(row) for row in rows]

    async def clear_running(self) -> int:







        if not self.ready:
            return 0
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM runs WHERE status = 'running'")
        removed = int(row["n"]) if row else 0
        if removed:
            await self._db.execute("DELETE FROM runs WHERE status = 'running'")
            logger.warning("清理了 %s 条中断残留的运行记录（上次进程未正常退出）", removed)
        return removed

    async def purge_older_than(self, days: int) -> int:





        if not self.ready or days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM runs WHERE updated_at < ?", (cutoff,)
        )
        removed = int(row["n"]) if row else 0
        if removed:
            await self._db.execute("DELETE FROM runs WHERE updated_at < ?", (cutoff,))
            logger.info("已清理 %s 条过期待续跑记录", removed)
        return removed


def _row_to_record(row: dict[str, Any]) -> RunRecord:
    return RunRecord(
        id=str(row["id"]),
        kind=str(row["kind"]),
        ref_id=str(row.get("ref_id") or ""),
        session_id=str(row.get("session_id") or ""),
        status=str(row.get("status") or "running"),
        step=int(row.get("step") or 0),
        last_action=str(row.get("last_action") or ""),
        error=str(row.get("error") or ""),
        created_at=float(row.get("created_at") or 0),
        updated_at=float(row.get("updated_at") or 0),
    )
