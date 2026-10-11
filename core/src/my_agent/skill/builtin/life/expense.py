"""记账技能：记录一笔支出、统计花销分布。

数据存在本机 SQLite，不上传任何地方。
分类做**自动推断**——用户说话通常是「中午吃饭 35」，不会主动说"分类=餐饮"，
让模型每次都追问分类体验会很差。推断不准时用户可以显式指定 category 覆盖。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill
from ....storage.life import EXPENSE_CATEGORIES


class ExpenseRecordParams(BaseModel):
    amount: float = Field(..., gt=0, description="金额，正数（单位：元）")
    note: str = Field("", description="这笔钱的用途描述，例如「中午吃拉面」「打车去机场」")
    category: str | None = Field(
        None,
        description=(
            "消费分类。留空时会根据 note 自动推断。"
            f"可选值：{'、'.join(EXPENSE_CATEGORIES)}"
        ),
    )
    date: str | None = Field(
        None, description="消费日期，格式 YYYY-MM-DD；留空表示今天。也可传「昨天」「前天」"
    )


@skill(
    name="expense_record",
    display_name="记一笔账",
    description=(
        "记录一笔消费支出。当用户说「中午吃饭花了 35」「打车 20 块」「昨天买了本书 58 元」时使用。"
        "会自动根据用途推断分类；用户明确说了分类时才传 category。"
        "记录完成后返回该笔账的明细，可向用户复述确认。"
    ),
    params_model=ExpenseRecordParams,
    category="life",
    permission_level="safe",
    tags=["记账", "生活"],
)
class ExpenseRecordSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ExpenseRecordParams(**params)
        repository = ctx.service("expenses")

        note = args.note.strip()
        category = (args.category or "").strip() or None

        spent_on: str | None = None
        if args.date:
            spent_on = _resolve_relative_date(args.date)

        record = await repository.add(
            amount=args.amount,
            note=note,
            category=category,
            spent_on=spent_on,
        )

        payload = record.to_dict()
        payload["auto_category"] = category is None
        payload["hint"] = (
            f"已记录：{record.spent_on} {record.category} {record.amount:.2f} 元"
            + (f"（{record.note}）" if record.note else "")
        )
        return payload


def _resolve_relative_date(text: str) -> str:
    from datetime import date, timedelta

    raw = text.strip()
    today = date.today()
    mapping = {
        "今天": 0,
        "今日": 0,
        "昨天": -1,
        "昨日": -1,
        "前天": -2,
        "明天": 1,
    }
    if raw in mapping:
        return (today + timedelta(days=mapping[raw])).isoformat()
    return raw  # 交给仓储层统一规范化（支持 2026/9/17、20260917 等写法）


class ExpenseAnalyzeParams(BaseModel):
    period: str = Field(
        "month",
        description=(
            "统计周期：today 今天 / yesterday 昨天 / week 本周 / lastweek 上周 / "
            "month 本月 / lastmonth 上月 / year 今年 / 30d 最近 30 天 / all 全部"
        ),
    )
    category: str | None = Field(None, description="只看某个分类；留空表示全部分类")
    list_limit: int = Field(20, ge=0, le=200, description="附带返回多少条明细，0 表示不返回")


@skill(
    name="expense_analyze",
    display_name="花销统计",
    description=(
        "统计某个周期的花销：总额、笔数、平均单笔、各分类占比、每日花销趋势，并附带最近的明细。"
        "当用户问「这个月花了多少钱」「钱主要花在哪了」「上周餐饮花了多少」时使用。"
        "返回的 by_category 与 by_day 可以直接作为 chart_generate 的输入画饼图或折线图。"
    ),
    params_model=ExpenseAnalyzeParams,
    category="life",
    permission_level="safe",
    tags=["记账", "统计"],
)
class ExpenseAnalyzeSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ExpenseAnalyzeParams(**params)
        repository = ctx.service("expenses")

        try:
            # 分类过滤必须同时作用于汇总，否则会出现
            # "总额是全部花销、明细却只有交通"的自相矛盾结果
            summary = await repository.summary(period=args.period, category=args.category)
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

        recent: list[dict[str, Any]] = []
        if args.list_limit > 0:
            records = await repository.list(
                period=args.period, category=args.category, limit=args.list_limit
            )
            recent = [record.to_dict() for record in records]

        if summary["count"] == 0:
            span = summary.get("range")
            where = f"{span['start']} ~ {span['end']}" if span else "全部记录"
            return {
                "period": args.period,
                "range": summary.get("range"),
                "total": 0,
                "count": 0,
                "message": f"{where} 没有记账记录。",
            }

        top = summary["by_category"][:5]
        summary["top_categories_text"] = "、".join(
            f"{item['category']} {item['total']:.2f} 元（{item['ratio'] * 100:.0f}%）"
            for item in top
        )
        summary["recent"] = recent
        return summary
