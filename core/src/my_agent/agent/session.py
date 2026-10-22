












from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import SessionNotFoundError
from ..memory.short_term import MemoryManager, is_internal

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL = 60 * 60 * 24 * 7  


@dataclass
class Session:
    id: str
    title: str = "新对话"
    model_id: str | None = None
    system_prompt: str = ""
    enabled_skills: set[str] | None = None
    assistant_id: str | None = None
    
    reasoning_effort: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    memory: MemoryManager = field(default_factory=MemoryManager)
    
    message_count: int = 0
    
    
    
    
    context_summary: str = ""
    context_summary_upto: int = 0
    
    
    
    
    
    
    
    
    
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.updated_at = time.time()

    def apply_assistant(self, profile: Any) -> None:










        self.assistant_id = profile.id
        self.system_prompt = profile.system_prompt
        
        
        
        
        
        self.enabled_skills = set(profile.enabled_skills) or None
        if profile.model_id:
            self.model_id = profile.model_id
        
        
        
        
        
        
        
        
        if getattr(profile, "reasoning_effort", None):
            self.reasoning_effort = profile.reasoning_effort
        self.touch()

    def auto_title(self, first_message: str) -> None:

        if self.title != "新对话" or not first_message.strip():
            return
        text = " ".join(first_message.strip().split())
        self.title = text[:24] + ("…" if len(text) > 24 else "")

    def recount(self) -> int:

        self.message_count = sum(
            1 for message in self.memory.messages if message.role in ("user", "assistant")
        )
        return self.message_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model_id": self.model_id,
            "assistant_id": self.assistant_id,
            
            
            "reasoning_effort": self.reasoning_effort,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }

    def history(self) -> list[dict[str, Any]]:

        out: list[dict[str, Any]] = []
        for message in self.memory.messages:
            if message.role not in ("user", "assistant"):
                continue
            if (
                message.role == "assistant"
                and not message.content
                and not message.plan
                and not message.tool_calls
                and not message.reasoning_content
            ):
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                continue
            if message.role == "user" and is_internal(message.content):
                continue  
            
            
            
            item: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            
            if message.plan:
                item["plan"] = message.plan
            
            
            
            
            
            
            if message.reasoning_content:
                item["reasoning"] = message.reasoning_content
            if message.tool_calls:
                
                
                
                
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in message.tool_calls
                ]
            out.append(item)
        return out


