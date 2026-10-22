






















from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import Message, ToolCall
from .db import Database

logger = logging.getLogger(__name__)

DELETE_MESSAGES = "DELETE FROM messages WHERE session_id = ?"
INSERT_MESSAGE = """
INSERT INTO messages
    (session_id, seq, role, content, reasoning_content, tool_calls, tool_call_id, name,
     created_at, ts_trusted, plan)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""



MESSAGE_FINGERPRINT = (
    "SELECT seq, role, length(content) AS content_len FROM messages "
    "WHERE session_id = ? ORDER BY seq"
)


LAST_MESSAGE_CONTENT = (
    "SELECT content FROM messages WHERE session_id = ? ORDER BY seq DESC LIMIT 1"
)
UPSERT_SESSION = """
INSERT INTO sessions
    (id, title, model_id, system_prompt, enabled_skills, assistant_id,
     context_summary, context_summary_upto, reasoning_effort,
     message_count, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    model_id = excluded.model_id,
    system_prompt = excluded.system_prompt,
    enabled_skills = excluded.enabled_skills,
    assistant_id = excluded.assistant_id,
    context_summary = excluded.context_summary,
    context_summary_upto = excluded.context_summary_upto,
    reasoning_effort = excluded.reasoning_effort,
    message_count = excluded.message_count,
    updated_at = excluded.updated_at
"""


@dataclass
class SessionRecord:


    id: str
    title: str = "新对话"
    model_id: str | None = None
    system_prompt: str = ""
    enabled_skills: list[str] | None = None
    assistant_id: str | None = None
    
    
    
    context_summary: str = ""
    context_summary_upto: int = 0
    
    
    
    reasoning_effort: str | None = None
    message_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _plan_to_json(plan: dict[str, Any] | None) -> str | None:

    if not plan:
        return None
    return json.dumps(plan, ensure_ascii=False)


def _plan_from_json(raw: str | None) -> dict[str, Any] | None:

    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("消息中的 plan 字段损坏，已忽略: %s", raw[:120])
        return None
    return data if isinstance(data, dict) else None


def _tool_calls_to_json(tool_calls: list[ToolCall] | None) -> str | None:
    if not tool_calls:
        return None
    return json.dumps(
        [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
                "raw_arguments": call.raw_arguments,
            }
            for call in tool_calls
        ],
        ensure_ascii=False,
    )


def _tool_calls_from_json(raw: str | None) -> list[ToolCall] | None:
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("消息中的 tool_calls 字段损坏，已忽略: %s", raw[:120])
        return None
    if not isinstance(items, list):
        return None
    calls: list[ToolCall] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        calls.append(
            ToolCall(
                id=str(item.get("id") or ""),
                name=str(item["name"]),
                arguments=item.get("arguments") or {},
                raw_arguments=str(item.get("raw_arguments") or ""),
            )
        )
    return calls or None


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    
    
    
    async def list_sessions(self) -> list[SessionRecord]:
        rows = await self._db.fetch_all(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        )
        return [self._row_to_record(row) for row in rows]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        row = await self._db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return self._row_to_record(row) if row else None

    async def count_sessions(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM sessions")
        return int(row["n"]) if row else 0

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> SessionRecord:
        raw_skills = row.get("enabled_skills")
        skills: list[str] | None = None
        if raw_skills:
            try:
                parsed = json.loads(raw_skills)
                if isinstance(parsed, list):
                    skills = [str(item) for item in parsed]
            except json.JSONDecodeError:
                skills = None
        return SessionRecord(
            id=row["id"],
            title=row["title"],
            model_id=row.get("model_id"),
            system_prompt=row.get("system_prompt") or "",
            enabled_skills=skills,
            assistant_id=row.get("assistant_id"),
            context_summary=row.get("context_summary") or "",
            context_summary_upto=int(row.get("context_summary_upto") or 0),
            
            reasoning_effort=row.get("reasoning_effort") or None,
            message_count=int(row.get("message_count") or 0),
            created_at=float(row.get("created_at") or 0),
            updated_at=float(row.get("updated_at") or 0),
        )

    
    
    
    async def save_session(
        self,
        record: SessionRecord,
        messages: list[Message] | None = None,
        *,
        mode: str = "replace",
    ) -> None:






        enabled = (
            json.dumps(record.enabled_skills, ensure_ascii=False)
            if record.enabled_skills
            else None
        )
        statements: list[tuple[str, tuple[Any, ...]]] = [
            (
                UPSERT_SESSION,
                (
                    record.id,
                    record.title,
                    record.model_id,
                    record.system_prompt,
                    enabled,
                    record.assistant_id,
                    record.context_summary,
                    record.context_summary_upto,
                    record.reasoning_effort,
                    record.message_count,
                    record.created_at,
                    record.updated_at,
                ),
            )
        ]

        if messages is not None:
            now = time.time()
            
            
            
            
            
            
            prefix: int | None = None
            if mode == "append":
                prefix = await self._stored_prefix_len(record.id, messages)
                if prefix is None:
                    logger.info(
                        "会话 %s 的消息前缀与库里对不上（疑似回滚/清空/改写），本次退回全量重写",
                        record.id,
                    )
            if prefix is None:
                prefix = 0
                statements.append((DELETE_MESSAGES, (record.id,)))
            
            
            
            
            
            
            
            
            statements.extend(
                (
                    INSERT_MESSAGE,
                    (
                        record.id,
                        seq,
                        message.role,
                        message.content,
                        message.reasoning_content,
                        _tool_calls_to_json(message.tool_calls),
                        message.tool_call_id,
                        message.name,
                        message.created_at if message.created_at is not None else now,
                        1 if message.created_at is not None else 0,
                        _plan_to_json(message.plan),
                    ),
                )
                
                for seq, message in enumerate(messages)
                if seq >= prefix
            )

        await self._db.transaction(statements)

    async def _stored_prefix_len(
        self, session_id: str, messages: list[Message]
    ) -> int | None:


















        rows = await self._db.fetch_all(MESSAGE_FINGERPRINT, (session_id,))
        if len(rows) > len(messages):
            return None
        for index, row in enumerate(rows):
            message = messages[index]
            if row["role"] != message.role:
                return None
            if int(row.get("content_len") or 0) != len(message.content or ""):
                return None
        if rows:
            last = await self._db.fetch_one(LAST_MESSAGE_CONTENT, (session_id,))
            if last is None or (last.get("content") or "") != (
                messages[len(rows) - 1].content or ""
            ):
                return None
        return len(rows)

    async def load_messages(self, session_id: str) -> list[Message]:
        rows = await self._db.fetch_all(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [
            Message(
                role=row["role"],
                content=row["content"] or "",
                tool_calls=_tool_calls_from_json(row.get("tool_calls")),
                tool_call_id=row.get("tool_call_id"),
                name=row.get("name"),
                reasoning_content=row.get("reasoning_content") or "",
                
                
                created_at=float(row["created_at"]) if row.get("ts_trusted") else None,
                
                plan=_plan_from_json(row.get("plan")),
            )
            for row in rows
        ]

    async def clear_messages(self, session_id: str, *, updated_at: float | None = None) -> None:
        await self._db.transaction(
            [
                (DELETE_MESSAGES, (session_id,)),
                (
                    "UPDATE sessions SET message_count = 0, updated_at = ? WHERE id = ?",
                    (updated_at or time.time(), session_id),
                ),
            ]
        )

    async def delete_session(self, session_id: str) -> bool:
        existing = await self.get_session(session_id)
        if existing is None:
            return False
        
        
        await self._db.transaction(
            [
                (DELETE_MESSAGES, (session_id,)),
                ("DELETE FROM sessions WHERE id = ?", (session_id,)),
            ]
        )
        return True

    async def delete_sessions(self, session_ids: list[str]) -> int:






        if not session_ids:
            return 0

        placeholders = ",".join("?" for _ in session_ids)
        params = tuple(session_ids)
        rows = await self._db.fetch_all(
            f"SELECT id FROM sessions WHERE id IN ({placeholders})", params
        )
        existing = [str(row["id"]) for row in rows]
        if not existing:
            return 0

        
        
        placeholders = ",".join("?" for _ in existing)
        params = tuple(existing)
        
        
        await self._db.transaction(
            [
                (f"DELETE FROM messages WHERE session_id IN ({placeholders})", params),
                (f"DELETE FROM sessions WHERE id IN ({placeholders})", params),
            ]
        )
        return len(existing)
