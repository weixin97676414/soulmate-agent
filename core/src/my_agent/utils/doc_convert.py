"""文档转换：Markdown ↔ Word ↔ PDF。

## PDF 为什么走浏览器渲染

项目已经把 Playwright（含 Node 驱动）打进冻结产物，用来做浏览器自动化 ——
而浏览器天生就是一个排版引擎：Markdown → HTML → `page.pdf()` 得到的就是
**离线、中文正常、不要求用户装 Office** 的 PDF。

对比另外两条路：
- `reportlab` / `fpdf2`：得自带一个中文字体并随包分发，还要自己实现分页与
  表格布局，做出来的效果远不如浏览器；
- `weasyprint`：会拖进 GTK/Pango 原生 DLL，在 PyInstaller onedir 下最容易崩、
  体积也最大。

所以这里复用已有的 Playwright，**零新增依赖、零新增体积**。

## 渲染 PDF 用的是独立的无头浏览器

不用浏览器技能那个"带界面的会话"：那样每转一次文档都会在用户屏幕上闪一个
标签页，而且会写进他的浏览记录。这里另起一个无头实例，渲染完就关。

## 转换能力的边界（如实说明，不假装支持）

Word ↔ Markdown 覆盖常用结构：标题、段落、有序/无序列表、表格、加粗斜体、
代码块。**不还原**：图片、批注、页眉页脚、复杂嵌套样式 —— 排版类的东西转换
必然有损，与其做出一个"看起来像但其实错位"的结果，不如让用户知道边界。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)

#: 打印用的最小 CSS：中文字体走系统自带（不随包分发字体文件），
#: 并给表格/代码块一个能看的样子 —— 否则导出的 PDF 是一堆裸文本。
_PRINT_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", "SimSun", "宋体", sans-serif;
  font-size: 11pt; line-height: 1.7; color: #1a1a1a;
}
h1 { font-size: 19pt; margin: 0 0 12px; }
h2 { font-size: 15pt; margin: 20px 0 8px; }
h3 { font-size: 13pt; margin: 16px 0 6px; }
p { margin: 0 0 10px; }
ul, ol { margin: 0 0 10px 1.4em; padding: 0; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 10pt; }
th, td { border: 1px solid #b8b8b8; padding: 5px 8px; text-align: left; }
th { background: #f2f2f2; }
code {
  font-family: Consolas, "Courier New", monospace; font-size: 10pt;
  background: #f5f5f5; padding: 1px 4px; border-radius: 3px;
}
pre { background: #f7f7f7; border: 1px solid #e5e5e5; padding: 10px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { margin: 10px 0; padding: 4px 12px; border-left: 3px solid #cfcfcf; color: #555; }
"""


def _markdown_parser() -> MarkdownIt:
    # 表格不在 commonmark 预设里，但 markdown-it 有这个规则，显式打开即可
    return MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def markdown_to_html(markdown_text: str, *, title: str = "") -> str:
    """Markdown → 完整的 HTML 文档（带打印样式）。"""
    body = _markdown_parser().render(markdown_text or "")
    heading = f"<title>{_escape(title)}</title>" if title else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"{heading}<style>{_PRINT_CSS}</style></head><body>{body}</body></html>"
    )


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


async def html_to_pdf(html: str, target: Path, *, timeout_ms: int = 60_000) -> None:
    """用系统浏览器把 HTML 渲染成 PDF。

    无头 + 独立实例：不打扰用户正在用的浏览器，也不会在他的会话里留下标签页。
    """
    from playwright.async_api import async_playwright

    from ..browser.session import _apply_frozen_shim, _detect_channel

    _apply_frozen_shim()
    channel = _detect_channel()
    if channel is None:
        raise DocConvertError(
            "没检测到系统里的 Edge 或 Chrome，无法生成 PDF。"
            "可以先把它转成 Word，或用其它工具导出。"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=channel, headless=True)
        try:
            page = await browser.new_page()
            # wait_until="load"：保证样式与字体都已就位，否则可能导出空白页
            await page.set_content(html, wait_until="load", timeout=timeout_ms)
            await page.pdf(
                path=str(target),
                format="A4",
                print_background=True,
                margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
            )
        finally:
            await browser.close()


class DocConvertError(Exception):
    """转换失败（缺依赖、文件损坏、格式不支持）。"""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


# --------------------------------------------------------------------------- #
# Markdown → Word
# --------------------------------------------------------------------------- #
def markdown_to_docx(markdown_text: str, target: Path, *, title: str = "") -> None:
    """Markdown → .docx（标题/段落/列表/表格/加粗斜体/代码块）。"""
    docx = _require("docx")
    document = docx.Document()

    if title:
        document.add_heading(title, level=0)

    tokens = _markdown_parser().parse(markdown_text or "")
    list_stack: list[str] = []
    # 列表项的样式要在**它内部的段落**上加，而不是在 list_item_open 上 ——
    # 那时后面跟的是 paragraph_open，inline 内容还没到，直接取会拿到空文本
    # （这个坑的表现是"列表整段消失"，而其它结构都正常）。
    pending_list_style: str | None = None

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open":
            level = int(token.tag[1:]) if token.tag[1:].isdigit() else 1
            inline = tokens[index + 1]
            document.add_heading(_plain(inline.content), level=min(level, 4))
            index += 3
            continue
        if token.type == "paragraph_open":
            inline = tokens[index + 1]
            paragraph = (
                document.add_paragraph(style=pending_list_style)
                if pending_list_style
                else document.add_paragraph()
            )
            pending_list_style = None
            _add_runs(paragraph, inline)
            index += 3
            continue
        if token.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append("bullet" if token.type.startswith("bullet") else "number")
            index += 1
            continue
        if token.type in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
            pending_list_style = None
            index += 1
            continue
        if token.type == "list_item_open":
            pending_list_style = (
                "List Number" if list_stack and list_stack[-1] == "number" else "List Bullet"
            )
            index += 1
            continue
        if token.type in ("fence", "code_block"):
            paragraph = document.add_paragraph()
            run = paragraph.add_run(token.content.rstrip("\n"))
            run.font.name = "Consolas"
            index += 1
            continue
        if token.type == "table_open":
            index = _append_table(document, tokens, index)
            continue
        index += 1

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))


