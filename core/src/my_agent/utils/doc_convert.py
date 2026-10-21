



























from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)



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
    
    return MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def markdown_to_html(markdown_text: str, *, title: str = "") -> str:

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


    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail





def markdown_to_docx(markdown_text: str, target: Path, *, title: str = "") -> None:

    docx = _require("docx")
    document = docx.Document()

    if title:
        document.add_heading(title, level=0)

    tokens = _markdown_parser().parse(markdown_text or "")
    list_stack: list[str] = []
    
    
    
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
    del header_rows  
    return index + 1


def _plain(text: str) -> str:

    return (text or "").replace("*", "").replace("`", "").strip()


def _add_runs(paragraph: Any, inline: Any) -> None:

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





def docx_to_markdown(path: Path) -> str:

    docx = _require("docx")
    try:
        document = docx.Document(str(path))
    except Exception as exc:  
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





def pdf_to_text(path: Path) -> str:






    pypdf = _require("pypdf")
    try:
        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  
        raise DocConvertError("这个 PDF 读不出来（可能被加密或已损坏）。", detail=str(exc)) from exc
    return "\n\n".join(pages).strip()


def _require(name: str) -> Any:

    import importlib

    try:
        return importlib.import_module(name)
    except ImportError as exc:  
        raise DocConvertError(
            f"缺少文档处理依赖 {name}，当前环境不支持文档转换。"
        ) from exc
