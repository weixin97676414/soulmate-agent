"""群里的「对话」—— 一个群可以有多条互不相干的消息流。

与单聊的 `SessionRepository` 是**同构**的：`group_threads` 之于 `group_events`，
正如 `sessions` 之于 `messages`。唯一的区别是归属键 —— 这里是 `group_id`，
单聊是 `assistant_id`。所以那边验证过的形状（一张表存元信息、另一张表按它分组
存内容）直接搬过来用，不需要另发明一套。

为什么必须单独一张表，而不是靠 `SELECT DISTINCT thread_id` 从事件表派生：

- **标题**：列表里要显示"这条对话聊的是什么"，而事件全是模型吐出来的碎片，
  派生它得再去捞首条 `topic` 事件；
- **空对话**：刚点「开启新对话」还没说话时，事件表里**零行** —— 派生不出来，
  用户会看到自己刚建的对话凭空消失。

## ⚠️ 遗留数据的「认领」（adopt_legacy）

v13 之前的群事件没有对话维度，迁移时 `thread_id` 全被灌成空串
（见 `group_events.LEGACY_THREAD_ID`）。`list_threads` 会在返回前把这种群
**认领一次**：建一条对话，再把那些事件改挂过去。

为什么不"读的时候兜底空串"就好：那样空串会永远是个特殊值，每条读路径都得
记得兼容（`clear` / `discuss` / 前端列表……），漏一处就是"记录凭空少了"。
认领一次之后系统里就只剩普通对话，没有特殊值可漏。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from .db import Database
from .group_events import GroupEventRepository

#: 认领出来的那条对话叫什么。
#:
#: 不叫"对话 1"：它是**升级前所有历史**的容身处，用户看到"对话记录"能立刻
#: 明白"我以前的记录都在这儿"，而"对话 1"只会让他去找不存在的对话 0。
LEGACY_TITLE = "对话记录"

#: 新建对话的默认名（与单聊 `sessions` 的默认标题一致）。
DEFAULT_TITLE = "新对话"


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GroupThreadRepository:
    """群对话的建 / 列 / 改 / 删。"""

    def __init__(self, db: Database, events: GroupEventRepository) -> None:
        self._db = db
        self._events = events

    async def list_threads(self, group_id: str) -> list[dict[str, Any]]:
        """列出该群的全部对话，最近有动静的排前面。

        ⚠️ 返回**之前**先认领遗留数据：调用方（选群、刷新列表）拿到的一定是
        "历史已经归好位"的状态，不需要自己去想空串的事。
        """
        await self._adopt_legacy(group_id)
        rows = await self._db.fetch_all(
            """
            SELECT id, group_id, title, created_at, updated_at
            FROM group_threads WHERE group_id = ?
            ORDER BY updated_at DESC
            """,
            (group_id,),
        )
        return [dict(row) for row in rows]

    async def create(self, group_id: str, title: str | None = None) -> dict[str, Any]:
        """新建一条空对话并返回它。

        id 用 12 位 uuid hex，与单聊 `SessionManager.create` 同一个做法 ——
        不同群、不同对话之间天然不冲突，不需要任何协调。
        """
        thread_id = uuid.uuid4().hex[:12]
        now = _now()
        await self._db.insert(
            """
            INSERT INTO group_threads (id, group_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, group_id, (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE, now, now),
        )
        return {
            "id": thread_id,
            "group_id": group_id,
            "title": (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE,
            "created_at": now,
            "updated_at": now,
        }

    async def get(self, group_id: str, thread_id: str) -> dict[str, Any] | None:
        """取一条对话；**必须同时匹配群**，否则 A 群能拿 B 群的 id 去读。"""
        row = await self._db.fetch_one(
            """
            SELECT id, group_id, title, created_at, updated_at
            FROM group_threads WHERE id = ? AND group_id = ?
            """,
            (thread_id, group_id),
        )
        return dict(row) if row else None

    async def rename(self, group_id: str, thread_id: str, title: str) -> bool:
        """改名。空标题会被拒（列表里出现一条没名字的对话是无法解释的）。"""
        clean = title.strip()
        if not clean:
            return False
        affected = await self._db.execute_affected(
            "UPDATE group_threads SET title = ? WHERE id = ? AND group_id = ?",
            (clean, thread_id, group_id),
        )
        return affected > 0

    async def touch(self, group_id: str, thread_id: str, occurred_at: str | None = None) -> None:
        """把 `updated_at` 推到现在。

        在**一轮讨论开始时**调一次即可（不必每条事件都调）：它的唯一用途是
        列表排序与"最近聊过"的显示，粒度到"这一轮"就够了。
        """
        await self._db.execute(
            "UPDATE group_threads SET updated_at = ? WHERE id = ? AND group_id = ?",
            (occurred_at or _now(), thread_id, group_id),
        )

    async def delete(self, group_id: str, thread_id: str) -> bool:
        """删一条对话，**连带删掉它的事件**。

        事件不删的话它们会永远留在库里，且因为对话表里已经没有对应行而
        再也无法从界面到达 —— 属于纯泄漏。
        """
        affected = await self._db.execute_affected(
            "DELETE FROM group_threads WHERE id = ? AND group_id = ?",
            (thread_id, group_id),
        )
        if affected == 0:
            return False
        await self._events.clear(group_id, thread_id)
        return True

    async def delete_group(self, group_id: str) -> None:
        """删群时连带清掉它的对话。事件由 `GroupEventRepository.delete_group` 清。"""
        await self._db.execute_affected(
            "DELETE FROM group_threads WHERE group_id = ?", (group_id,)
        )

    # ------------------------------------------------------------------ #
    # 遗留数据
    # ------------------------------------------------------------------ #
    async def _adopt_legacy(self, group_id: str) -> None:
        """把该群尚未认领的历史事件收进一条对话里（每个群只做一次）。

        判据是"**事件表里有空串的行**"，而不是"对话表里有没有行"：用户可能已经
        建过别的对话了，但那批老事件仍然悬在空串上 —— 只按"有没有对话"判断
        会让它们永远认领不掉，表现为"历史记录不见了"。
        """
        span = await self._events.legacy_span(group_id)
        if span is None:
            return
        first, last = span
        thread_id = uuid.uuid4().hex[:12]
        await self._db.insert(
            """
            INSERT INTO group_threads (id, group_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, group_id, LEGACY_TITLE, first or _now(), last or _now()),
        )
        moved = await self._events.adopt_legacy(group_id, thread_id)
        if moved:
            logger.info("群 %s 的历史事件已认领进对话 %s（%s 条）", group_id, thread_id, moved)
