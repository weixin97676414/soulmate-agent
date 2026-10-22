
























from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..llm.base import ImagePart, Message, ToolCall
from ..security.injection import UNTRUSTED_CLOSE, annotate
from ..utils.timefmt import format_message_time, format_now
from . import spill as spill_mod
from .spill import DEFAULT_DELIVER_CHARS

logger = logging.getLogger(__name__)









IMAGE_TOKEN_ESTIMATE = 1200























INTERNAL_OPEN = "⟪internal⟫"
INTERNAL_CLOSE = "⟪/internal⟫"


def internal_hint(text: str) -> str:

    return f"{INTERNAL_OPEN}{text}{INTERNAL_CLOSE}"


def is_internal(content: str) -> bool:

    return content.startswith(INTERNAL_OPEN)












SUMMARY_PREFIX = (
    "以下是与你更早对话的**摘要**（不是原文，用于保持连续性，不必逐字复述）。\n"
    "更早的完整对话记录**没有被删除**：它仍然保存在用户的会话里、用户随时能看到，"
    "只是没有再随本次请求发送。\n"
    "如果摘要没有覆盖到你需要的具体细节，请**直接说明你需要什么或询问用户**，"
    "不要凭猜测补全被省略的部分。\n"
    "摘要如下：\n"
)


def dropped_notice(count: int) -> str:








    return (
        f"[说明：为腾出上下文容量，更早的 {count} 条消息这一次没有随请求发送。"
        "这些内容**没有被删除** —— 用户在自己的对话记录里仍能看到完整历史。"
        "如果你需要其中的具体细节，请明确说明你需要什么，或直接询问用户；"
        "不要凭猜测补上被省略的部分。]"
    )


def summary_message(summary: str) -> Message:

    return Message(role="system", content=f"{SUMMARY_PREFIX}{summary}")















def with_time_prefixes(messages: list[Message]) -> list[Message]:













    if not messages:
        return messages
    last_user = max(
        (index for index, item in enumerate(messages) if item.role == "user"),
        default=-1,
    )
    out: list[Message] = []
    for index, message in enumerate(messages):
        if message.created_at is None or message.role not in ("user", "assistant"):
            out.append(message)
            continue
        if index == last_user:
            prefix = f"现在：{format_now(message.created_at)}\n"
        else:
            prefix = f"[{format_message_time(message.created_at)}] "
        
        
        out.append(replace(message, content=f"{prefix}{message.content}"))
    return out


