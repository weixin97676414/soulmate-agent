























from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .db import Database



MAX_REPLAY_EVENTS = 4000






LEGACY_THREAD_ID = ""


class GroupEventRepository:


    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, group_id: str, thread_id: str, event: str, data: dict[str, Any]) -> None:








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






        return await self._db.execute_affected(
            "UPDATE group_events SET thread_id = ? WHERE group_id = ? AND thread_id = ?",
            (thread_id, group_id, LEGACY_THREAD_ID),
        )

    async def clear(self, group_id: str, thread_id: str | None = None) -> int:




        if thread_id is None:
            return await self._db.execute_affected(
                "DELETE FROM group_events WHERE group_id = ?", (group_id,)
            )
        return await self._db.execute_affected(
            "DELETE FROM group_events WHERE group_id = ? AND thread_id = ?",
            (group_id, thread_id),
        )

    async def delete_group(self, group_id: str) -> int:

        return await self.clear(group_id, None)
