"""办公技能测试：Excel 读写与聚合、文档解析、报告与图表生成。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_agent.errors import (
    PathNotAllowedError,
    SkillExecutionError,
    SkillPermissionError,
    SkillValidationError,
)
from my_agent.skill.builtin.office.chart import ChartGenerateSkill
from my_agent.skill.builtin.office.document import DocParseSkill
from my_agent.skill.builtin.office.excel import (
    ExcelAnalyzeSkill,
    ExcelReadSkill,
    ExcelWriteSkill,
)
from my_agent.skill.builtin.office.report import ReportGenerateSkill
from my_agent.skill.manager import SkillManager

openpyxl = pytest.importorskip("openpyxl", reason="需要 office 依赖")


@pytest.fixture(autouse=True)
def auto_approve(skill_env):
    """让确认自动通过。

    excel_write 是 confirm 级技能，没有确认通道时会被**正确地拒绝**。
    这里显式装一个"总是批准"的通道，好让写入逻辑本身可测；
    确认机制自身的行为由 test_agent_loop / test_security / test_server 覆盖。
    """

    async def approve(_request) -> bool:
        return True

    skill_env.ctx.confirm = approve


@pytest.fixture
def manager(skill_env) -> SkillManager:
    skills = SkillManager()
    for skill_cls in (
        ExcelReadSkill,
        ExcelWriteSkill,
        ExcelAnalyzeSkill,
        DocParseSkill,
        ReportGenerateSkill,
        ChartGenerateSkill,
    ):
        skills.register(skill_cls)
    return skills


def make_xlsx(path: Path, rows: list[list], sheet: str = "Sheet1") -> Path:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


SALES_ROWS = [
    ["月份", "产品", "销售额"],
    ["1月", "A", 1200],
    ["1月", "B", 800],
    ["2月", "A", 1500],
    ["2月", "B", 950],
    ["3月", "A", 1700],
]


# --------------------------------------------------------------------------- #
# excel_read
# --------------------------------------------------------------------------- #
async def test_excel_read(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    result = json.loads(await manager.execute("excel_read", {"file_path": str(path)}, skill_env.ctx))

    assert result["columns"] == ["月份", "产品", "销售额"]
    assert result["total_rows"] == 5
    assert result["rows"][0]["月份"] == "1月"
    assert result["sheets"] == ["Sheet1"]
    assert result["truncated"] is False


async def test_excel_read_respects_max_rows(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    result = json.loads(
        await manager.execute(
            "excel_read", {"file_path": str(path), "max_rows": 2}, skill_env.ctx
        )
    )
    assert len(result["rows"]) == 2
    # total_rows 必须是真实行数，否则模型会以为表里只有 2 行
    assert result["total_rows"] == 5
    assert result["truncated"] is True


async def test_excel_read_handles_blank_and_duplicate_headers(manager, skill_env):
    path = make_xlsx(
        skill_env.root / "messy.xlsx",
        [["名称", None, "名称"], ["a", 1, "x"], [None, None, None], ["b", 2, "y"]],
    )
    result = json.loads(await manager.execute("excel_read", {"file_path": str(path)}, skill_env.ctx))
    assert result["columns"] == ["名称", "列2", "名称_1"]
    # 整行为空的行应被跳过
    assert result["total_rows"] == 2


async def test_excel_read_unknown_sheet_lists_available(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS, sheet="数据")
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "excel_read", {"file_path": str(path), "sheet_name": "不存在的表"}, skill_env.ctx
        )
    assert "数据" in str(exc.value)


# --------------------------------------------------------------------------- #
# excel_analyze
# --------------------------------------------------------------------------- #
async def test_excel_analyze_sum_by_group(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    result = json.loads(
        await manager.execute(
            "excel_analyze",
            {"file_path": str(path), "group_by": "月份", "value_column": "销售额"},
            skill_env.ctx,
        )
    )
    assert result["aggregation"] == "sum"
    # 2月=1500+950=2450 > 1月=1200+800=2000 > 3月=1700，默认按值倒序
    assert [(item["group"], item["value"]) for item in result["items"]] == [
        ("2月", 2450),
        ("1月", 2000),
        ("3月", 1700),
    ]
    assert result["total"] == 6150
    assert result["groups"] == 3


async def test_excel_analyze_count_mode(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    result = json.loads(
        await manager.execute(
            "excel_analyze",
            {"file_path": str(path), "group_by": "产品", "aggregation": "count"},
            skill_env.ctx,
        )
    )
    counts = {item["group"]: item["value"] for item in result["items"]}
    assert counts == {"A": 3, "B": 2}


async def test_excel_analyze_reports_unknown_column_with_hint(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "excel_analyze",
            {"file_path": str(path), "group_by": "季度", "value_column": "销售额"},
            skill_env.ctx,
        )
    message = str(exc.value)
    assert "季度" in message
    # 必须把可用列列出来，否则模型只能瞎猜
    assert "月份" in message


async def test_excel_analyze_requires_value_column_for_sum(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "excel_analyze", {"file_path": str(path), "group_by": "产品"}, skill_env.ctx
        )
    assert "value_column" in str(exc.value)


async def test_excel_analyze_skips_non_numeric(manager, skill_env):
    path = make_xlsx(
        skill_env.root / "mixed.xlsx",
        [["部门", "金额"], ["销售", 100], ["销售", "无"], ["技术", 200]],
    )
    result = json.loads(
        await manager.execute(
            "excel_analyze",
            {"file_path": str(path), "group_by": "部门", "value_column": "金额"},
            skill_env.ctx,
        )
    )
    assert result["skipped_non_numeric"] == 1
    assert result["total"] == 300


# --------------------------------------------------------------------------- #
# excel_write
# --------------------------------------------------------------------------- #
async def test_excel_write_creates_file(manager, skill_env):
    target = skill_env.root / "out.xlsx"
    result = json.loads(
        await manager.execute(
            "excel_write",
            {
                "file_path": str(target),
                "rows": [{"名称": "甲", "数量": 1}, {"名称": "乙", "数量": 2}],
            },
            skill_env.ctx,
        )
    )
    assert result["written_rows"] == 2
    assert target.is_file()

    readback = json.loads(
        await manager.execute("excel_read", {"file_path": str(target)}, skill_env.ctx)
    )
    assert readback["columns"] == ["名称", "数量"]
    assert readback["total_rows"] == 2


async def test_excel_write_append_preserves_existing_columns(manager, skill_env):
    target = make_xlsx(skill_env.root / "base.xlsx", [["名称", "数量"], ["甲", 1]])
    await manager.execute(
        "excel_write",
        {"file_path": str(target), "rows": [{"名称": "乙", "数量": 2}], "mode": "append"},
        skill_env.ctx,
    )
    readback = json.loads(
        await manager.execute("excel_read", {"file_path": str(target)}, skill_env.ctx)
    )
    assert readback["total_rows"] == 2
    assert readback["columns"] == ["名称", "数量"]


async def test_excel_write_append_adds_new_column(manager, skill_env):
    """新出现的键应补成新列，而不是被丢弃。"""
    target = make_xlsx(skill_env.root / "base.xlsx", [["名称", "数量"], ["甲", 1]])
    await manager.execute(
        "excel_write",
        {
            "file_path": str(target),
            "rows": [{"名称": "乙", "数量": 2, "备注": "新增"}],
            "mode": "append",
        },
        skill_env.ctx,
    )
    readback = json.loads(
        await manager.execute("excel_read", {"file_path": str(target)}, skill_env.ctx)
    )
    assert "备注" in readback["columns"]


async def test_excel_write_overwrite_clears_rows(manager, skill_env):
    target = make_xlsx(skill_env.root / "base.xlsx", [["名称"], ["甲"], ["乙"], ["丙"]])
    await manager.execute(
        "excel_write",
        {
            "file_path": str(target),
            "rows": [{"名称": "只有我"}],
            "mode": "overwrite",
        },
        skill_env.ctx,
    )
    readback = json.loads(
        await manager.execute("excel_read", {"file_path": str(target)}, skill_env.ctx)
    )
    assert readback["total_rows"] == 1
    assert readback["rows"][0]["名称"] == "只有我"


async def test_excel_write_is_confirm_level(manager):
    """写操作必须有副作用标记，否则会绕过权限确认。"""
    assert manager.get("excel_write").meta.permission_level == "confirm"


async def test_excel_write_denied_without_confirm_channel(manager, skill_env):
    """没有确认通道时必须拒绝写入，绝不能"悄悄写进去"。"""
    skill_env.ctx.confirm = None
    target = skill_env.root / "不该被创建.xlsx"

    with pytest.raises(SkillPermissionError):
        await manager.execute(
            "excel_write",
            {"file_path": str(target), "rows": [{"a": 1}]},
            skill_env.ctx,
        )
    assert not target.exists()


async def test_excel_write_denied_when_user_rejects(manager, skill_env):
    async def reject(_request) -> bool:
        return False

    skill_env.ctx.confirm = reject
    target = skill_env.root / "用户拒绝.xlsx"

    with pytest.raises(SkillPermissionError):
        await manager.execute(
            "excel_write",
            {"file_path": str(target), "rows": [{"a": 1}]},
            skill_env.ctx,
        )
    assert not target.exists()


async def test_excel_write_rejects_non_serializable_cell(manager, skill_env):
    target = skill_env.root / "nested.xlsx"
    await manager.execute(
        "excel_write",
        {"file_path": str(target), "rows": [{"配置": {"a": 1}}]},
        skill_env.ctx,
    )
    readback = json.loads(
        await manager.execute("excel_read", {"file_path": str(target)}, skill_env.ctx)
    )
    assert json.loads(readback["rows"][0]["配置"]) == {"a": 1}


# --------------------------------------------------------------------------- #
# doc_parse
# --------------------------------------------------------------------------- #
async def test_doc_parse_text(manager, skill_env):
    path = skill_env.root / "note.md"
    path.write_text("# 标题\n\n正文内容", encoding="utf-8")
    result = json.loads(await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx))
    assert result["document_type"] == "text"
    assert "正文内容" in result["text"]


async def test_doc_parse_gbk_text(manager, skill_env):
    """中文 Windows 上的文本文件经常是 GBK，不能直接按 UTF-8 读崩。"""
    path = skill_env.root / "gbk.txt"
    path.write_bytes("这是 GBK 编码的中文内容".encode("gb18030"))
    result = json.loads(await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx))
    assert "中文内容" in result["text"]
    assert result["encoding"] in ("gb18030", "utf-8")


async def test_doc_parse_csv_renders_table(manager, skill_env):
    path = skill_env.root / "data.csv"
    path.write_text("月份,金额\n1月,100\n2月,200\n", encoding="utf-8")
    result = json.loads(await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx))
    assert result["document_type"] == "csv"
    assert result["columns"] == ["月份", "金额"]
    assert result["rows"] == 2
    assert "| 1月 | 100 |" in result["text"]


async def test_doc_parse_docx(manager, skill_env):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("第一段内容")
    document.add_paragraph("第二段内容")
    path = skill_env.root / "doc.docx"
    document.save(str(path))

    result = json.loads(await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx))
    assert result["document_type"] == "docx"
    assert "第一段内容" in result["text"]


async def test_doc_parse_pdf(manager, skill_env):
    pypdf = pytest.importorskip("pypdf")
    path = skill_env.root / "blank.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as handle:
        writer.write(handle)

    result = json.loads(await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx))
    assert result["document_type"] == "pdf"
    assert result["pages"] == 1


async def test_doc_parse_truncates_and_says_so(manager, skill_env):
    path = skill_env.root / "long.txt"
    path.write_text("字" * 5000, encoding="utf-8")
    result = json.loads(
        await manager.execute(
            "doc_parse", {"file_path": str(path), "max_chars": 500}, skill_env.ctx
        )
    )
    assert result["truncated"] is True
    assert result["total_chars"] == 5000
    assert len(result["text"]) == 500


async def test_doc_parse_redirects_xlsx_to_excel_read(manager, skill_env):
    path = make_xlsx(skill_env.root / "sales.xlsx", SALES_ROWS)
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("doc_parse", {"file_path": str(path)}, skill_env.ctx)
    assert "excel_read" in str(exc.value)


async def test_doc_parse_missing_file(manager, skill_env):
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "doc_parse", {"file_path": str(skill_env.root / "nope.txt")}, skill_env.ctx
        )
    assert "不存在" in str(exc.value)


# --------------------------------------------------------------------------- #
# report_generate
# --------------------------------------------------------------------------- #
async def test_report_generate_writes_markdown(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "report_generate",
            {
                "title": "本周周报",
                "summary": "本周完成度良好",
                "sections": [
                    {"heading": "本周工作", "bullets": ["完成 A", "完成 B"]},
                    {"heading": "下周计划", "content": "继续推进 C"},
                ],
                "metadata": {"作者": "张三"},
            },
            skill_env.ctx,
        )
    )
    target = Path(result["file"])
    assert target.is_file()
    assert target.parent == skill_env.paths.artifacts_dir

    text = target.read_text(encoding="utf-8")
    assert "# 本周周报" in text
    assert "> 本周完成度良好" in text
    assert "## 本周工作" in text
    assert "- 完成 A" in text
    assert "- 作者：张三" in text


async def test_report_generate_includes_toc(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "report_generate",
            {
                "title": "报告",
                "output_name": "with-toc.md",
                "sections": [{"heading": "第一章"}, {"heading": "第二章"}],
                "include_toc": True,
            },
            skill_env.ctx,
        )
    )
    text = Path(result["file"]).read_text(encoding="utf-8")
    assert "## 目录" in text
    assert "1. 第一章" in text


async def test_report_generate_rejects_empty(manager, skill_env):
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("report_generate", {"title": "空报告"}, skill_env.ctx)
    assert "至少" in str(exc.value)


async def test_report_generate_sanitizes_output_name(manager, skill_env):
    """模型可能给出带目录的路径，必须只取文件名并落在产物目录内。"""
    result = json.loads(
        await manager.execute(
            "report_generate",
            {
                "title": "穿越测试",
                "output_name": "../../../evil.md",
                "content": "内容",
            },
            skill_env.ctx,
        )
    )
    target = Path(result["file"]).resolve()
    assert target.parent == skill_env.paths.artifacts_dir.resolve()
    assert target.name == "evil.md"


async def test_report_generate_avoids_overwrite(manager, skill_env):
    first = json.loads(
        await manager.execute(
            "report_generate", {"title": "A", "output_name": "same.md", "content": "1"}, skill_env.ctx
        )
    )
    second = json.loads(
        await manager.execute(
            "report_generate", {"title": "B", "output_name": "same.md", "content": "2"}, skill_env.ctx
        )
    )
    assert first["file"] != second["file"]
    assert Path(first["file"]).read_text(encoding="utf-8") != Path(second["file"]).read_text(
        encoding="utf-8"
    )


async def test_report_is_registered_as_artifact(manager, skill_env):
    await manager.execute(
        "report_generate", {"title": "归档测试", "content": "x"}, skill_env.ctx
    )
    artifacts = await skill_env.workspace.list_files(kind="artifact")
    assert len(artifacts) == 1
    assert artifacts[0].note == "归档测试"


# --------------------------------------------------------------------------- #
# chart_generate
# --------------------------------------------------------------------------- #
async def test_chart_generate_bar(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "chart_generate",
            {
                "chart_type": "bar",
                "title": "月度销售",
                "categories": ["1月", "2月", "3月"],
                "series": [{"name": "A 产品", "values": [1200, 1500, 1700]}],
            },
            skill_env.ctx,
        )
    )
    svg = Path(result["file"]).read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "月度销售" in svg
    assert "1月" in svg


async def test_chart_generate_pie_and_line(manager, skill_env):
    for chart_type in ("pie", "line"):
        result = json.loads(
            await manager.execute(
                "chart_generate",
                {
                    "chart_type": chart_type,
                    "title": f"{chart_type} 图",
                    "categories": ["甲", "乙"],
                    "series": [{"name": "占比", "values": [60, 40]}],
                    "output_name": f"{chart_type}.svg",
                },
                skill_env.ctx,
            )
        )
        svg = Path(result["file"]).read_text(encoding="utf-8")
        assert "<svg" in svg and "</svg>" in svg


async def test_chart_generate_rejects_length_mismatch(manager, skill_env):
    """数值与标签数量不一致是模型最常犯的错，必须给出可操作的提示。"""
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "chart_generate",
            {
                "title": "错位",
                "categories": ["a", "b", "c"],
                "series": [{"name": "s", "values": [1, 2]}],
            },
            skill_env.ctx,
        )
    assert "一一对应" in str(exc.value)


async def test_chart_generate_rejects_unknown_type(manager, skill_env):
    """类型是 Literal，参数校验阶段就会被拦下（比进到技能里再报错更早）。"""
    with pytest.raises(SkillValidationError) as exc:
        await manager.execute(
            "chart_generate",
            {
                "chart_type": "radar",
                "title": "不支持",
                "categories": ["a"],
                "series": [{"name": "s", "values": [1]}],
            },
            skill_env.ctx,
        )
    message = str(exc.value)
    assert "bar" in message and "line" in message and "pie" in message


# --------------------------------------------------------------------------- #
# 白名单强制
# --------------------------------------------------------------------------- #
async def test_office_skills_respect_path_whitelist(manager, skill_env, tmp_path_factory):
    """白名单是硬约束：技能不能读写白名单之外的文件。

    错误类型必须是 ``PathNotAllowedError`` 而不是被包装成
    ``SkillExecutionError`` —— 否则上层无法区分"权限问题"和"代码 bug"。
    """
    outside = tmp_path_factory.mktemp("outside") / "secret.xlsx"
    make_xlsx(outside, [["机密", "数据"], ["a", 1]])

    with pytest.raises(PathNotAllowedError) as read_exc:
        await manager.execute("excel_read", {"file_path": str(outside)}, skill_env.ctx)
    assert "白名单之外" in str(read_exc.value)

    with pytest.raises(PathNotAllowedError):
        await manager.execute("doc_parse", {"file_path": str(outside)}, skill_env.ctx)

    with pytest.raises(PathNotAllowedError):
        await manager.execute(
            "excel_write",
            {"file_path": str(outside), "rows": [{"a": 1}]},
            skill_env.ctx,
        )