class MemoryManager:


    def __init__(
        self,
        *,
        max_context_tokens: int = 32000,
        spill_root: Path | None = None,
        spill_session: str = "",
        deliver_chars: int = DEFAULT_DELIVER_CHARS,
    ) -> None:
        self._messages: list[Message] = []
        self._max_tokens = max_context_tokens
        
        
        self._spill_root = spill_root
        self._spill_session = spill_session
        
        self._deliver_chars = deliver_chars
        
        
        self._spilled: dict[str, tuple[Path, int]] = {}
        
        
        
        
        
        self._summary = ""
        self._summary_upto = 0

    def configure(
        self,
        *,
        max_context_tokens: int | None = None,
        spill_root: Path | None = None,
        spill_session: str | None = None,
    ) -> None:






        if max_context_tokens is not None:
            self._max_tokens = max_context_tokens
        if spill_root is not None:
            self._spill_root = spill_root
        if spill_session is not None:
            self._spill_session = spill_session

    
    
    
    def ensure_system(self, prompt: str) -> None:








        if not prompt:
            if self._has_system:
                del self._messages[0]
                
                
                self._summary_upto = max(0, self._summary_upto - 1)
            return
        if self._messages and self._messages[0].role == "system":
            if self._messages[0].content != prompt:
                self._messages[0] = Message(role="system", content=prompt)
            return
        self._messages.insert(0, Message(role="system", content=prompt))

    def add_user(self, text: str, *, images: list[ImagePart] | None = None) -> Message:
        
        msg = Message(role="user", content=text, images=list(images or []), created_at=time.time())
        self._messages.append(msg)
        return msg

    def add_assistant(
        self,
        content: str,
        tool_calls: list[ToolCall] | None = None,
        reasoning_content: str = "",
        plan: dict[str, Any] | None = None,
    ) -> Message:
        msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or None,
            reasoning_content=reasoning_content,
            created_at=time.time(),
            plan=plan,
        )
        self._messages.append(msg)
        return msg

    def add_tool(self, tool_call_id: str, name: str, result: str) -> Message:


















        text = str(result)
        annotated, hits = annotate(text, source=name)
        
        
        
        
        
        
        
        
        

        msg = Message(
            role="tool",
            content=annotated,
            tool_call_id=tool_call_id,
            name=name,
            injection_hits=[hit.label for hit in hits],
            created_at=time.time(),
        )
        self._messages.append(msg)
        return msg

    def pop_last_assistant(self) -> Message | None:

        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i].role == "assistant":
                return self._messages.pop(i)
        return None

    
    
    
    @property
    def summary(self) -> str:
        return self._summary

    @property
    def summary_upto(self) -> int:

        return self._summary_upto

    def set_summary(self, summary: str, upto: int) -> None:





        self._summary = summary.strip()
        self._summary_upto = max(0, min(upto, len(self._messages)))

    def clear_summary(self) -> None:
        self._summary = ""
        self._summary_upto = 0

    def compressible_range(self, *, keep_recent: int) -> tuple[int, int]:



















        start = max(self._summary_upto, 1 if self._has_system else 0)
        end = len(self._messages) - max(keep_recent, 0)
        
        while start < end < len(self._messages) and self._messages[end].role == "tool":
            end -= 1
        return (start, end) if end > start else (start, start)

    @property
    def _has_system(self) -> bool:
        return bool(self._messages) and self._messages[0].role == "system"

    
    
    
    def get_context(self) -> list[Message]:





        head, body = self._split_head()
        prefix = list(head)
        if self._summary:
            prefix.append(summary_message(self._summary))

        
        covered = max(0, min(self._summary_upto - len(head), len(body)))
        
        
        
        while covered < len(body) and body[covered].role == "tool":
            covered += 1
        budget = max(self._max_tokens - self._estimate_tokens(prefix), 0)
        
        
        body = self._externalize(body[covered:])
        kept = self._trim(body, budget)

        
        
        
        
        
        
        
        dropped = len(body) - len(kept)
        if dropped > 0:
            kept = [Message(role="system", content=dropped_notice(dropped)), *kept]
        
        
        
        return with_time_prefixes(prefix + kept)

    
    
    
    def externalize_oversized(self) -> int:














        if self._spill_root is None:
            return 0
        count = 0
        for message in self._messages:
            key = message.tool_call_id or ""
            if message.role != "tool" or not key or key in self._spilled:
                continue
            if len(message.content) <= self._deliver_chars:
                continue
            try:
                path = spill_mod.write_spill(
                    self._spill_root, self._spill_session, key, message.content
                )
            except OSError as exc:
                
                
                logger.warning("工具结果无损外置失败，将按原样投递：%s", exc)
                continue
            head = message.content[: self._deliver_chars]
            if not head.rstrip().endswith(UNTRUSTED_CLOSE):
                head = f"{head}\n{UNTRUSTED_CLOSE}"
            pointer = spill_mod.deliver_pointer(
                path,
                total_chars=len(message.content),
                delivered_chars=self._deliver_chars,
            )
            self._spilled[key] = f"{head}\n{pointer}"
            count += 1
        if count:
            logger.info("上下文超限：已无损外置 %s 条超长工具结果并重试", count)
        return count

    def _externalize(self, messages: list[Message]) -> list[Message]:





        if not self._spilled:
            return messages
        out: list[Message] = []
        for message in messages:
            key = message.tool_call_id or ""
            view = self._spilled.get(key) if key else None
            
            if view is None or len(message.content) <= self._deliver_chars:
                out.append(message)
                continue
            out.append(replace(message, content=view))
        return out

    def _split_head(self) -> tuple[list[Message], list[Message]]:
        if self._has_system:
            return [self._messages[0]], list(self._messages[1:])
        return [], list(self._messages)

    @property
    def messages(self) -> list[Message]:

        return self._messages

    @property
    def last_message(self) -> Message | None:
        return self._messages[-1] if self._messages else None

    def __len__(self) -> int:
        return len(self._messages)

    
    
    
    def _trim(self, messages: list[Message], budget: int) -> list[Message]:






        if not messages:
            return messages

        
        
        
        sizes = [self._estimate_tokens([message]) for message in messages]
        total = sum(sizes)
        if total <= budget:
            return messages

        cut = 0
        while cut < len(messages) and total > budget:
            total -= sizes[cut]
            cut += 1
        while cut < len(messages) and messages[cut].role == "tool":
            cut += 1

        return messages[cut:]

    def _truncate(self, messages: list[Message]) -> list[Message]:

        system = [m for m in messages[:1] if m.role == "system"]
        rest = messages[len(system) :]
        budget = self._max_tokens - self._estimate_tokens(system)
        return system + self._trim(rest, max(budget, 0))

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:

        total = 0
        for m in messages:
            total += len(m.content) // 2
            total += 4  
            
            
            
            total += len(m.images) * IMAGE_TOKEN_ESTIMATE
            for tc in m.tool_calls or []:
                total += len(tc.name) // 2 + len(tc.raw_arguments) // 2 + 4
        return total

    def estimated_tokens(self) -> int:

        return self._estimate_tokens(self._messages)

    def context_tokens(self) -> int:






        return self._estimate_tokens(self.get_context())

    
    
    
    def to_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for m in self._messages:
            records.append(
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                    "tool_calls": [tc.to_openai() for tc in m.tool_calls] if m.tool_calls else None,
                    "created_at": m.created_at,
                    
                    
                    "plan": m.plan,
                }
            )
        return records

    def clear(self, *, keep_system: bool = True) -> None:
        
        
        
        
        keep = keep_system and self._has_system
        self._messages = self._messages[:1] if keep else []
        
        
        self.clear_summary()

    def replace(
        self,
        messages: list[Message],
        *,
        summary: str = "",
        summary_upto: int = 0,
    ) -> None:






        self._messages = list(messages)
        self.clear_summary()
        if summary:
            self.set_summary(summary, summary_upto or len(self._messages))
