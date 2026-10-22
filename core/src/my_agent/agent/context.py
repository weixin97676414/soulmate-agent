






























from __future__ import annotations

import logging
from dataclasses import dataclass

from ..errors import ContextOverflowError, LLMError
from ..llm.base import BaseLLM, Message
from ..memory.short_term import MemoryManager
from ..utils.timefmt import format_message_time

logger = logging.getLogger(__name__)



_OVERFLOW_HINTS = (
    "context length",
    "context_length",
    "maximum context",
    "max context",
    "too many tokens",
    "token limit",
    "reduce the length",
    "string too long",
    "context window",
    "maximum number of tokens",
    "input is too long",
    "exceeds the maximum",
)


def looks_like_context_overflow(message: str) -> bool:





    lowered = message.lower()
    return any(hint in lowered for hint in _OVERFLOW_HINTS)


@dataclass
class ContextPolicy:


    
    
    reserve_tokens: int = 1024
    
    keep_recent: int = 6
    
    compress_threshold: float = 0.8
    
    
    
    
    
    max_summary_chars: int = 2400
    
    summarize_budget_tokens: int = 6000


_SUMMARIZE_SYSTEM = """你是一个对话记录压缩器。把用户提供的对话片段压缩成简短摘要。

要求：
1. **只保留事实**：用户的目标与偏好、已达成的约定、涉及的文件名与路径、
   关键数据与数字、已经排除掉的方案及原因、尚未解决的问题。
2. 不要复述寒暄、不要评论、不要输出"以上是摘要"之类的话，直接给摘要正文。
3. 不要编造片段里没有的信息。
4. **时间要落到绝对日期**：片段里每条消息前都有 `[月-日 时:分]`，遇到"昨天""上周"
   "刚才"这类相对说法，请换算成具体日期写进摘要（例如"9 月 24 日改过方案"）。
   摘要会被用在很久以后的对话里，相对时间在那里等于没有信息。
5. 用简体中文，条目式，尽量紧凑。"""

_MERGE_SYSTEM = """你在合并几段对话摘要。把它们整合成一段连续的摘要。

要求：
1. 合并重复信息，保留所有**事实性约定**（文件名、路径、数字、口径、已排除的方案）。
2. 按时间先后组织，不要分类罗列；时间用**绝对日期**，不要保留"昨天/上周"这类说法。
3. 不要评论，不要输出"以下是合并结果"之类的话，直接给摘要正文。
4. 用简体中文，条目式，尽量紧凑。"""


def render_transcript(messages: list[Message]) -> str:









    lines: list[str] = []
    for message in messages:
        stamp = f"[{format_message_time(message.created_at)}] " if message.created_at else ""
        if message.role == "tool":
            lines.append(f"{stamp}[工具结果 {message.name or ''}] {message.content}")
            continue
        if message.role == "assistant":
            if message.content:
                lines.append(f"{stamp}[助手] {message.content}")
            for call in message.tool_calls or []:
                lines.append(f"{stamp}[助手调用工具] {call.name}({call.raw_arguments or call.arguments})")
            continue
        if message.role == "system":
            
            
            continue
        lines.append(f"{stamp}[用户] {message.content}")
    return "\n".join(lines)


class ContextGuard:


    def __init__(self, policy: ContextPolicy | None = None) -> None:
        self.policy = policy or ContextPolicy()

    
    
    
    def usage_ratio(self, memory: MemoryManager, token_limit: int) -> float:

        if token_limit <= 0:
            return 0.0
        return memory.context_tokens() / token_limit

    def should_compress(self, memory: MemoryManager, token_limit: int) -> bool:

        if token_limit <= 0:
            return False
        if self.usage_ratio(memory, token_limit) < self.policy.compress_threshold:
            return False
        start, end = memory.compressible_range(keep_recent=self.policy.keep_recent)
        return end > start

    def check(self, memory: MemoryManager, token_limit: int) -> None:






        budget = token_limit - self.policy.reserve_tokens
        if budget <= 0:
            return
        used = memory.context_tokens()
        if used > budget:
            raise ContextOverflowError(
                f"上下文用量 {used} token 已超过模型可用窗口 {budget} token，正在压缩历史。",
                detail={"used": used, "budget": budget},
            )

    
    
    
    async def compress(
        self,
        llm: BaseLLM,
        memory: MemoryManager,
        *,
        token_limit: int,
    ) -> bool:





        start, end = memory.compressible_range(keep_recent=self.policy.keep_recent)
        if end <= start:
            return False

        target = memory.messages[start:end]
        try:
            summary = await self._summarize(llm, target, token_limit=token_limit)
        except LLMError as exc:
            logger.warning("上下文压缩失败，回落到裁剪: %s", exc)
            return False
        except Exception as exc:  
            logger.warning("上下文压缩出现意外错误，回落到裁剪: %s", exc)
            return False

        if not summary:
            return False

        
        
        if memory.summary:
            summary = await self._safe_merge(llm, [memory.summary, summary])

        
        
        
        
        
        
        
        
        
        
        
        
        
        
        memory.set_summary(summary, end)
        logger.info(
            "上下文已压缩：%s 条消息 -> 摘要 %s 字（用量占比 %.0f%%）",
            end - start,
            len(summary),
            self.usage_ratio(memory, token_limit) * 100,
        )
        return True

    async def _summarize(
        self,
        llm: BaseLLM,
        messages: list[Message],
        *,
        token_limit: int,
    ) -> str:
        budget = min(self.policy.summarize_budget_tokens, max(token_limit // 2, 1000))
        partials: list[str] = []
        for batch in self._batch(messages, budget):
            transcript = render_transcript(batch)
            if not transcript.strip():
                continue
            text = await self._call(llm, _SUMMARIZE_SYSTEM, transcript)
            if text:
                partials.append(text)

        if not partials:
            return ""
        if len(partials) == 1:
            return partials[0]
        return await self._safe_merge(llm, partials)

    async def _safe_merge(self, llm: BaseLLM, partials: list[str]) -> str:

        try:
            merged = await self._call(llm, _MERGE_SYSTEM, "\n\n---\n\n".join(partials))
            return merged or "\n".join(partials)
        except Exception as exc:  
            logger.warning("摘要合并失败，改为直接拼接: %s", exc)
            return "\n".join(partials)

    @staticmethod
    async def _call(llm: BaseLLM, system: str, payload: str) -> str:
        response = await llm.chat(
            [
                Message(role="system", content=system),
                Message(role="user", content=payload),
            ],
            None,
            
            temperature=0.2,
        )
        return (response.content or "").strip()

    def _batch(self, messages: list[Message], budget: int) -> list[list[Message]]:






        batches: list[list[Message]] = []
        current: list[Message] = []
        used = 0

        for message in messages:
            size = MemoryManager._estimate_tokens([message])
            if current and used + size > budget:
                
                
                
                
                carry: list[Message] = []
                while (
                    len(current) > 1
                    and current[-1].role == "assistant"
                    and current[-1].tool_calls
                ):
                    carry.insert(0, current.pop())
                batches.append(current)
                current = carry
                used = sum(MemoryManager._estimate_tokens([m]) for m in current)
            current.append(message)
            used += size

        if current:
            batches.append(current)
        return batches
