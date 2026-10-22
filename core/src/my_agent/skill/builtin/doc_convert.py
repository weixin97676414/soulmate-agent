










from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils.doc_convert import (
    DocConvertError,
    docx_to_markdown,
    html_to_pdf,
    markdown_to_docx,
    markdown_to_html,
    pdf_to_text,
)
from ..base import BaseSkill, SkillContext
from ..decorator import skill

logger = logging.getLogger(__name__)


def _to_skill_error(exc: DocConvertError) -> SkillExecutionError:
    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        
        return path.read_text(encoding="gbk", errors="replace")
    except OSError as exc:
        raise SkillExecutionError(f"文件读不出来：{exc}") from exc


class WordToMarkdownParams(BaseModel):
    path: str = Field(..., description="要转换的 .docx 文件路径")
    output_name: str | None = Field(None, description="输出文件名，留空按原标题生成")


@skill(
    name="doc_word_to_markdown",
    display_name="Word 转 Markdown",
    description=(
        "把一个 Word（.docx）文件转换成 Markdown。当用户说「把这份文档转成 Markdown」"
        "「把这个 word 变成 md 我要发到知识库」时使用。"
        "保留标题层级、列表、表格与加粗斜体；图片、批注、页眉页脚不会保留。"
    ),
    params_model=WordToMarkdownParams,
    category="office",
    permission_level="confirm",
    tags=["文档转换", "Word", "Markdown"],
)
class WordToMarkdownSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = WordToMarkdownParams(**params)
        source = ctx.resolve_input_file(args.path)
        try:
            markdown = docx_to_markdown(source)
        except DocConvertError as exc:
            raise _to_skill_error(exc) from exc

        target = ctx.artifact_output(args.output_name or f"{source.stem}.md")
        if target.suffix.lower() not in (".md", ".markdown"):
            target = target.with_suffix(".md")
        target.write_text(markdown, encoding="utf-8")

        artifact = await ctx.register_artifact(target, note="Word 转 Markdown")
        return {
            "file": str(target),
            "filename": target.name,
            "chars": len(markdown),
            "artifact": artifact,
            "content": markdown,
            "message": "已转换完成，Markdown 内容见 content 字段，文件也在产物区。",
        }


class MarkdownToWordParams(BaseModel):
    path: str | None = Field(None, description="要转换的 Markdown 文件路径；与 content 二选一")
    content: str | None = Field(None, description="直接给 Markdown 文本；与 path 二选一")
    title: str = Field("", description="文档标题（会作为一级标题写进 Word）")
    output_name: str | None = Field(None, description="输出文件名，留空自动生成")


@skill(
    name="doc_markdown_to_word",
    display_name="Markdown 转 Word",
    description=(
        "把 Markdown 文本或 .md 文件转成 Word（.docx）文档。"
        "当用户说「把这份 Markdown 导出成 Word」「写成 docx 发给我」时使用。"
        "标题、列表、表格、加粗斜体、代码块都会正常排版。"
    ),
    params_model=MarkdownToWordParams,
    category="office",
    permission_level="confirm",
    tags=["文档转换", "Markdown", "Word"],
)
class MarkdownToWordSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = MarkdownToWordParams(**params)
        if (args.path is None) == (args.content is None):
            raise SkillExecutionError("请提供 path（.md 文件）或 content（Markdown 文本）中的一个。")

        if args.path is not None:
            source = ctx.resolve_input_file(args.path)
            markdown = _read_text(source)
            default_name = f"{source.stem}.docx"
        else:
            markdown = args.content or ""
            default_name = "文档.docx"

        target = ctx.artifact_output(args.output_name or default_name)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        try:
            markdown_to_docx(markdown, target, title=args.title)
        except DocConvertError as exc:
            raise _to_skill_error(exc) from exc

        artifact = await ctx.register_artifact(target, note="Markdown 转 Word")
        return {
            "file": str(target),
            "filename": target.name,
            "artifact": artifact,
            "message": "Word 文档已生成，可在右侧产物区打开。",
        }


