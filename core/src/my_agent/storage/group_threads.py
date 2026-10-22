
























from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from .db import Database
from .group_events import GroupEventRepository





LEGACY_TITLE = "对话记录"


DEFAULT_TITLE = "新对话"


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GroupThreadRepository:


    def __init__(self, db: Database, events: GroupEventRepository) -> None:
        self._db = db
        self._events = events

    async def list_threads(self, group_id: str) -> list[dict[str, Any]]:





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

        row = await self._db.fetch_one(
            """
            SELECT id, group_id, title, created_at, updated_at
            FROM group_threads WHERE id = ? AND group_id = ?
            """,
            (thread_id, group_id),
        )
        return dict(row) if row else None

    async def rename(self, group_id: str, thread_id: str, title: str) -> bool:

        clean = title.strip()
        if not clean:
            return False
        affected = await self._db.execute_affected(
            "UPDATE group_threads SET title = ? WHERE id = ? AND group_id = ?",
            (clean, thread_id, group_id),
        )
        return affected > 0

    async def touch(self, group_id: str, thread_id: str, occurred_at: str | None = None) -> None:





        await self._db.execute(
            "UPDATE group_threads SET updated_at = ? WHERE id = ? AND group_id = ?",
            (occurred_at or _now(), thread_id, group_id),
        )

    async def delete(self, group_id: str, thread_id: str) -> bool:





        affected = await self._db.execute_affected(
            "DELETE FROM group_threads WHERE id = ? AND group_id = ?",
            (thread_id, group_id),
        )
        if affected == 0:
            return False
        await self._events.clear(group_id, thread_id)
        return True

    async def delete_group(self, group_id: str) -> None:

        await self._db.execute_affected(
            "DELETE FROM group_threads WHERE group_id = ?", (group_id,)
        )

    
    
    
    async def _adopt_legacy(self, group_id: str) -> None:






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
