"""群聊记录（按「对话 + 事件」持久化）。

## 为什么存"事件流"而不是"消息列表"

前端渲染群聊本来就是在消费一串 SSE 事件（`topic` / `speaker` / `message` /
`vote` …）。把事件原样存下来，恢复时**重放**一遍就能复用同一套渲染逻辑 ——
不需要为"从数据库读"再写一条并行的构造路径，而两条路径迟早会长歪。

## 为什么 `delta` 不落库

逐字分片一条发言能有上千个，存下来既没意义又会把库撑爆。真正的内容在收尾的
`message` / `summary` 事件里是完整的，重放时天然还原。

## 一条流 = 一个「对话」

`thread_id` 把事件分成多条互不相干的流（产品要求"每个群可能产生
多个对话"），对应单聊里的一个 `session`。它由 `GroupThreadRepository` 建与删，
这里只负责按它归类读写。

⚠️ **所有方法的 `thread_id` 都是必填、没有默认值**，这是刻意的：
传漏了它就会写进下面那个遗留哨兵里，和升级前的历史混成一堆。宁可让调用方多写
一个参数，也不要让"忘了传"表现为"记录跑到别的对话里去了"。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .db import Database

# 单个对话最多回放多少条事件。群聊是"多轮讨论"，一次讨论几千条很正常；
# 但历史无限增长会让进入页面越来越慢，所以读的时候封顶。
MAX_REPLAY_EVENTS = 4000

#: **v13 之前的遗留标记**：那批事件是加列时用 `DEFAULT ''` 灌进来的。
#:
#: 它不是一个正常的对话 id，而是"还没被认领的历史"。`GroupThreadRepository.
#: adopt_legacy` 会把它改写成一个真实 id（每个群各一次），之后这个值就只可能
#: 出现在**尚未打开过**的群里。**新代码任何情况下都不该往它上面写。**
LEGACY_THREAD_ID = ""


class GroupEventRepository:
    """群聊事件的落库与回放（按对话分组）。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, group_id: str, thread_id: str, event: str, data: dict[str, Any]) -> None:
        """向某个对话追加一条事件。

        ``seq`` 在**同一条 SQL 里**由 `MAX(seq)+1` 算出：拆成"先查再插"的话，
        两条事件并发写入会算出同一个 seq（中间隔着 await），排序就乱了。

        编号按 **`thread_id`** 递增而不是按群 —— 每条对话是一条独立的流，
        它内部的顺序只跟自己有关。
        """
        payload = json.dumps(data, ensure_ascii=False)
        await self._db.insert(
            """
            INSERT INTO group_events (group_id, thread_id, seq, event, data, created_at)
            VALUES (
                ?, ?,
                (SELECT COALESCE(MAX(seq), 0) + 1 FROM group_events
                 WHERE group_id = ? AND thread_id = ?),
                ?, ?, ?
            )
            """,
            (
                group_id,
                thread_id,
                group_id,
                thread_id,
                event,
                payload,
                datetime.now(UTC).isoformat(),
            ),
        )

    async def list_events(
        self,
        group_id: str,
        thread_id: str | None,
        limit: int = MAX_REPLAY_EVENTS,
    ) -> list[dict[str, Any]]:
        """按顺序取出该对话最近的事件，用于重放。

        **取最近 limit 条**（再按 seq 升序返回）：直接取最早的那批会让用户
        永远看不到最新一轮讨论。

        ⚠️ ``thread_id`` 为 ``None`` 表示**整个群**（不分对话）—— 历史检索
        （`agent/history.py`）要的正是这个：用户问"我们之前说过什么"时，
        不该因为那句话在另一条对话里就搜不到。其余场景一律传具体 id。
        """
        if thread_id is None:
            rows = await self._db.fetch_all(
                """
                SELECT seq, event, data, created_at FROM (
                    SELECT seq, event, data, created_at
                    FROM group_events WHERE group_id = ?
                    ORDER BY seq DESC LIMIT ?
                ) ORDER BY seq ASC
                """,
                (group_id, limit),
            )
        else:
            rows = await self._db.fetch_all(
                """
                SELECT seq, event, data, created_at FROM (
                    SELECT seq, event, data, created_at
                    FROM group_events WHERE group_id = ? AND thread_id = ?
                    ORDER BY seq DESC LIMIT ?
                ) ORDER BY seq ASC
                """,
                (group_id, thread_id, limit),
            )
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["data"])
            except (TypeError, ValueError):
                # 单条坏数据不该让整个历史打不开：跳过它继续
                continue
            events.append(
                {
                    "seq": row["seq"],
                    "event": row["event"],
                    "data": payload,
                    "created_at": row["created_at"],
                }
            )
        return events

    async def legacy_span(self, group_id: str) -> tuple[str, str] | None:
        """未被认领的历史事件的时间跨度 ``(最早, 最晚)``；没有则 ``None``。

        用于把遗留数据认领成一条对话时，给它一个像样的创建/更新时间 ——
        否则列表里它要么排在最后（用"现在"当时间），要么显示成 1970 年。
        """
        row = await self._db.fetch_one(
            """
            SELECT MIN(created_at) AS first, MAX(created_at) AS last, COUNT(*) AS n
            FROM group_events WHERE group_id = ? AND thread_id = ?
            """,
            (group_id, LEGACY_THREAD_ID),
        )
        if not row or not row["n"]:
            return None
        return (row["first"], row["last"])

    async def adopt_legacy(self, group_id: str, thread_id: str) -> int:
        """把该群未被认领的历史事件改挂到 ``thread_id`` 上，返回改写条数。

        ⚠️ **这是升级不丢数据的关键一步**（见 `DEFAULT_THREAD_ID` 的说明）。
        改写前后那些事件的行数、顺序、内容都不变，只是换了一个归类 ——
        用户可以理解成"历史被收进了第一条对话里"。
        """
        return await self._db.execute_affected(
            "UPDATE group_events SET thread_id = ? WHERE group_id = ? AND thread_id = ?",
            (thread_id, group_id, LEGACY_THREAD_ID),
        )

    async def clear(self, group_id: str, thread_id: str | None = None) -> int:
        """清空对话记录，返回删除条数。

        ``thread_id`` 为 ``None`` 时清**整个群**的事件（删群时用）。
        """
        if thread_id is None:
            return await self._db.execute_affected(
                "DELETE FROM group_events WHERE group_id = ?", (group_id,)
            )
        return await self._db.execute_affected(
            "DELETE FROM group_events WHERE group_id = ? AND thread_id = ?",
            (group_id, thread_id),
        )

    async def delete_group(self, group_id: str) -> int:
        """删群时连带清掉它的全部事件（避免孤儿数据越积越多）。"""
        return await self.clear(group_id, None)
