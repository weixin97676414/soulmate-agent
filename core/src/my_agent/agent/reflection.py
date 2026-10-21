



















from __future__ import annotations

import logging
from dataclasses import dataclass

from ..llm.base import BaseLLM, Message

logger = logging.getLogger(__name__)



_OK = "OK"
_REVISE = "REVISE"

_REVIEW_SYSTEM = f"""你是回答质量检查员。判断助手给出的回答是否**完整、正确**地满足了用户的要求。

只输出下面两种之一：
- 完全满足：输出 `{_OK}`
- 有问题：输出 `{_REVISE}:` 后接一句话说明缺什么或错在哪

判断标准（从宽）：
- 回答更啰嗦、风格不够好、可以更详细 —— 这些**不算问题**，输出 {_OK}；
- 只有"漏掉了用户明确要求的内容""答的不是用户问的""事实明显错误"才算问题。

不要输出任何其他内容。"""

_MIN_ANSWER_CHARS = 20


@dataclass
class Reflection:


    needs_revision: bool = False
    feedback: str = ""

    @property
    def passed(self) -> bool:
        return not self.needs_revision


class Reflector:


    def __init__(self, *, enabled: bool = False, max_rounds: int = 1) -> None:
        self.enabled = enabled
        self.max_rounds = max(0, max_rounds)

    def should_review(self, answer: str, *, rounds_done: int) -> bool:
        if not self.enabled or rounds_done >= self.max_rounds:
            return False
        
        return len((answer or "").strip()) >= _MIN_ANSWER_CHARS

    async def review(
        self,
        llm: BaseLLM,
        *,
        user_input: str,
        answer: str,
        tool_summary: str = "",
    ) -> Reflection:

        payload = [f"用户的要求：\n{user_input}"]
        if tool_summary:
            payload.append(f"\n已经做过的操作：\n{tool_summary}")
        payload.append(f"\n助手的回答：\n{answer}")

        try:
            response = await llm.chat(
                [
                    Message(role="system", content=_REVIEW_SYSTEM),
                    Message(role="user", content="\n".join(payload)),
                ],
                None,
                temperature=0.0,
            )
        except Exception as exc:  
            logger.warning("回答自检失败，按通过处理: %s", exc)
            return Reflection()

        verdict = (response.content or "").strip()
        if verdict.upper().startswith(_REVISE):
            feedback = verdict[len(_REVISE) :].lstrip("：: ").strip()
            return Reflection(needs_revision=True, feedback=feedback or "请检查是否完整满足要求。")
        return Reflection()


def revision_hint(feedback: str) -> str:

    from ..memory.short_term import internal_hint

    return internal_hint(
        "交付前自检发现问题，请修正后重新给出完整回答（不要解释自检过程）：" + feedback
    )