class SessionManager:


    def __init__(
        self,
        *,
        repository: Any = None,
        ttl_seconds: int = DEFAULT_SESSION_TTL,
        on_persist_error: Callable[[Session, Exception], None] | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._repo = repository
        self._ttl = ttl_seconds
        
        self._loaded: set[str] = set()
        
        
        
        self._on_persist_error = on_persist_error

    @property
    def persistent(self) -> bool:
        return self._repo is not None

    
    
    
    async def initialize(self) -> int:

        if self._repo is None:
            return 0
        records = await self._repo.list_sessions()
        for record in records:
            self._sessions[record.id] = Session(
                id=record.id,
                title=record.title,
                model_id=record.model_id,
                system_prompt=record.system_prompt,
                enabled_skills=set(record.enabled_skills) if record.enabled_skills else None,
                assistant_id=record.assistant_id,
                reasoning_effort=record.reasoning_effort,
                created_at=record.created_at,
                updated_at=record.updated_at,
                message_count=record.message_count,
                context_summary=record.context_summary,
                context_summary_upto=record.context_summary_upto,
            )
        if records:
            logger.info("已恢复 %s 个历史会话", len(records))
        return len(records)

    
    
    
    async def create(
        self, *, model_id: str | None = None, title: str = "新对话"
    ) -> Session:
        session = Session(id=uuid.uuid4().hex[:12], title=title, model_id=model_id)
        self._sessions[session.id] = session
        self._loaded.add(session.id)
        await self.persist(session, include_messages=True)
        return session

    async def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"会话不存在或已过期: {session_id}")
        await self._ensure_loaded(session)
        return session

    async def get_or_create(
        self, session_id: str | None, *, model_id: str | None = None
    ) -> Session:
        if not session_id:
            return await self.create(model_id=model_id)

        session = self._sessions.get(session_id)
        if session is None:
            session = await self._restore_or_create(session_id, model_id=model_id)
        await self._ensure_loaded(session)
        return session

    async def _restore_or_create(
        self, session_id: str, *, model_id: str | None = None
    ) -> Session:









        record = None
        if self._repo is not None:
            record = await self._repo.get_session(session_id)

        if record is not None:
            session = Session(
                id=record.id,
                title=record.title,
                model_id=record.model_id or model_id,
                system_prompt=record.system_prompt,
                enabled_skills=set(record.enabled_skills) if record.enabled_skills else None,
                assistant_id=record.assistant_id,
                reasoning_effort=record.reasoning_effort,
                created_at=record.created_at,
                updated_at=record.updated_at,
                message_count=record.message_count,
                context_summary=record.context_summary,
                context_summary_upto=record.context_summary_upto,
            )
            
            self._sessions[session_id] = session
            logger.info("会话 %s 已从数据库重新载入内存", session_id)
            return session

        
        
        session = Session(id=session_id, model_id=model_id)
        self._sessions[session_id] = session
        self._loaded.add(session_id)
        await self.persist(session, include_messages=True)
        return session

    def list(self) -> list[dict[str, Any]]:
        sessions = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
        return [session.to_dict() for session in sessions]

    async def rename(self, session_id: str, title: str) -> Session:
        session = await self.get(session_id)
        session.title = title.strip() or session.title
        session.touch()
        await self.persist(session)
        return session

    async def update_meta(
        self,
        session_id: str,
        *,
        model_id: str | None = None,
        system_prompt: str | None = None,
        enabled_skills: set[str] | None = None,
    ) -> Session:
        session = await self.get(session_id)
        if model_id is not None:
            session.model_id = model_id
        if system_prompt is not None:
            session.system_prompt = system_prompt
            
            session.memory.clear(keep_system=False)
        if enabled_skills is not None:
            session.enabled_skills = enabled_skills or None
        session.touch()
        await self.persist(session, include_messages=system_prompt is not None)
        return session

    async def delete(self, session_id: str) -> bool:
        existed = self._sessions.pop(session_id, None) is not None
        self._loaded.discard(session_id)
        if self._repo is not None:
            removed = await self._repo.delete_session(session_id)
            return existed or removed
        return existed

    async def delete_many(self, session_ids: list[str]) -> int:
        
        deleted = 0
        for session_id in session_ids:
            if await self.delete(session_id):
                deleted += 1
        return deleted

    async def clear_history(self, session_id: str) -> Session:
        session = await self.get(session_id)
        session.memory.clear(keep_system=True)
        session.recount()
        session.touch()
        await self.persist(session, include_messages=True)
        return session

    
    
    
    async def _ensure_loaded(self, session: Session) -> None:
        if session.id in self._loaded:
            return
        if self._repo is None:
            self._loaded.add(session.id)
            return
        messages = await self._repo.load_messages(session.id)
        
        
        
        session.memory.replace(
            messages,
            summary=session.context_summary,
            summary_upto=session.context_summary_upto,
        )
        self._loaded.add(session.id)

    async def persist(
        self,
        session: Session,
        *,
        include_messages: bool = False,
        mode: str = "replace",
    ) -> None:














        if self._repo is None:
            return
        if session.id in self._loaded:
            
            
            
            session.context_summary = session.memory.summary
            session.context_summary_upto = session.memory.summary_upto
        session.recount()
        record = self._to_record(session)
        try:
            await self._repo.save_session(
                record,
                session.memory.messages if include_messages else None,
                mode=mode if include_messages else "replace",
            )
        except Exception as exc:  
            
            
            logger.error("会话落盘失败 session=%s: %s", session.id, exc)
            if self._on_persist_error is not None:
                
                with contextlib.suppress(Exception):
                    self._on_persist_error(session, exc)

    @staticmethod
    def _to_record(session: Session):
        from ..storage.sessions import SessionRecord

        return SessionRecord(
            id=session.id,
            title=session.title,
            model_id=session.model_id,
            system_prompt=session.system_prompt,
            enabled_skills=sorted(session.enabled_skills) if session.enabled_skills else None,
            assistant_id=session.assistant_id,
            reasoning_effort=session.reasoning_effort,
            context_summary=session.context_summary,
            context_summary_upto=session.context_summary_upto,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    
    
    
    def evict_expired(self) -> int:

        now = time.time()
        expired = [
            key
            for key, session in self._sessions.items()
            if now - session.updated_at > self._ttl and key in self._loaded
        ]
        for key in expired:
            del self._sessions[key]
            self._loaded.discard(key)
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)