def _append_table(document: Any, tokens: list[Any], index: int) -> int:
    """把 markdown-it 的表格 token 折成 docx 表格；返回下一个待处理的下标。"""
    rows: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    header_rows = 0
    while index < len(tokens) and tokens[index].type != "table_close":
        token = tokens[index]
        if token.type == "tr_open":
            current = []
        elif token.type == "inline":
            bold = bool(token.children) and any(
                child.type == "strong_open" for child in (token.children or [])
            )
            current.append((_plain(token.content), bold))
        elif token.type == "tr_close":
            rows.append(current)
            current = []
        elif token.type == "thead_close":
            header_rows = len(rows)
        index += 1

    if not rows:
        return index + 1

    width = max(len(row) for row in rows)
    table = document.add_table(rows=0, cols=width)
    table.style = "Table Grid"
    for row in rows:
        cells = table.add_row().cells
        for column in range(width):
            text, bold = row[column] if column < len(row) else ("", False)
            cells[column].text = text
            if bold:
                for paragraph in cells[column].paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
    del header_rows  # 表头加粗由 strong 语法决定，样式上不再另做处理
    return index + 1


def _plain(text: str) -> str:
    """去掉行内标记，留纯文本（供标题/单元格用）。"""
    return (text or "").replace("*", "").replace("`", "").strip()


def _add_runs(paragraph: Any, inline: Any) -> None:
    """按行内 token 生成 runs，保留加粗/斜体/行内代码。"""
    children = getattr(inline, "children", None) or []
    if not children:
        paragraph.add_run(_plain(inline.content))
        return

    bold = italic = False
    for child in children:
        if child.type == "strong_open":
            bold = True
        elif child.type == "strong_close":
            bold = False
        elif child.type == "em_open":
            italic = True
        elif child.type == "em_close":
            italic = False
        elif child.type == "code_inline":
            run = paragraph.add_run(child.content)
            run.font.name = "Consolas"
        elif child.type in ("text", "softbreak", "hardbreak"):
            run = paragraph.add_run("\n" if child.type != "text" else child.content)
            run.bold = bold or None
            run.italic = italic or None


# --------------------------------------------------------------------------- #
# Word → Markdown
# --------------------------------------------------------------------------- #
def docx_to_markdown(path: Path) -> str:
    """`.docx` → Markdown（标题层级、列表、表格、加粗斜体）。"""
    docx = _require("docx")
    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001 - 损坏/加密/其实是 .doc
        raise DocConvertError(
            "读不出这个 Word 文件。如果是 .doc（旧格式）请先用 Word 另存为 .docx。",
            detail=str(exc),
        ) from exc

    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = _runs_to_markdown(paragraph)
        if not text.strip():
            continue
        style = (paragraph.style.name or "").lower()
        if style.startswith("heading"):
            level = "".join(ch for ch in paragraph.style.name if ch.isdigit()) or "1"
            lines.append(f"{'#' * min(int(level), 6)} {text}")
        elif "list bullet" in style:
            lines.append(f"- {text}")
        elif "list number" in style:
            lines.append(f"1. {text}")
        else:
            lines.append(text)
        lines.append("")

    for table in document.tables:
        lines.extend(_table_to_markdown(table))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _runs_to_markdown(paragraph: Any) -> str:
    pieces: list[str] = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        if run.bold:
            text = f"**{text.strip()}**" if text.strip() else text
        if run.italic:
            text = f"*{text.strip()}*" if text.strip() else text
        pieces.append(text)
    return "".join(pieces).strip()


def _table_to_markdown(table: Any) -> list[str]:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([cell.text.strip().replace("\n", " ") for cell in row.cells])
    if not rows:
        return []

    width = max(len(row) for row in rows)
    header = rows[0] + [""] * (width - len(rows[0]))
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        padded = row + [""] * (width - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return lines


# --------------------------------------------------------------------------- #
# PDF → 文字
# --------------------------------------------------------------------------- #
def pdf_to_text(path: Path) -> str:
    """抽取 PDF 里的文字。

    **不还原排版**：PDF 里"每一行画在哪"是绘图指令，没有段落概念，
    抽出来的是按页面顺序的文字。这一点必须让用户知道 ——
    否则他会以为转换坏了。
    """
    pypdf = _require("pypdf")
    try:
        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - 加密/损坏
        raise DocConvertError("这个 PDF 读不出来（可能被加密或已损坏）。", detail=str(exc)) from exc
    return "\n\n".join(pages).strip()


def _require(name: str) -> Any:
    """惰性导入 office 依赖，缺了给一句人话。"""
    import importlib

    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - 打包时一定带着
        raise DocConvertError(
            f"缺少文档处理依赖 {name}，当前环境不支持文档转换。"
        ) from exc
