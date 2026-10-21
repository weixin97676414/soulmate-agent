





from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill
from ....utils.chart import DEFAULT_HEIGHT, DEFAULT_WIDTH, render_chart


class ChartSeries(BaseModel):
    name: str = Field("", description="系列名称，会显示在图例中")
    values: list[float] = Field(..., description="与 categories 一一对应的数值列表")


class ChartGenerateParams(BaseModel):
    chart_type: Literal["bar", "line", "pie"] = Field(
        "bar", description="图表类型：bar 柱状图 / line 折线图 / pie 饼图"
    )
    title: str = Field(..., description="图表标题")
    categories: list[str] = Field(..., description="分类标签，如月份、部门名")
    series: list[ChartSeries] = Field(
        ...,
        description=(
            "数据系列。柱状图/折线图可传多个系列做对比；"
            "饼图只用第一个系列（饼图表达的就是一个维度的占比）"
        ),
    )
    output_name: str = Field("chart.svg", description="输出文件名")
    width: int = Field(DEFAULT_WIDTH, ge=320, le=2000, description="画布宽度（像素）")
    height: int = Field(DEFAULT_HEIGHT, ge=240, le=1600, description="画布高度（像素）")


@skill(
    name="chart_generate",
    display_name="生成图表",
    description=(
        "把数据渲染成图表文件（柱状图 / 折线图 / 饼图），保存为 SVG 并归档到产物目录。"
        "当用户要求「把数据做成柱状图」「画个趋势图」「用饼图看占比」时使用。"
        "数据需要你自行整理好：categories 是分类标签，series 是数值列表且长度必须与 categories 一致。"
        "典型用法是先用 excel_analyze 得到聚合结果，再把结果喂给本工具画图。"
    ),
    params_model=ChartGenerateParams,
    category="office",
    permission_level="safe",
    tags=["图表", "可视化"],
)
class ChartGenerateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ChartGenerateParams(**params)

        if not args.categories:
            raise SkillExecutionError("categories 不能为空。")
        if not args.series:
            raise SkillExecutionError("series 不能为空。")

        for item in args.series:
            if len(item.values) != len(args.categories):
                raise SkillExecutionError(
                    f"系列「{item.name or '(未命名)'}」有 {len(item.values)} 个数值，"
                    f"但 categories 有 {len(args.categories)} 个标签，两者必须一一对应。"
                )

        svg = render_chart(
            args.chart_type,
            args.title,
            args.categories,
            [{"name": item.name, "values": item.values} for item in args.series],
            width=args.width,
            height=args.height,
        )

        target = ctx.artifact_output(args.output_name)
        if target.suffix.lower() != ".svg":
            target = target.with_suffix(".svg")
        target.write_text(svg, encoding="utf-8")

        artifact = await ctx.register_artifact(target, note=args.title)
        return {
            "file": str(target),
            "filename": target.name,
            "chart_type": args.chart_type,
            "title": args.title,
            "categories": args.categories,
            "series": [{"name": item.name, "values": item.values} for item in args.series],
            "artifact": artifact,
            "hint": "图表已保存为 SVG，用户可在「设置 → 工作区与产物」中预览。",
        }
