"""报告生成技能：把结构化内容渲染成 Markdown 文件并归档为产物。

**为什么不用 jinja2**：默认报告模板是固定的（标题 + 元信息 + 正文 + 目录），
用字符串拼接即可完成，不值得为它引入一个模板引擎依赖。少一个依赖就少一份
打包体积与升级风险。

生成的文件落在 ``artifacts/``，同时登记进工作区，客户端「工作区与产物」
页签里可以直接看到并预览。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill


class ReportSection(BaseModel):
    heading: str = Field(..., description="小节标题")
    content: str = Field("", description="小节正文，支持 Markdown")
    bullets: list[str] = Field(
        default_factory=list, description="要点列表，会渲染成无序列表"
    )


class ReportGenerateParams(BaseModel):
    title: str = Field(..., description="报告标题")
    output_name: str = Field(
        "report.md", description="输出文件名（只取文件名部分，目录固定为产物目录）"
    )
    content: str = Field("", description="报告正文（Markdown）。与 sections 至少提供一个")
    sections: list[ReportSection] = Field(
        default_factory=list, description="结构化小节，会渲染成带标题的章节"
    )
    summary: str = Field("", description="摘要，渲染在标题下方")
    include_toc: bool = Field(False, description="是否生成目录")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="附加元信息，如作者、部门，会渲染成列表"
    )


@skill(
    name="report_generate",
    display_name="生成报告",
    description=(
        "把内容渲染成一份 Markdown 报告文件并保存到产物目录。"
        "当用户要求「生成周报」「把分析结果整理成报告」「输出一份总结文档」时使用。"
        "正文由你撰写并作为 content 传入；也可以用 sections 传入结构化章节。"
        "生成后返回文件路径，可告诉用户在工作区中查看。"
    ),
    params_model=ReportGenerateParams,
    category="office",
    permission_level="safe",
    tags=["报告", "写作"],
)
class ReportGenerateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReportGenerateParams(**params)

        if not args.content.strip() and not args.sections:
            raise SkillExecutionError("content 与 sections 至少要提供一个，否则报告是空的。")

        lines: list[str] = [f"# {args.title}", ""]

        meta_lines: list[str] = [f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}"]
        meta_lines.extend(f"- {key}：{value}" for key, value in args.metadata.items())
        lines.extend(meta_lines)
        lines.append("")

        if args.summary.strip():
            lines.extend(["> " + args.summary.strip().replace("\n", "\n> "), ""])

        if args.include_toc and args.sections:
            lines.append("## 目录")
            lines.append("")
            lines.extend(f"{index}. {section.heading}" for index, section in enumerate(args.sections, 1))
            lines.append("")

        if args.content.strip():
            lines.extend([args.content.strip(), ""])

        for section in args.sections:
            lines.extend([f"## {section.heading}", ""])
            if section.content.strip():
                lines.extend([section.content.strip(), ""])
            if section.bullets:
                lines.extend(f"- {item}" for item in section.bullets)
                lines.append("")

        markdown = "\n".join(lines).rstrip() + "\n"

        target = ctx.artifact_output(args.output_name)
        if target.suffix.lower() not in (".md", ".markdown", ".txt"):
            target = target.with_suffix(".md")
        target.write_text(markdown, encoding="utf-8")

        artifact = await ctx.register_artifact(target, note=args.title)
        return {
            "file": str(target),
            "filename": target.name,
            "title": args.title,
            "sections": len(args.sections),
            "chars": len(markdown),
            "artifact": artifact,
            "hint": "报告已保存到产物目录，用户可在「设置 → 工作区与产物」中查看。",
        }
