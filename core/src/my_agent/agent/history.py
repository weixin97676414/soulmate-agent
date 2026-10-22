





















from __future__ import annotations

import logging
from typing import Any

from ..utils.timefmt import format_stamp, parse_iso

logger = logging.getLogger(__name__)


MAX_GROUP_EVENTS = 4000


MAX_SESSIONS = 30

SNIPPET = 300


class HistorySearch:


    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def search(
        self,
        *,
        query: str,
        scope: str = "all",
        group_id: str = "",
        author: str = "",
        since: float | None = None,
        until: float | None = None,
        limit: int = 50,
        assistant_id: str | None = None,
    ) -> dict[str, Any]:
        keyword = (query or "").strip()
        if not keyword:
            return {"count": 0, "results": [], "message": "没有给检索关键词。"}

        notes: list[str] = []
        hits: list[dict[str, Any]] = []
        unknown_time = 0

        if scope in ("all", "group"):
            found, unknown = await self._from_groups(keyword, group_id, author, since, until)
            hits.extend(found)
            unknown_time += unknown
        if scope in ("all", "chat"):
            found, unknown, note = await self._from_chats(keyword, author, since, until)
            hits.extend(found)
            unknown_time += unknown
            if note:
                notes.append(note)
        if scope in ("all", "memory"):
            found, note = await self._from_memory(keyword, since, until, assistant_id, group_id)
            hits.extend(found)
            if note:
                notes.append(note)

        
        hits.sort(key=lambda item: item.get("_at") or 0, reverse=True)
        for item in hits:
            item.pop("_at", None)

        if unknown_time:
            notes.append(
                f"有 {unknown_time} 条更早的记录没有时间戳，无法判断是否落在你给的时间段里，已跳过。"
            )

        return {
            "count": min(len(hits), limit),
            "total": len(hits),
            "results": hits[:limit],
            "notes": notes or None,
            "message": (
                "没有找到相关记录。换一个关键词，或者把时间范围放宽一点试试。"
                if not hits
                else None
            ),
        }

    
    
    
    async def _from_groups(
        self,
        keyword: str,
        group_id: str,
        author: str,
        since: float | None,
        until: float | None,
    ) -> tuple[list[dict[str, Any]], int]:
        runtime = self._runtime
        if not getattr(runtime, "db_ready", False):
            return [], 0

        groups = (
            [runtime.groups.get(group_id)]
            if group_id
            else list(runtime.groups.groups)
        )
        hits: list[dict[str, Any]] = []
        unknown = 0
        for group in groups:
            if group is None:
                continue
            try:
                
                
                
                events = await runtime.group_event_repo.list_events(
                    group.id, None, MAX_GROUP_EVENTS
                )
            except Exception as exc:  
                logger.warning("群记录读取失败 group=%s: %s", group.id, exc)
                continue
            for item in events:
                data = item.get("data") or {}
                if item.get("event") not in ("topic", "message", "summary"):
                    continue
                content = str(data.get("content") or "").strip()
                if not content or keyword.lower() not in content.lower():
                    continue
                who = "用户" if item.get("event") == "topic" else str(data.get("name") or "搭子")
                if author and author not in who:
                    continue
                at = parse_iso(item.get("created_at"))
                if (since is not None or until is not None) and at is None:
                    unknown += 1
                    continue
                if at is not None and since is not None and at < since:
                    continue
                if at is not None and until is not None and at > until:
                    continue
                hits.append(
                    {
                        "source": "群聊",
                        "where": group.name,
                        "author": who,
                        "when": format_stamp(at),
                        "text": content[:SNIPPET],
                        "_at": at or 0,
                    }
                )
        return hits, unknown

    
    
    
    async def _from_chats(
        self,
        keyword: str,
        author: str,
        since: float | None,
        until: float | None,
    ) -> tuple[list[dict[str, Any]], int, str]:
        runtime = self._runtime
        summaries = runtime.sessions.list()
        note = ""
        if len(summaries) > MAX_SESSIONS:
            note = (
                f"单聊只翻了最近 {MAX_SESSIONS} 个会话（共 {len(summaries)} 个）；"
                "更早的会话没有检索。"
            )
        hits: list[dict[str, Any]] = []
        unknown = 0
        for summary in summaries[:MAX_SESSIONS]:
            session_id = str(summary.get("id") or "")
            if not session_id:
                continue
            try:
                session = await runtime.sessions.get(session_id)
            except Exception as exc:  
                logger.warning("会话读取失败 session=%s: %s", session_id, exc)
                continue
            who_assistant = self._assistant_name(session.assistant_id)
            title = session.title or "（未命名对话）"
            for message in session.history():
                content = str(message.get("content") or "").strip()
                if not content or keyword.lower() not in content.lower():
                    continue
                is_user = message.get("role") == "user"
                who = "我" if is_user else who_assistant
                if author and author not in who:
                    continue
                at = message.get("created_at")
                at = float(at) if isinstance(at, (int, float)) and at else None
                if (since is not None or until is not None) and at is None:
                    unknown += 1
                    continue
                if at is not None and since is not None and at < since:
                    continue
                if at is not None and until is not None and at > until:
                    continue
                hits.append(
                    {
                        "source": "单聊",
                        "where": title,
                        "author": who,
                        "when": format_stamp(at),
                        "text": content[:SNIPPET],
                        "_at": at or 0,
                    }
                )
        return hits, unknown, note

    
    
    
    async def _from_memory(
        self,
        keyword: str,
        since: float | None,
        until: float | None,
        assistant_id: str | None,
        group_id: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        runtime = self._runtime
        settings = runtime.config.settings
        if not settings.memory.long_term_enabled:
            
            return [], "长期记忆没有打开（设置 → 安全与通用 → 长期记忆），本次没有检索它。"

        
        
        sources: list[tuple[str, Any]] = []
        if assistant_id:
            sources.append(("当前搭子", runtime.memory_for(assistant_id)))
        
        joined_groups: list[str] = []
        if group_id:
            
            
            sources.append(("当前群", runtime.memory_for_group(group_id)))
        elif assistant_id:
            
            
            
            
            
            
            joined_groups = runtime.groups_for_assistant(assistant_id)
            for joined in joined_groups:
                sources.append(
                    (f"群「{self._group_name(joined)}」", runtime.memory_for_group(joined))
                )
        sources.append(("全局", runtime.memory_for(None)))

        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        unavailable = 0
        
        
        
        rebuilding = 0
        for label, memory in sources:
            if not getattr(memory, "available", False):
                unavailable += 1
                continue
            if getattr(memory, "rebuilding", False):
                rebuilding += 1
                continue
            try:
                
                
                
                found = await memory.search(keyword, since=since, until=until)
            except Exception as exc:  
                logger.warning("长期记忆检索失败（%s）: %s", label, exc)
                unavailable += 1
                continue
            for hit in found:
                if hit.id in seen:
                    continue
                seen.add(hit.id)
                tags = str(hit.metadata.get("tags") or "").strip()
                hits.append(
                    {
                        "source": "长期记忆",
                        "where": f"{label}·{tags}" if tags else label,
                        "author": "",
                        "when": format_stamp(hit.ts),
                        "text": hit.text[:SNIPPET],
                        "score": round(hit.score, 4),
                        "_at": hit.ts or 0,
                    }
                )
        note = ""
        if rebuilding:
            note = (
                "长期记忆正在用当前模型重建向量（嵌入方式换过），这几个库这次先跳过；"
                "原文都还在库里，重建完就能照常检索。"
            )
        if len(joined_groups) > 3:
            
            
            
            extra = f"本次检索并入了 {len(joined_groups)} 个群的共同记忆。"
            note = f"{note}{extra}" if note else extra
        if unavailable:
            extra = (
                f"有 {unavailable} 个长期记忆库当前不可用（没装 chromadb 或读取出错），"
                "本次没有检索它们（详见应用日志）。"
            )
            note = f"{note}{extra}" if note else extra
        return hits, note

    def _group_name(self, group_id: str) -> str:





        if not group_id:
            return ""
        try:
            group = self._runtime.groups.get(group_id)
        except Exception:  
            return group_id
        name = str(getattr(group, "name", "") or "").strip()
        return name or group_id

    def _assistant_name(self, assistant_id: str | None) -> str:
        if not assistant_id:
            return "搭子"
        profile = self._runtime.assistants.get(assistant_id)
        if profile is None:
            return "搭子"
        return profile.nickname or profile.name
