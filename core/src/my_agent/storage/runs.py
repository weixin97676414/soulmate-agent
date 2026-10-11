"""**未完成运行**的进度（断点续跑）。

## 这张表只存"还没跑完的"

用户的要求是：「任务跑到一半某个搭子挂了、或用户手动叫停，要能保存进度、下次接着跑，
别一次失败全白干」。落到这里的生命周期很简单：

- **开始**一次运行 → 插一行 ``running``；
- **正常跑完** → 把这一行**删掉** —— 不需要续跑，留着只会让界面上的「继续」永远挂着；
- **失败 / 被叫停** → 更新成 ``failed`` / ``cancelled``，并留下"跑到第几步、最后做的是
  什么、接着哪个会话"。

于是这张表的语义就是"**待续跑的运行**"，不会随日常使用无限增长。
而"某次执行失败过"这类**历史**归审计（``storage/audit.py``）—— 两件事不要混在一张表里：
一个要能删（续跑完就没意义），一个要留存可查。

## 为什么记 ``session_id``

"接着跑"的实质是**接着那个会话跑**：模型能看到上一次已经做到哪里，于是不重复劳动。
没有会话 id 就只能从头再来一遍 —— 那正是用户说的"一次失败全白干"。
"""

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
    """一次未完成运行的进度。"""

    id: str
    kind: str  # task / group / chat
    ref_id: str = ""  # 任务 id / 群 id（chat 用会话 id，留空）
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
    """未完成运行的读写。

    数据库不可用时（纯内存降级模式）所有方法都安全地空转：续跑功能随之不可用，
    但**绝不能让"记不了进度"这件事把一个正在跑的对话搞崩**。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def ready(self) -> bool:
        return self._db.connected

    async def start(self, *, kind: str, ref_id: str = "", session_id: str = "") -> str:
        """开始一次运行，返回 run_id（拿不到就返回空串，调用方据此跳过后续更新）。"""
        if not self.ready:
            return ""
        run_id = uuid.uuid4().hex[:12]
        now = time.time()
        try:
            await self._db.execute(INSERT_RUN, (run_id, kind, ref_id, session_id, now, now))
        except Exception as exc:  # noqa: BLE001 - 记不了进度不该影响正事
            logger.warning("运行记录写入失败 kind=%s ref=%s: %s", kind, ref_id, exc)
            return ""
        return run_id

    async def attach_session(self, run_id: str, session_id: str) -> None:
        """把会话 id 补上。

        定时任务的会话是**执行中**才建出来的（``_execute`` 里 create），所以只能后补；
        而它恰恰是"接着跑"最关键的一个字段。
        """
        if not self.ready or not run_id or not session_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, time.time(), run_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("运行记录补会话失败 run=%s: %s", run_id, exc)

    async def progress(self, run_id: str, *, step: int, last_action: str = "") -> None:
        """记下"跑到哪了"。只在关键节点调用（每个工具/每轮），不是每帧。"""
        if not self.ready or not run_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET step = ?, last_action = ?, updated_at = ? WHERE id = ?",
                (step, last_action, time.time(), run_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("运行进度写入失败 run=%s: %s", run_id, exc)

    async def finish(self, run_id: str) -> None:
        """正常收尾 → 删掉这一行（没有要续跑的东西了）。"""
        if not self.ready or not run_id:
            return
        try:
            await self._db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        except Exception as exc:  # noqa: BLE001
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
        """失败 / 被叫停 / 没做完 → 留成待续跑。

        ``status`` 有三种，它们对用户的含义完全不同（界面据此措辞）：

        - ``failed``：出错了，要去修配置或换个说法；
        - ``incomplete``：没出错但没做完（典型是一次任务的执行步数用尽）——
          还能接着做，别把它显示成"失败"；
        - ``cancelled``：用户自己点停止，或界面断开。
        """
        if not self.ready or not run_id:
            return
        try:
            await self._db.execute(
                "UPDATE runs SET status = ?, step = ?, last_action = ?, error = ?, "
                "updated_at = ? WHERE id = ?",
                (status, step, last_action, error, time.time(), run_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("运行记录落盘失败 run=%s: %s", run_id, exc)

    async def get(self, run_id: str) -> RunRecord | None:
        if not self.ready:
            return None
        row = await self._db.fetch_one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _row_to_record(row) if row else None

    async def list_pending(self, *, kind: str | None = None) -> list[RunRecord]:
        """列出待续跑的运行（界面上的「继续」入口就靠它）。"""
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
        """清掉"显示还在跑、其实进程已经没了"的残留行。

        启动那一刻不可能有运行在跑（进程刚起来），所以 ``running`` 一定属于上一次
        被强杀/断电的进程。留着它们的后果是：任务再也建不出新记录？不 —— 新的会另起一行，
        但这一行会**永远**停在 running（界面上「继续」永远不会出现，而它明明没跑完）。
        删除比标记更诚实：那一次执行没有可续跑的现场（会话都没来得及落盘）。
        """
        if not self.ready:
            return 0
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM runs WHERE status = 'running'")
        removed = int(row["n"]) if row else 0
        if removed:
            await self._db.execute("DELETE FROM runs WHERE status = 'running'")
            logger.warning("清理了 %s 条中断残留的运行记录（上次进程未正常退出）", removed)
        return removed

    async def purge_older_than(self, days: int) -> int:
        """清理太久以前的待续跑记录。

        不做清理的话，一年前那次失败会一直躺在列表里 —— 用户早就忘了它是什么，
        还会以为"这里有东西没跑完"。默认留 30 天，够他回头捡起来。
        """
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
