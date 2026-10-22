












from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.doc_convert import (
    MarkdownToWordSkill,
    PdfToTextSkill,
    ToPdfSkill,
    WordToMarkdownSkill,
)
from my_agent.utils.doc_convert import (
    DocConvertError,
    docx_to_markdown,
    markdown_to_docx,
    markdown_to_html,
    pdf_to_text,
)

SAMPLE = """# 季度总结

本季度**重点**是提速，*次要*目标是降本。

## 动作项

- 把构建时间压到 5 分钟
- 补齐回归用例

## 数据

| 指标 | 上季度 | 本季度 |
| --- | --- | --- |
| 构建时长 | 12 分钟 | 4 分钟 |
| 用例数 | 300 | 460 |
"""


class TestMarkdownToHtml:
    def test_structure_and_chinese_font(self):
        html = markdown_to_html(SAMPLE, title="季度总结")

        assert "<h1>" in html and "<h2>" in html
        assert "<table>" in html and "<th>" in html
        assert "<strong>重点</strong>" in html
        
        assert "Microsoft YaHei" in html
        assert "季度总结" in html

    def test_html_is_escaped_not_executed(self):

        html = markdown_to_html("<script>alert(1)</script>")

        assert "<script>" not in html


class TestWordRoundTrip:
    def test_structures_survive(self, tmp_path):
        target = tmp_path / "out.docx"
        markdown_to_docx(SAMPLE, target, title="季度总结")
        assert target.exists()

        back = docx_to_markdown(target)

        assert "# 季度总结" in back
        assert "## 动作项" in back
        assert "- 把构建时间压到 5 分钟" in back
        assert "**重点**" in back
        
        assert "| 指标 | 上季度 | 本季度 |" in back
        assert "| 构建时长 | 12 分钟 | 4 分钟 |" in back

    def test_old_doc_format_gives_actionable_hint(self, tmp_path):
        broken = tmp_path / "old.doc"
        broken.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  

        with pytest.raises(DocConvertError) as info:
            docx_to_markdown(broken)

        assert "docx" in info.value.message


class TestPdfToText:
    def test_encrypted_or_broken_pdf_is_reported(self, tmp_path):
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4\n" + "这不是一个真的 PDF".encode())

        with pytest.raises(DocConvertError) as info:
            pdf_to_text(broken)

        assert "PDF" in info.value.message


class TestSkills:
    def _ctx(self, tmp_path) -> SkillContext:
        from my_agent.config.paths import AppPaths

        paths = AppPaths(tmp_path / "AgentDesktop").ensure()
        return SkillContext(paths=paths, session_id="s1")

    def test_permission_levels(self):
        assert PdfToTextSkill.meta.permission_level == "safe"
        assert WordToMarkdownSkill.meta.permission_level == "confirm"
        assert MarkdownToWordSkill.meta.permission_level == "confirm"
        assert ToPdfSkill.meta.permission_level == "confirm"

    @pytest.mark.asyncio
    async def test_markdown_to_word_then_back(self, tmp_path):
        ctx = self._ctx(tmp_path)
        source = tmp_path / "input.md"
        source.write_text(SAMPLE, encoding="utf-8")

        to_word = await MarkdownToWordSkill().run(ctx, path=str(source), title="季度总结")
        assert Path(to_word["file"]).exists()

        back = await WordToMarkdownSkill().run(ctx, path=to_word["file"])
        assert "# 季度总结" in back["content"]
        assert "| 指标 | 上季度 | 本季度 |" in back["content"]

    @pytest.mark.asyncio
    async def test_to_pdf_rejects_unsupported_input(self, tmp_path):

        ctx = self._ctx(tmp_path)
        bad = tmp_path / "x.csv"
        bad.write_text("a,b\n", encoding="utf-8")

        with pytest.raises(SkillExecutionError) as info:
            await ToPdfSkill().run(ctx, path=str(bad))

        assert "不支持" in str(info.value)

    @pytest.mark.asyncio
    async def test_skills_require_exactly_one_payload(self, tmp_path):
        ctx = self._ctx(tmp_path)

        with pytest.raises(SkillExecutionError):
            await MarkdownToWordSkill().run(ctx, path="a.md", content="# x")
        with pytest.raises(SkillExecutionError):
            await MarkdownToWordSkill().run(ctx)

    @pytest.mark.asyncio
    async def test_pdf_to_text_on_scanned_file_explains_ocr(self, tmp_path):

        ctx = self._ctx(tmp_path)
        
        
        import pypdf

        blank = tmp_path / "blank.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with blank.open("wb") as handle:
            writer.write(handle)

        result = await PdfToTextSkill().run(ctx, path=str(blank))

        assert result["chars"] == 0
        assert "OCR" in result["message"]


@pytest.mark.live
@pytest.mark.asyncio
async def test_pdf_render_end_to_end(tmp_path):




    from my_agent.config.paths import AppPaths

    ctx = SkillContext(paths=AppPaths(tmp_path / "AgentDesktop").ensure(), session_id="s1")

    result = await ToPdfSkill().run(ctx, content=SAMPLE, title="季度总结")

    text = pdf_to_text(Path(result["file"]))
    assert "季度总结" in text
    assert "构建时长" in text
