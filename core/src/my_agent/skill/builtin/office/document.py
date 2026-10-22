






from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill
from .._deps import require

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".log", ".json", ".yaml", ".yml", ".py", ".sql"}

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1")


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def _truncate(text: str, max_chars: int) -> tuple[str, bool, int]:
    if len(text) <= max_chars:
        return text, False, len(text)
    return text[:max_chars], True, len(text)


def _parse_pdf(path: Path, max_chars: int, max_pages: int) -> dict[str, Any]:
    pypdf = require("pypdf", "解析 PDF")
    try:
        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
        limit = min(total_pages, max_pages)
        chunks: list[str] = []
        for index in range(limit):
            try:
                chunks.append(reader.pages[index].extract_text() or "")
            except Exception as exc:  
                chunks.append(f"[第 {index + 1} 页解析失败：{exc}]")
        text = "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())
    except Exception as exc:  
        raise SkillExecutionError(f"无法解析 PDF：{exc}") from exc

    content, truncated, length = _truncate(text, max_chars)
    return {
        "document_type": "pdf",
        "pages": total_pages,
        "pages_read": limit,
        "text": content,
        "truncated": truncated,
        "total_chars": length,
        "note": (
            f"PDF 共 {total_pages} 页，本次仅读取前 {limit} 页"
            if limit < total_pages
            else None
        ),
    }


def _parse_docx(path: Path, max_chars: int) -> dict[str, Any]:
    docx = require("docx", "解析 Word 文档")
    try:
        document = docx.Document(str(path))
    except Exception as exc:  
        raise SkillExecutionError(f"无法解析 Word 文档：{exc}") from exc

    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    tables: list[str] = []
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            tables.append(" | ".join(cells))
        tables.append("")

    body = "\n".join(paragraphs)
    if tables:
        body += "\n\n[表格]\n" + "\n".join(tables)

    content, truncated, length = _truncate(body, max_chars)
    return {
        "document_type": "docx",
        "paragraphs": len(paragraphs),
        "tables": len(document.tables),
        "text": content,
        "truncated": truncated,
        "total_chars": length,
        "note": None,
    }


def _parse_csv(path: Path, max_chars: int, max_rows: int) -> dict[str, Any]:








    raw, encoding = _decode(path.read_bytes())
    reader = csv.reader(io.StringIO(raw))

    header: list[str] = []
    preview: list[list[str]] = []
    body_rows = 0
    for index, row in enumerate(reader):
        if index == 0:
            header = row
            continue
        body_rows += 1
        
        if len(preview) < max_rows:
            preview.append(row)

    if not header:
        return {
            "document_type": "csv",
            "rows": 0,
            "columns": [],
            "text": "",
            "truncated": False,
            "encoding": encoding,
            "note": "文件为空",
        }

    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend(
        "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in preview
    )

    content, truncated, _ = _truncate("\n".join(lines), max_chars)
    return {
        "document_type": "csv",
        "rows": body_rows,
        "columns": header,
        "text": content,
        "truncated": truncated or body_rows > len(preview),
        "encoding": encoding,
        "note": (
            f"共 {body_rows} 行数据，仅展示前 {len(preview)} 行。"
            f"如需统计请改用 excel_analyze 或 excel_read。"
        ),
    }


def _parse_text(path: Path, max_chars: int) -> dict[str, Any]:
    raw = path.read_bytes()
    text, encoding = _decode(raw)
    content, truncated, length = _truncate(text, max_chars)
    return {
        "document_type": "text",
        "text": content,
        "truncated": truncated,
        "total_chars": length,
        "encoding": encoding,
        "note": None,
    }


class DocParseParams(BaseModel):
    file_path: str = Field(..., description="文档的绝对路径")
    
    
    
    max_chars: int = Field(
        12000, ge=500, le=20_000_000, description="最多返回多少字符（填大即可返回全文）"
    )
    max_pages: int = Field(30, ge=1, le=20_000, description="PDF 最多读取多少页")
    max_rows: int = Field(30, ge=1, le=5_000_000, description="CSV 最多展示多少行")


@skill(
    name="doc_parse",
    display_name="解析文档",
    description=(
        "提取 PDF、Word(.docx)、纯文本(.txt/.md/.json/.log)、CSV 文件的内容。"
        "当用户要求「提取这份合同里的条款」「总结这份 PDF」「看看这个 CSV 有什么」时使用。"
        "返回文本内容；被截断时会给出说明，可调大 max_chars 或分段读取。"
        "注意：操作 Excel 请用 excel_read，本工具不处理 .xlsx。"
    ),
    params_model=DocParseParams,
    category="office",
    permission_level="safe",
    tags=["文档", "解析"],
)
class DocParseSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = DocParseParams(**params)
        path = ctx.resolve_input_file(args.file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            result = _parse_pdf(path, args.max_chars, args.max_pages)
        elif suffix in (".docx", ".doc"):
            if suffix == ".doc":
                raise SkillExecutionError(
                    "不支持旧版 .doc 格式，请先用 Word 另存为 .docx 再解析。"
                )
            result = _parse_docx(path, args.max_chars)
        elif suffix == ".csv":
            result = _parse_csv(path, args.max_chars, args.max_rows)
        elif suffix in TEXT_SUFFIXES or suffix == "":
            result = _parse_text(path, args.max_chars)
        elif suffix in (".xlsx", ".xlsm", ".xls"):
            raise SkillExecutionError(
                f"{suffix} 是 Excel 文件，请改用 excel_read（查看数据）或 excel_analyze（做统计）。"
            )
        else:
            
            result = _parse_text(path, args.max_chars)
            result["note"] = f"未知文件类型 {suffix}，已按纯文本尝试解析。"

        return {
            "file": str(path),
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            **result,
        }
