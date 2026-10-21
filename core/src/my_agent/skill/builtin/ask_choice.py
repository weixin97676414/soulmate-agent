



























from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ...security.interaction import KIND_CHOICE, InteractionRequest
from ..base import BaseSkill, SkillContext
from ..decorator import skill


class _Option(BaseModel):


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
        
        
        return "用户提交了选择，但没有带回具体内容。请再问一次，或直接问他。"
    return f"用户选择了：{chosen}"