class ToPdfParams(BaseModel):
    path: str | None = Field(None, description="要转换的 .md / .markdown / .docx 文件路径")
    content: str | None = Field(None, description="直接给 Markdown 文本（与 path 二选一）")
    title: str = Field("", description="文档标题")
    output_name: str | None = Field(None, description="输出文件名，留空自动生成")


@skill(
    name="doc_to_pdf",
    display_name="转成 PDF",
    description=(
        "把 Markdown 或 Word 转成 PDF。当用户说「导出成 PDF」「生成一份 PDF 给他」时使用。"
        "内置离线渲染，**不要求本机安装 Office**，中文正常显示。"
    ),
    params_model=ToPdfParams,
    category="office",
    permission_level="confirm",
    tags=["文档转换", "PDF"],
)
class ToPdfSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ToPdfParams(**params)
        if args.path is None and args.content is None:
            raise SkillExecutionError("请提供 path（.md 或 .docx）或 content（Markdown 文本）。")

        source: Path | None = None
        if args.path is not None:
            source = ctx.resolve_input_file(args.path)
            suffix = source.suffix.lower()
            if suffix == ".docx":
                try:
                    markdown = docx_to_markdown(source)
                except DocConvertError as exc:
                    raise _to_skill_error(exc) from exc
            elif suffix in (".md", ".markdown", ".txt"):
                markdown = _read_text(source)
            else:
                raise SkillExecutionError(f"不支持的文件类型：{suffix}，请给 Markdown 或 .docx。")
            default_name = f"{source.stem}.pdf"
        else:
            markdown = args.content or ""
            default_name = "文档.pdf"

        target = ctx.artifact_output(args.output_name or default_name)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")

        html = markdown_to_html(markdown, title=args.title)
        try:
            await html_to_pdf(html, target)
        except DocConvertError as exc:
            raise _to_skill_error(exc) from exc

        artifact = await ctx.register_artifact(target, note="转成 PDF")
        return {
            "file": str(target),
            "filename": target.name,
            "size": target.stat().st_size if target.exists() else 0,
            "artifact": artifact,
            "message": "PDF 已生成，可在右侧产物区打开。",
        }


class PdfToTextParams(BaseModel):
    path: str = Field(..., description="要抽取文字的 PDF 路径")
    output_name: str | None = Field(None, description="同时存成 .md 时的文件名")


@skill(
    name="doc_pdf_to_text",
    display_name="PDF 转文字",
    description=(
        "从 PDF 里抽取文字内容，并可同时保存成 Markdown 文件。"
        "当用户说「把这个 PDF 里的内容读出来」「PDF 转成文字」时使用。"
        "**不还原排版**：图片、表格线、分栏位置都不会保留，只按页面顺序取出文字。"
    ),
    params_model=PdfToTextParams,
    category="office",
    permission_level="safe",
    tags=["文档转换", "PDF"],
)
class PdfToTextSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = PdfToTextParams(**params)
        source = ctx.resolve_input_file(args.path)
        try:
            text = pdf_to_text(source)
        except DocConvertError as exc:
            raise _to_skill_error(exc) from exc

        payload: dict[str, Any] = {
            "file": str(source),
            "chars": len(text),
            "text": text,
        }
        if args.output_name:
            target = ctx.artifact_output(args.output_name)
            if target.suffix.lower() not in (".md", ".txt"):
                target = target.with_suffix(".md")
            target.write_text(text, encoding="utf-8")
            payload["artifact"] = await ctx.register_artifact(target, note="PDF 转文字")
            payload["saved_to"] = str(target)

        if not text.strip():
            payload["message"] = (
                "这个 PDF 里没有可抽取的文字 —— 它可能是扫描件（整页都是图片）。"
                "这种情况需要先做 OCR，当前工具做不到。"
            )
        return payload
