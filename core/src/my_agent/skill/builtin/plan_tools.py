"""计划进度回报：让用户看见 AI 到底做到哪一步了。

来源：产品约定 —— 计划要"逐项打勾、看得见进度"，
执行中每完成一步就更新卡片，而不是最后突然说一句"都做完了"。

## 这个技能为什么这么"薄"

它**只收参数、不判断真伪**。真正的裁决在引擎
（``Agent.apply_plan_update``）：技能看不到本轮计划 —— 计划活在引擎状态里，
不在任何技能上下文里。让技能"假装更新成功"是典型的静默失败：模型以为自己
汇报过了，卡片上却什么都没变。

所以这里的返回值只是**兜底**，正常情况下会被引擎替换成
"第 N 步已标记为 done" 这类如实回话。

## 什么时候该出现

只有**本轮有已确认的执行计划**时才该被调用。没有计划的普通对话里调它，
引擎会明确回一句"本轮没有执行计划"（不假装成功），模型下一轮自然会停手。
"""

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
    # 用 Literal 而不是裸字符串：JSON Schema 里会变成 enum，
    # 模型写错值当场就知道，比事后由引擎"归一化"要少一次白跑。
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
        # 真伪由引擎裁决（见模块文档）：这里只把参数原样回执，
        # 引擎会用**真实计划**替换掉这段文字，再决定要不要广播进度事件。
        return {
            "ok": True,
            "step": args.step,
            "status": args.status,
            "hint": f"已收到第 {args.step} 步的进度汇报（{args.status}）。",
        }
