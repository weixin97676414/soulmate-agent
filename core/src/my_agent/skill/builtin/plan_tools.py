




















from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..base import BaseSkill, SkillContext
from ..decorator import skill


class PlanUpdateParams(BaseModel):
    step: str = Field(
        ...,
        min_length=1,
        description='要更新的步号，取自本轮计划里的编号（字符串形式，如 "2"）。',
    )
    
    
    status: Literal["doing", "done", "failed"] = Field(
        ...,
        description="这一步的状态：doing=开始做、done=做完了、failed=做不成（出错或放弃）。",
    )
    note: str = Field(
        "",
        description="补充说明：失败 / 跳过的原因，或这一步的关键结论（可选，会显示在卡片上）。",
    )


@skill(
    name="plan_update",
    display_name="汇报计划进度",
    description=(
        "在**本轮已确认执行计划**的前提下，汇报计划里某一步的进度 —— "
        "开始做某步时标 doing、做完标 done、做不成标 failed，用户会实时看到卡片打勾。"
        "\n\n何时调用：每**开始**或**完成**计划中的一步后立刻调用一次；"
        "某步失败且不打算重试时用 failed，并在 note 里写清原因。"
        "\n\n输入：step 是本轮计划里的步号（如 \"1\"、\"2\"），"
        "status 取 doing / done / failed，note 可选（失败原因或关键结论，会显示给用户）。"
        "\n\n注意：**只在有执行计划时才调用**，普通对话（没有计划）不要用它。"
        "步号写错不会生效，返回会告诉你可用的步号。"
    ),
    params_model=PlanUpdateParams,
    category="system",
    permission_level="safe",
    tags=["计划", "进度"],
)
class PlanUpdateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = PlanUpdateParams(**params)
        
        
        return {
            "ok": True,
            "step": args.step,
            "status": args.status,
            "hint": f"已收到第 {args.step} 步的进度汇报（{args.status}）。",
        }
