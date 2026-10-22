






from __future__ import annotations

import json

import pytest

from my_agent.storage.preview import MAX_TABLE_ROWS, build_preview


def make(tmp_path, name: str, content: str | bytes):
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def preview(path, name: str | None = None):
    return build_preview(path, original_name=name or path.name, download_url="/v1/files/x")





def test_svg_preview(tmp_path):
    path = make(tmp_path, "chart.svg", '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    result = preview(path)
    assert result["kind"] == "svg"
    assert "<rect/>" in result["content"]


def test_markdown_preview(tmp_path):
    path = make(tmp_path, "report.md", "# 周报\n\n本周完成了 MCP 集成。")
    result = preview(path)
    assert result["kind"] == "markdown"
    assert "MCP 集成" in result["content"]


def test_csv_preview_becomes_table(tmp_path):
    path = make(tmp_path, "sales.csv", "月份,金额\n1月,100\n2月,200")
    result = preview(path)

    assert result["kind"] == "table"
    sheet = result["sheets"][0]
    assert sheet["columns"] == ["月份", "金额"]
    assert sheet["rows"] == [["1月", "100"], ["2月", "200"]]
    assert sheet["total_rows"] == 2
    assert sheet["truncated"] is False


def test_xlsx_preview(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    path = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "销售"
    sheet.append(["月份", "金额"])
    sheet.append(["1月", 100])
    sheet.append(["2月", 200])
    workbook.create_sheet("空表")
    workbook.save(path)

    result = preview(path)
    assert result["kind"] == "table"
    assert result["sheets"][0]["name"] == "销售"
    assert result["sheets"][0]["columns"] == ["月份", "金额"]
    assert result["sheets"][0]["rows"] == [["1月", 100], ["2月", 200]]
    
    assert [s["name"] for s in result["sheets"]] == ["销售"]


def test_docx_preview_keeps_heading_structure(tmp_path):
    docx = pytest.importorskip("docx")

    path = tmp_path / "doc.docx"
    document = docx.Document()
    document.add_heading("季度总结", level=1)
    document.add_paragraph("本季度收入增长明显。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "金额"
    table.cell(1, 0).text = "A"
    table.cell(1, 1).text = "100"
    document.save(path)

    result = preview(path)
    assert result["kind"] == "markdown"
    
    assert "# 季度总结" in result["content"]
    assert "| 项目 | 金额 |" in result["content"]


def test_image_preview_uses_url_not_base64(tmp_path):
    
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    path = make(tmp_path, "shot.png", png)
    result = preview(path)
    assert result["kind"] == "image"
    
    assert result["url"] == "/v1/files/x"


def test_json_preview_is_pretty_printed(tmp_path):
    path = make(tmp_path, "data.json", '{"a":1,"b":[2,3]}')
    result = preview(path)
    assert result["kind"] == "json"
    assert json.loads(result["content"]) == {"a": 1, "b": [2, 3]}





def test_broken_json_falls_back_to_text(tmp_path):

    path = make(tmp_path, "broken.json", "{这不是合法 JSON")
    result = preview(path)
    assert result["kind"] == "text"
    assert "这不是合法 JSON" in result["content"]
    assert "解析失败" in result.get("note", "")


def test_broken_xlsx_returns_unsupported(tmp_path):

    path = make(tmp_path, "fake.xlsx", b"this is definitely not a workbook")
    result = preview(path)
    assert result["kind"] == "unsupported"
    assert result["reason"]


def test_broken_pdf_returns_unsupported(tmp_path):
    path = make(tmp_path, "fake.pdf", b"%PDF-1.4 not really")
    result = preview(path)
    assert result["kind"] == "unsupported"
    assert result["reason"]


def test_unknown_extension_is_graceful(tmp_path):
    path = make(tmp_path, "archive.zip", b"PK\x03\x04")
    result = preview(path)
    assert result["kind"] == "unsupported"
    assert ".zip" in result["reason"]


def test_missing_file_is_graceful(tmp_path):
    path = tmp_path / "gone.md"
    result = preview(path)
    assert result["kind"] == "unsupported"
    assert "丢失" in result["reason"]





def test_large_csv_is_truncated(tmp_path):

    rows = ["序号,值"] + [f"{i},{i * 2}" for i in range(1, MAX_TABLE_ROWS + 500)]
    path = make(tmp_path, "big.csv", "\n".join(rows))

    result = preview(path)
    sheet = result["sheets"][0]
    assert len(sheet["rows"]) == MAX_TABLE_ROWS
    assert sheet["truncated"] is True
    
    assert sheet["total_rows"] == MAX_TABLE_ROWS + 499


def test_huge_text_is_truncated(tmp_path):
    path = make(tmp_path, "huge.md", "字" * 500_000)
    result = preview(path)
    assert result["kind"] == "markdown"
    assert result["truncated"] is True
    assert len(result["content"]) <= 200_000


def test_long_cell_is_clipped(tmp_path):

    path = make(tmp_path, "wide.csv", "标题,内容\nA," + "x" * 5000)
    result = preview(path)
    cell = result["sheets"][0]["rows"][0][1]
    assert len(cell) < 600
    assert cell.endswith("…")


def test_metadata_is_always_present(tmp_path):
    path = make(tmp_path, "a.md", "内容")
    result = preview(path)
    for key in ("name", "suffix", "size", "download_url", "kind"):
        assert key in result
