"""Reflection：回答交付前自检一轮。

对应《智能体框架开发文档》7.4 节的反思机制。

## 解决什么

模型最常见的两种失误是**答非所问**和**漏了用户明确要求的点**。
它们在本轮内看不出来（模型自认为答完了），要等用户回一句"你没做 X"。
让它在交付前对着原始要求自查一遍，能拦下相当一部分。

## 代价与默认值

每次自检 = 一次额外的 LLM 调用，直接翻倍响应成本与延迟。所以：

1. **默认关闭**，由用户在设置里开启；
2. 只在**有实质产出**时才自检（空回答、纯寒暄不值得查）；
3. 最多修正 ``max_rounds`` 次，避免"改—查—改"无限循环；
4. 自检调用失败一律当"通过"，绝不因为自检出问题而卡住回答。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..llm.base import BaseLLM, Message

logger = logging.getLogger(__name__)

# 判定标记。刻意要求一个**固定前缀**而不是"让模型回答是否满意"：
# 后者会得到"我认为基本满足要求，但可以更详细"这种无法程序化判断的话。
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
    """一次自检的结果。"""

    needs_revision: bool = False
    feedback: str = ""

    @property
    def passed(self) -> bool:
        return not self.needs_revision


class Reflector:
    """回答交付前的自检。"""

    def __init__(self, *, enabled: bool = False, max_rounds: int = 1) -> None:
        self.enabled = enabled
        self.max_rounds = max(0, max_rounds)

    def should_review(self, answer: str, *, rounds_done: int) -> bool:
        if not self.enabled or rounds_done >= self.max_rounds:
            return False
        # 空回答与只有寒暄的回答不值得花一次调用去查
        return len((answer or "").strip()) >= _MIN_ANSWER_CHARS

    async def review(
        self,
        llm: BaseLLM,
        *,
        user_input: str,
        answer: str,
        tool_summary: str = "",
    ) -> Reflection:
        """自检一轮。任何异常都按"通过"处理。"""
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
        except Exception as exc:  # noqa: BLE001 - 自检是增强，不该阻塞交付
            logger.warning("回答自检失败，按通过处理: %s", exc)
            return Reflection()

        verdict = (response.content or "").strip()
        if verdict.upper().startswith(_REVISE):
            feedback = verdict[len(_REVISE) :].lstrip("：: ").strip()
            return Reflection(needs_revision=True, feedback=feedback or "请检查是否完整满足要求。")
        return Reflection()


def revision_hint(feedback: str) -> str:
    """把自检意见包装成内部提示，注入后让模型重答一次。"""
    from ..memory.short_term import internal_hint

    return internal_hint(
        "交付前自检发现问题，请修正后重新给出完整回答（不要解释自检过程）：" + feedback
    )
