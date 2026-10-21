

























from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...storage.files import is_safe_file_id
from ..base import BaseSkill, SkillContext
from ..decorator import skill




MAX_SVG_CHARS = 2_000_000


_SVG_ROOT = re.compile(r"<\s*svg[\s/>]", re.IGNORECASE)



_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?[ \t]*```\s*$", re.DOTALL)


_FORBIDDEN = re.compile(r"<\s*script|javascript\s*:", re.IGNORECASE)


def normalize_svg(raw: str) -> str:

    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    return text


class SvgCreateParams(BaseModel):
    filename: str = Field(
        "design.svg",
        description="产物文件名，例如「封面.svg」。可以写中文；不要带路径。",
    )
    svg: str = Field(
        ...,
        description=(
            "完整的 SVG 文本，从 <svg ...> 到 </svg>。"
            "宽高请写在 svg 标签上（width/height/viewBox），否则预览里会按默认尺寸显示。"
        ),
    )
    title: str = Field("", description="这份产物的说明（可选，会显示在产物列表里）")


@skill(
    name="svg_create",
    display_name="自由创作 SVG",
    description=(
        "把你自己写好的 **SVG 文本**保存成产物文件（用户能在右侧产物区看到图）。"
        "用于**自由设计**的图形：封面、海报、示意图、图标、版式、带渐变/光效/网格的插画。"
        "\n\n与「生成图表」的区别：需要**统计图表**（柱状/折线/饼图，数据进图形出）时用 chart_generate；"
        "需要**按你的设计画东西**时用本工具。"
        "\n\n写 SVG 的要点：根元素用自己的 <svg>，并在上面写 width/height/viewBox；"
        "自检一遍闭合标签是否齐全。**不要在 SVG 里写 <script>** —— "
        "预览是把 SVG 当图片渲染的，脚本不会执行，写了只会让图缺一块。"
    ),
    params_model=SvgCreateParams,
    category="office",
    permission_level="safe",
    tags=["图形", "SVG", "设计"],
)
class SvgCreateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = SvgCreateParams(**params)
        svg = normalize_svg(args.svg)

        if not svg:
            raise SkillExecutionError("svg 是空的。请把完整的 SVG 文本放进来。")
        if len(svg) > MAX_SVG_CHARS:
            raise SkillExecutionError(
                f"SVG 文本过长（{len(svg)} 字符，上限 {MAX_SVG_CHARS}）。"
                "请精简后重试；这里不会替你截断 —— 截断后的图会是残缺的。"
            )
        if not _SVG_ROOT.search(svg):
            raise SkillExecutionError(
                "这段内容里没找到 <svg> 根元素，看起来不是 SVG。"
                "请给出从 <svg ...> 到 </svg> 的完整文本（不要只给内部片段）。"
            )
        
        
        
        
        
        
        
        
        if _FORBIDDEN.search(svg):
            raise SkillExecutionError(
                "SVG 里不能包含 <script> 或 javascript: —— 预览是把 SVG 当图片渲染的，"
                "脚本不会执行；请改用纯图形/样式的方式实现同样的效果。"
            )

        filename = Path(args.filename).name.strip() or "design.svg"
        if not filename.lower().endswith(".svg"):
            filename = f"{filename}.svg"
        
        
        
        
        if not is_safe_file_id(filename):
            raise SkillExecutionError(
                f"文件名「{filename}」不可用：不能含 < > : \" / \\ | ? * 或路径分隔符，"
                "不能以点或空格开头结尾，也不能含 ..（中文是允许的）。请换一个名字。"
            )

        target = ctx.artifact_output(filename)
        target.write_text(svg, encoding="utf-8")

        artifact = await ctx.register_artifact(target, note=args.title or "SVG 设计图")
        return {
            "file": str(target),
            "filename": target.name,
            "chars": len(svg),
            "artifact": artifact,
            "hint": "SVG 已保存，用户可在右侧产物区预览（也可用「另存为」导出）。",
        }
