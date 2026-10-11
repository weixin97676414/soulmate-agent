"""让用户做选择：AI 不确定用户意图时，把自己的几种理解摆出来让用户点一个。

## 为什么需要它（而不是让模型直接开口问）

模型遇到模糊需求有几条路，都有毛病：

- **猜**：猜错了整轮白做，用户还得从头纠正；
- **在正文里问**：用户得打字回答，而且模型常常"问完就自己往下做了" ——
  它没法真的**停下来**；
- **`grill_me`（苏格拉底式追问）**：那是一段提示词，让模型在**下一轮**追问，
  同样停不下来，也无法保证用户真的回答。

这个技能把"问"变成一个**有返回值**的动作：调用它，整轮任务就停在这里，
直到用户在弹窗里点一个选项（或不选、关掉）。模型拿到明确答复再继续。

## 产品约定

1. **允许自定义输入**：AI 没想到的第 N+1 种，用户能自己写；
2. **可取消**：关掉弹窗 = "你的理解都不对，重新想"；
3. **不超时**：问了就一直等 —— 用户可能刚离开电脑。

## ⚠️ `timeout=86400` 不是业务超时

技能内挂起**会**被 ``manager._run_with_timeout`` 的 ``asyncio.wait_for`` 掐掉
（默认 30 秒）。24 小时只是"兜底别让它永远占着"（见 ``SkillContext.ask_interaction``
的说明，以及实证脚本 ``core/_chk_timeout.py``）。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ...security.interaction import KIND_CHOICE, InteractionRequest
from ..base import BaseSkill, SkillContext
from ..decorator import skill


class _Option(BaseModel):
    """一个候选理解。"""

    label: str = Field(..., description="选项文字，一句话说清这种理解是什么（尽量短，用户要一眼扫过）")
    description: str = Field("", description="可选的补充说明，帮用户区分相近的选项")


class _Input(BaseModel):
    question: str = Field(
        ...,
        description=(
            "要问用户的问题。写成「我不确定的是哪个点」，而不是「你要什么」—— "
            "用户看到的标题就是它，含糊的话他只能反问回来。"
        ),
    )
    options: list[_Option] = Field(
        ...,
        min_length=2,
        max_length=6,
        description=(
            "2 到 6 个候选理解。每项是**你对用户意图的一种猜测**（不是让用户做选择题选项）—— "
            "用户点一个就等于告诉你「对，我就是要这个」。"
        ),
    )
    allow_custom: bool = Field(
        True,
        description="是否允许用户自己输入第 N+1 种（默认允许）。只有在你已穷尽可能性时才关掉。",
    )


@skill(
    name="ask_choice",
    display_name="请你确认一下",
    description=(
        "当你**不太确定用户到底想要什么**时用它：把你理解的几种可能摆出来，弹窗让用户点一个。"
        "适用于需求含糊、一个词有多种解释、或你的方案有几种合理走向而用户没说清偏好的场合。"
        "用户除了选项还能自己填一个，也可以关掉弹窗表示「都不对」。"
        "⚠️ 不要用它问「你要不要继续」这种是非题（那是普通对话就能解决的），"
        "也不要用它代替你本该自己去查的事实。"
    ),
    params_model=_Input,
    category="general",
    permission_level="safe",
    # 见模块顶部说明：24 小时只是兜底，真正等多久由用户决定。
    timeout=86400,
    tags=["交互", "澄清", "意图"],
)
class AskChoiceSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)

        request = InteractionRequest(
            request_id=uuid4().hex,
            skill_name="ask_choice",
            display_name="请你确认一下",
            kind=KIND_CHOICE,
            payload={
                "question": args.question,
                "options": [
                    {"label": item.label, "description": item.description} for item in args.options
                ],
                "allow_custom": args.allow_custom,
            },
            prompt=args.question,
        )
        answer = await ctx.ask_interaction(request)

        return {"ok": True, "result": _describe(answer)}


def _describe(answer: dict[str, Any]) -> str:
    """把用户的答复整理成**给模型看的一句话**。

    ⚠️ 这里返回的字符串会作为工具结果回填给模型，**也会进消息表与上下文** ——
    所以它只该包含用户的选择本身，不该包含任何我们自己的推测
    （"用户可能还想..."这种）。模型需要知道的是**用户说了什么**，不是我们怎么理解。
    """
    if answer.get("cancelled"):
        if answer.get("interrupted"):
            return "用户没有作答（这次任务被停止或会话被关闭了）。如需继续，请重新问一次。"
        if answer.get("reason") == "no_channel":
            return (
                "当前环境没有可用的选择弹窗（例如定时任务里没人能作答）。"
                "请**按你最可能的那种理解往下做**，并在回复里说明这是你的假设、"
                "以及如果理解错了该怎么纠正。"
            )
        return (
            "用户关掉了弹窗，表示你列的那几种理解**都不对**。"
            "请不要在原来的选项里硬挑一个，而是重新理解他的需求；"
            "如果仍然拿不准，可以直接问他。"
        )

    custom = str(answer.get("custom") or "").strip()
    if custom:
        return f"用户没有选你给的选项，而是自己补充了：{custom}"

    chosen = str(answer.get("value") or "").strip()
    if not chosen:
        # 理论上不该发生（前端保证要么给 value 要么给 custom 要么 cancelled）。
        # 如实说明而不是编一个选项，否则模型会拿一个不存在的答案往下做。
        return "用户提交了选择，但没有带回具体内容。请再问一次，或直接问他。"
    return f"用户选择了：{chosen}"
