"""自我成长：把踩坑 / 被纠正 / 新认知沉淀为可复用常识。

来源是用户桌面「通用skills/self-growth」。每个搭子必装（见 orchestrator.create_assistant）。
纯提示词技能：run 返回几条硬规则，让模型在"失败 / 被纠正 / 学到更优做法"时
**先记录再继续**，而不是重复踩同一个坑。记录落到搭子自己的 MEMORY.md
（配合 self_persona_update 追加，见 self_persona.py —— 两条技能一起，人格记忆
与经验教训就都有了，互不打架）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSkill, SkillContext
from ..decorator import skill

_RULES = """# 自我成长规则

把踩坑 / 被纠正 / 新认知沉淀为可复用常识；做大事前先回顾相关部分。

## 触发
命令失败、被用户纠正、发现缺能力、外部工具失败、学到更优做法、知识过时。

## 记录什么（落到自己的 MEMORY.md，用 self_persona_update 追加，带日期）
- 踩坑：错在哪 / 为什么 / 怎么避免；
- 被纠正：用户的原话 / 我的偏差 / 正确认知；
- 验证过的做法、补充的知识盲区。

## 四条硬规则
1. **模糊词警报**：发现自己要写"可能 / 大概 / 应该是 / 我记得" → 停，先去查。查得到就查，查不到就直说查不到；不许把模糊词当结论交出去。
2. **不确定必须分级**：L1 缺细节（事知道、缺一个具体值）→ 立即查；L2 缺来源（结论记不清出处）→ 立即核；L3 完全不懂 → 直说"这个我不懂，需要先研究"。笼统的"不确定"不算交代，分级才算。
3. **一次纠正 = 永久防御**：被纠正一次就落盘，不等第二次。落盘必含：触发场景 + 我的偏差 + 正确口径；下次遇到同场景先读它。
4. **交付后不撒手**：重要任务记状态（任务 / 当前状态 / 最后更新 / 对方态度 / 下一步）；交付未获回音不等于结束，纳入下次回顾。

## 记录规则
简洁具体、用自己的话、不记敏感内容、每条带日期。
"""


class GrowthParams(BaseModel):
    note: str = Field("", description="这次要沉淀的经验/教训（留空则返回通用规则供自我检查）")


@skill(
    name="self_growth",
    display_name="自我成长（记录踩坑与纠正）",
    description=(
        "在**命令失败 / 被用户纠正 / 发现能力缺失 / 学到更优做法 / 知识过时**时，"
        "把这次的经验教训沉淀下来（记到自己的 MEMORY.md），避免下次重踩同一个坑。"
        "做重要的事之前，也可以先调它回顾一下有没有相关的前车之鉴。"
    ),
    params_model=GrowthParams,
    category="persona",
    permission_level="safe",
    tags=["成长", "记忆", "复盘"],
)
class SelfGrowthSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GrowthParams(**params)
        return {
            "ok": True,
            "note": args.note,
            "rules": _RULES,
            "hint": (
                "按上面的规则把经验写下来，然后用 self_persona_update 追加到自己的 MEMORY.md"
                "（带日期）。这次只返回规则，不替你做任何写操作。"
            ),
        }
