"""上下文超限的自愈：**先摘要压缩，压不动才裁剪**。

对应《智能体框架开发文档》4.6 节的「超限 → 截断 → 重试」链路。这个模块是
``ContextOverflowError`` 唯一的产生与消化地点 —— 在此之前它虽然定义了，
但从未被 raise 过，也就是那条链路其实不存在。

## 为什么压缩优先于裁剪

裁剪（``MemoryManager._trim``）会把最旧的消息**整条丢掉**。对长任务来说，
丢掉的往往正是用户一开始的约定：文件路径、口径、已经排除掉的方案。
结果是模型在第 30 轮突然开始"失忆"，反复问已经答过的问题、用错文件名 ——
用户会觉得模型变笨了，而不是"上下文满了"。

摘要保住了这些约定的要点，同时把消息条数大幅降下来。

## 成本控制（三条硬约束）

摘要本身要花一次 LLM 调用，不当心会把长对话成本翻倍。所以：

1. **只在超限时压，且一个会话同一段历史只压一次** —— 靠 ``_summary_upto``
   记住已经覆盖到哪，已进过摘要的内容不会重复压；
2. **用量没到阈值就不压** —— 提前压等于白花钱（``compress_threshold``）；
3. **压失败就回落到裁剪** —— 绝不因为压缩失败而让整轮对话失败。

## 一个容易忽略的坑

超限时，"拿去摘要的那批消息"加起来**同样可能超限**，直接丢给模型会立刻
再撞一次 400。所以这里做的是分批 map-reduce：先按预算切成若干批各自摘要，
再用一次调用把多段摘要合并。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..errors import ContextOverflowError, LLMError
from ..llm.base import BaseLLM, Message
from ..memory.short_term import MemoryManager
from ..utils.timefmt import format_message_time

logger = logging.getLogger(__name__)

# 厂商上报上下文超限时的措辞。各家完全不一致，而且不会告诉你"这就是超限"，
# 只会丢一句自然语言。宁可比对宽松一点，也不要漏判成普通 400。
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
    """判断一句厂商错误信息是不是"上下文超限"。

    只做纯文本判断，不做异常类型判断 —— 因为厂商是用 400 返回这句话的，
    在我们的异常体系里它就是一个普通的 ``LLMError``。
    """
    lowered = message.lower()
    return any(hint in lowered for hint in _OVERFLOW_HINTS)


@dataclass
class ContextPolicy:
    """上下文策略参数。"""

    # 给模型回复预留的空间（token）。算得很紧会导致"输入刚好卡满、
    # 输出一个字都放不下"，表现为模型返回空内容
    reserve_tokens: int = 1024
    # 最近多少条消息不参与压缩：它们是"当前正在做什么"的直接上下文
    keep_recent: int = 6
    # 用量超过该比例就开始压缩（提前压比撞到上限再压更稳，也不容易触发厂商的硬限制）
    compress_threshold: float = 0.8
    # 摘要长度**目标**（字符）。
    #
    # ⚠️ 它不再是"硬砍到这么多"：见 ``compress()`` 里为什么去掉那个切片。
    # 保留这个字段是为了给"摘要该多长"一个可调的预期（以及给测试与诊断一个参照），
    # 但它不再会让任何内容被无声丢掉。
    max_summary_chars: int = 2400
    # 单次摘要请求可用的 token 预算
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
    """把消息渲染成给压缩器看的纯文本。

    工具调用也要带上：模型"查过什么、拿到什么"往往比自己说的话更重要
    （例如查到的文件路径、报错原因）。

    **每条带时间前缀**：摘要要保留时间维度，压缩器才有素材把"昨天"换算成绝对日期
    （见 `_SUMMARIZE_SYSTEM` 第 4 条）。没有时间的话，一段三个月前的摘要在新对话里
    读起来就像刚发生的事 —— 那正是用户说的"别把旧的当当下聊"。
    """
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
            # system 不参与压缩（它在上下文里始终保留），跳过以免摘要变成
            # 一份提示词的复述
            continue
        lines.append(f"{stamp}[用户] {message.content}")
    return "\n".join(lines)


class ContextGuard:
    """上下文用量的检查、摘要压缩与回溯。"""

    def __init__(self, policy: ContextPolicy | None = None) -> None:
        self.policy = policy or ContextPolicy()

    # ------------------------------------------------------------------ #
    # 用量
    # ------------------------------------------------------------------ #
    def usage_ratio(self, memory: MemoryManager, token_limit: int) -> float:
        """当前上下文占用模型窗口的比例（0~1+）。"""
        if token_limit <= 0:
            return 0.0
        return memory.context_tokens() / token_limit

    def should_compress(self, memory: MemoryManager, token_limit: int) -> bool:
        """是否值得现在就压缩一次。"""
        if token_limit <= 0:
            return False
        if self.usage_ratio(memory, token_limit) < self.policy.compress_threshold:
            return False
        start, end = memory.compressible_range(keep_recent=self.policy.keep_recent)
        return end > start

    def check(self, memory: MemoryManager, token_limit: int) -> None:
        """超限就抛 ``ContextOverflowError``。

        ``MemoryManager`` 自己会裁剪到配置的上限，所以这里真正拦下来的是
        "配置上限大于模型真实窗口"造成的错配 —— 那种情况下不报错的话，
        请求会被厂商用一个和上下文无关的错误信息拒掉。
        """
        budget = token_limit - self.policy.reserve_tokens
        if budget <= 0:
            return
        used = memory.context_tokens()
        if used > budget:
            raise ContextOverflowError(
                f"上下文用量 {used} token 已超过模型可用窗口 {budget} token，正在压缩历史。",
                detail={"used": used, "budget": budget},
            )

    # ------------------------------------------------------------------ #
    # 压缩
    # ------------------------------------------------------------------ #
    async def compress(
        self,
        llm: BaseLLM,
        memory: MemoryManager,
        *,
        token_limit: int,
    ) -> bool:
        """把待丢弃的早期消息压缩成摘要并写入记忆。成功返回 True。

        **失败一律返回 False 而不是抛异常**：压缩是优化手段，不是必需品，
        它失败时调用方会回落到原有的裁剪逻辑，对话照样能继续。
        """
        start, end = memory.compressible_range(keep_recent=self.policy.keep_recent)
        if end <= start:
            return False

        target = memory.messages[start:end]
        try:
            summary = await self._summarize(llm, target, token_limit=token_limit)
        except LLMError as exc:
            logger.warning("上下文压缩失败，回落到裁剪: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 - 压缩不该让对话失败
            logger.warning("上下文压缩出现意外错误，回落到裁剪: %s", exc)
            return False

        if not summary:
            return False

        # 和已有摘要合并：否则第二次压缩会把第一次的成果覆盖掉，
        # 前面几十轮的约定就白保了
        if memory.summary:
            summary = await self._safe_merge(llm, [memory.summary, summary])

        # ⚠️ **不再对摘要做截断**（这里以前是 ``summary[:max_summary_chars]``）。
        #
        # 为什么去掉：摘要被砍掉尾巴时，丢的往往是**最近发生的事** —— 而"刚才在
        # 做什么"恰恰是模型最需要的上下文。而且这种砍法是无声的：模型看到的是一段
        # 读起来完整的摘要，于是它以为自己掌握了全部。
        #
        # 长度控制交给两处更合适的地方：
        # 1. 摘要提示词本身就要求"条目式、尽量紧凑"；
        # 2. 摘要过长的后果只是"下一次压缩来得更早"，那是一次正常的、可见的再压缩，
        #    而不是把内容丢掉。
        #
        # 另外要分清：这里压缩的是**派生出来的摘要**，原始对话一条都没少
        # （``_messages`` 始终完整，用户随时能看到），而且发给模型的摘要消息里
        # 已经写明"更早的完整记录仍在、需要细节就直接问"。
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
        """合并多段摘要；合并失败就退化成直接拼接（信息不丢，只是不够紧凑）。"""
        try:
            merged = await self._call(llm, _MERGE_SYSTEM, "\n\n---\n\n".join(partials))
            return merged or "\n".join(partials)
        except Exception as exc:  # noqa: BLE001
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
            # 压缩要的是稳定复现，不是创造力
            temperature=0.2,
        )
        return (response.content or "").strip()

    def _batch(self, messages: list[Message], budget: int) -> list[list[Message]]:
        """按 token 预算把消息切成若干批。

        切点必须避开 ``assistant(tool_calls)`` 与 ``tool`` 之间：
        把一次工具调用和它的结果拆到两批里，摘要会看到"调了工具但没有结果"，
        从而写出"某工具执行结果未知"这种没用的记录。
        """
        batches: list[list[Message]] = []
        current: list[Message] = []
        used = 0

        for message in messages:
            size = MemoryManager._estimate_tokens([message])
            if current and used + size > budget:
                # 回退到安全切点：若 current 的最后一条是「声明了工具调用的
                # assistant」，那它后面紧跟着的就是这批调用的结果。在这里切会把
                # 两者拆到不同批次，摘要只能看到"调了工具但没有结果"。
                # 于是把它一起挪到下一批（连同结果）。
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
