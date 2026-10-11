"""自由创作 SVG：把模型写好的 SVG 文本落成产物并登记。

## 为什么需要它实测反馈缺口）

在此之前，能产出 SVG 的内置技能只有 ``chart_generate`` —— 它只能画标准
柱状图 / 折线图 / 饼图。用户让 AI"照着我桌面那份封面做一个"时，模型的回话是
"我手上能登记产物、又能产出 SVG 的只有 chart_generate，它没法复刻渐变背景、
网格、光效那些设计"。

**缺口不在预览，而在"AI 没有把设计写成文件的手段"** —— 预览链路一直是通的。

## 与 ``chart_generate`` 的分工

这条要写进工具描述，模型才选得对：

- **统计图表**（数据进、图形出）→ ``chart_generate``，标题/图例/配色它自己保证；
- **自由设计**（封面 / 示意图 / 图标 / 版式）→ 本技能，模型自己写完整 SVG。

## 预览不需要改

``storage/preview.py`` 的 SVG 分支与前端 ``ArtifactPreview`` 早就支持它：
预览走 blob URL + ``<img>`` 渲染，**刻意不把 SVG 文本塞进 innerHTML**
（否则一个带 ``<script>`` 的 SVG 就能拿到 preload 暴露的 IPC 桥）。
所以这里只负责"把文本安全地写成文件"，不碰渲染方式。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...storage.files import is_safe_file_id
from ..base import BaseSkill, SkillContext
from ..decorator import skill

# 单份 SVG 文本上限。模型单轮输出远达不到这个量级，这里只是防"某个调用方
# 往这个参数里塞一整本书"把产物目录撑爆；超限**直接报错**而不是静默截断 ——
# 截断过的 SVG 会在预览里显示成一张残缺的图，比报错难查得多。
MAX_SVG_CHARS = 2_000_000

# 只认 `<svg`、`<svg>`、`<svg/>` 这几种开头，用来判断"这确实是一份 SVG"
_SVG_ROOT = re.compile(r"<\s*svg[\s/>]", re.IGNORECASE)

# 围栏：模型经常把内容包在 ```svg / ```xml 里一起交上来。剥掉，
# 否则文件开头是三个反引号，预览直接是一张破图。
_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?[ \t]*```\s*$", re.DOTALL)

# 明确拒绝的两类片段（见下方注释说明为什么只拒这两个）
_FORBIDDEN = re.compile(r"<\s*script|javascript\s*:", re.IGNORECASE)


def normalize_svg(raw: str) -> str:
    """把模型给的文本整理成可落盘的 SVG：剥围栏、去首尾空白。"""
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
        # **只拒这两类**：`<script>` 与 `javascript:`。
        #
        # 为什么不一律"净化"：用户要的是**自由设计**，把模型的设计悄悄改掉
        # 会得到一张它没打算画的图，而模型还以为画好了 —— 那是静默失真。
        # 直接报错，模型自己换一种画法即可。
        #
        # 为什么需要拒：预览虽然走 `<img>`（脚本不执行），但这份文件会被
        # **另存到用户自己的目录**，用户之后完全可能用浏览器打开它。
        if _FORBIDDEN.search(svg):
            raise SkillExecutionError(
                "SVG 里不能包含 <script> 或 javascript: —— 预览是把 SVG 当图片渲染的，"
                "脚本不会执行；请改用纯图形/样式的方式实现同样的效果。"
            )

        filename = Path(args.filename).name.strip() or "design.svg"
        if not filename.lower().endswith(".svg"):
            filename = f"{filename}.svg"
        # 先按**最终要用的文件名**校验一次。`artifact_output` 也会做一次
        # 字符替换，但它不会告诉你"这个名字其实不合格" —— 而 register_artifact
        # 遇到不合格的名字只会记一条 warning 然后静默丢弃登记（产物看得见文件、
        # 却在产物列表里找不到）。宁可在这里明确报错让模型改名。
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
