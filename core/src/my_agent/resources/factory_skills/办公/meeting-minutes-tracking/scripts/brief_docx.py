#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brief_docx.py · 工作简报 docx 生成器（v1.3）

按 brief-template.md 的事实规则生成 docx：
  - 字体：仿宋（正文 14pt）+ 黑体（标题 16/15pt）
  - 页面：A4 / 上 2.5 / 下 3.0 / 左 3.9 / 右 3.2 cm
  - 页脚："X / 总页" 居中
  - 节序：大标题 → 工作时间 → 函号 → 抬头 → 寒暄 → 一/三/四 + 结尾 + 附件 + 落款

调用方式：
    import yaml
    from brief_docx import build_brief
    data = yaml.safe_load(open("input.yaml", encoding="utf-8"))
    build_brief(data, "output.docx")

CLI:
    python3 brief_docx.py input.yaml output.docx
"""
import sys
import os
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ============ 字体辅助 ============

def _set_run_font(run, font_name, size, bold):
    """统一设置 run 字体（含中文字体的 eastAsia 字段）。"""
    run.font.name = font_name
    r = run._element
    rPr = r.find(qn('w:rPr'))
    if rPr is None:
        rPr = OxmlElement('w:rPr'); r.insert(0, rPr)
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts'); rPr.append(rFonts)
    rFonts.set(qn('w:eastAsia'), font_name)
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    if size:
        run.font.size = Pt(size)
    run.bold = bool(bold)


def _add_paragraph(doc, text, font="仿宋", size=14, bold=False,
                   align="left", space_after=0, indent_first=False):
    """添加段落，按标准规则。"""
    p = doc.add_paragraph()
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    if indent_first:
        pf.first_line_indent = Pt(28)
    if text:
        run = p.add_run(text)
        _set_run_font(run, font, size, bold)
    return p


def _add_heading(doc, text, size=15):
    """一级标题——黑体加粗。"""
    return _add_paragraph(doc, text, font="黑体", size=size, bold=True,
                          align="left", space_after=6)


def _add_big_title(doc, text):
    """大标题——黑体 16pt 居中加粗。"""
    return _add_paragraph(doc, text, font="黑体", size=16, bold=True,
                          align="center", space_after=0)


def _add_subhead(doc, text):
    """主题/子事项标题——仿宋 14pt 加粗左对齐。"""
    return _add_paragraph(doc, text, font="仿宋", size=14, bold=True,
                          align="left", space_after=0)


def _add_body(doc, text, bold=False, indent=False):
    """正文——仿宋 14pt 不加粗。"""
    return _add_paragraph(doc, text, font="仿宋", size=14, bold=bold,
                          align="left", space_after=0, indent_first=indent)


def _wrap_filename(name):
    """决定要不要给文件条目加书名号：
    - 已是《》包裹 → 直接用
    - 含中文冒号且无书名号 → 散文备注（如"其他文件：见..."）→ 不加
    - 其他 → 加书名号
    """
    if name.startswith("《"):
        return name
    if "：" in name and "《" not in name:
        return name
    return f"《{name}》"


def _add_file_ref(doc, name):
    """相关文件条目——仿宋 14pt 加粗。"""
    return _add_paragraph(doc, _wrap_filename(name), font="仿宋", size=14,
                          bold=True, align="left", space_after=0)


# ============ 页面/页脚 ============

def _setup_page(doc):
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(3.0)
    section.left_margin = Cm(3.9)
    section.right_margin = Cm(3.2)

    # 页脚："X / 总页" 居中（带空格）
    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run(" ")
    _set_run_font(run, "仿宋", 14, False)

    # PAGE field
    r1 = fp.add_run()
    _set_run_font(r1, "仿宋", 14, False)
    fld_begin = OxmlElement('w:fldChar'); fld_begin.set(qn('w:fldCharType'), 'begin')
    fld_text = OxmlElement('w:instrText'); fld_text.text = 'PAGE'
    fld_end = OxmlElement('w:fldChar'); fld_end.set(qn('w:fldCharType'), 'end')
    r1._r.append(fld_begin); r1._r.append(fld_text); r1._r.append(fld_end)

    sep = fp.add_run(" / ")
    _set_run_font(sep, "仿宋", 14, False)

    # NUMPAGES field
    r2 = fp.add_run()
    _set_run_font(r2, "仿宋", 14, False)
    fld_begin = OxmlElement('w:fldChar'); fld_begin.set(qn('w:fldCharType'), 'begin')
    fld_text = OxmlElement('w:instrText'); fld_text.text = 'NUMPAGES'
    fld_end = OxmlElement('w:fldChar'); fld_end.set(qn('w:fldCharType'), 'end')
    r2._r.append(fld_begin); r2._r.append(fld_text); r2._r.append(fld_end)

    end_sp = fp.add_run(" ")
    _set_run_font(end_sp, "仿宋", 14, False)


# ============ 主构建函数 ============

def build_brief(data, output_path):
    """根据 data 字典构建简报 docx。详细 schema 见 brief-skeleton.md 顶部 YAML。"""
    doc = Document()
    _setup_page(doc)

    # === 大标题 ===
    _add_big_title(doc, f"{data['客户名']}{data['项目名']}辅导项目")
    _add_big_title(doc, f"{data['年']}年{data['月']}月辅导简报")

    # 工作时间
    s_y, s_m, s_d = data['工作起始日'].split('-')
    e_y, e_m, e_d = data['工作结束日'].split('-')
    _add_paragraph(doc,
        f"（工作时间：{s_y}年{int(s_m)}月{int(s_d)}日-{int(e_m)}月{int(e_d)}日）",
        font="仿宋", size=14, bold=True, align="center", space_after=12)
    _add_paragraph(doc, "")

    # === 函号 / 抬头 / 寒暄 ===
    _add_body(doc, data['函号'])
    _add_body(doc, f"尊敬的{'、'.join(data['抬头对象'])}：")
    _add_body(doc, f"{data['寒暄称谓']}好！非常感谢您{data['寒暄称谓']}对我司的信任和支持！")

    next_month = data['月'] + 1
    next_year = data['年']
    if next_month > 12:
        next_month = 1
        next_year += 1
    _add_body(doc, f"有关{data['月']}月的工作简报，以及{next_year}年{next_month}月份工作计划如下： ")

    # === 一、本月辅导工作 ===
    _add_heading(doc, f"一、{data['月']}月份的辅导工作", size=15)
    _add_body(doc, f"{data['年']}年{data['月']}月份我司主要工作：")
    for item in data['本月工作概要']:
        _add_body(doc, item)
    _add_body(doc, f"主要围绕着这{len(data['本月工作概要'])}大板块展开一系列工作，具体内容如下：")
    _add_paragraph(doc, "")

    # 主题块循环
    for theme in data['主题列表']:
        _add_subhead(doc, theme['主题名'])
        if theme.get('主题概述'):
            _add_body(doc, theme['主题概述'])
        for sub in theme.get('子事项', []):
            if sub.get('标题'):
                _add_subhead(doc, sub['标题'])
            for log in sub.get('日志', []):
                _add_body(doc, log)
        if theme.get('备注'):
            _add_body(doc, f"（{theme['备注']}）")
        if theme.get('相关文件'):
            _add_subhead(doc, "相关文件：")
            for f in theme['相关文件']:
                _add_file_ref(doc, f)
        _add_paragraph(doc, "")

    # === 三、本月计划完成情况 ===
    if data.get('完成情况'):
        _add_heading(doc, f"三、{data['年']}年{data['月']}月工作计划完成情况", size=15)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        for i, h in enumerate(["上月计划项", "状态", "完成情况说明"]):
            cell = table.rows[0].cells[i]
            cell.text = ""
            run = cell.paragraphs[0].add_run(h)
            _set_run_font(run, "仿宋", 14, True)
        for row in data['完成情况']:
            cells = table.add_row().cells
            for i, key in enumerate(["上月计划项", "状态", "说明"]):
                cells[i].text = ""
                run = cells[i].paragraphs[0].add_run(row.get(key, ""))
                _set_run_font(run, "仿宋", 14, False)
        _add_paragraph(doc, "")

    # === 四、次月工作计划 ===
    if data.get('下月计划'):
        _add_heading(doc, f"四、{next_year}年{next_month}月工作计划", size=15)
        for block in data['下月计划']:
            _add_subhead(doc, block['主题'])
            for plan in block['计划']:
                _add_body(doc, f"· {plan}")
        _add_paragraph(doc, "")

    # === 结尾 + 联系人 ===
    _add_body(doc, "若有疑问、意见或建议，请随时联系我们，谢谢！")
    contact = data['联系人']
    _add_body(doc, f"{contact['姓名']},{contact['手机']},{contact['邮箱']}")
    _add_paragraph(doc, "")

    # === 附件区 ===
    if data.get('附件'):
        _add_subhead(doc, "附件：")
        for i, block in enumerate(data['附件']):
            label = block['主题名']
            if i == 0:
                label = f"（一）{label}"
            _add_subhead(doc, label)
            for f in block.get('文件', []):
                _add_body(doc, _wrap_filename(f))
        _add_paragraph(doc, "")

    # === 落款 ===
    _add_paragraph(doc, "")
    _add_paragraph(doc, "咨询项目组", font="仿宋", size=14, bold=True,
                   align="right", space_after=0)
    _add_paragraph(doc, data['落款日期'], font="仿宋", size=14, bold=True,
                   align="right", space_after=0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path


# ============ CLI ============

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"用法: python3 {sys.argv[0]} input.yaml output.docx")
        sys.exit(1)
    import yaml
    with open(sys.argv[1], encoding="utf-8") as f:
        data = yaml.safe_load(f)
    path = build_brief(data, sys.argv[2])
    print(f"已生成: {path}")


# ============ 文件说明 ============
#
# 调用流程：
#   1. Executor-C 扫描 memory/projects/clients/{客户}/*/{YYYY-MM-*.md} 切片
#   2. 按 brief-template.md §6 主题归并表聚类
#   3. 组装 data dict（schema 见 brief-skeleton.md 顶部 YAML）
#   4. 调 build_brief(data, output_path) 出 docx
#
# 与 meeting-minutes-tracking docx 生成的区别：
#   - 字体：本脚本用仿宋+黑体；会议纪要用微软雅黑
#   - 结构：本脚本是信函式段落；会议纪要是表格式
#   - 触发：本脚本月底批量；会议纪要按场次实时
#
# 关键设计点：
#   _wrap_filename() 是文件名书名号包裹的统一入口——
#   主题块"相关文件"和文末"附件"区都走这一个函数，
#   保证规则一致：已是《》→ 直接用；散文备注 → 不加；纯文件名 → 加书名号。
#   修改这个规则时只改这一处。
#
# 数据格式约定（与切片 frontmatter 对齐）：
#   data['年'] / data['月']：int，方便算次月
#   data['工作起始日'] / data['工作结束日']：YYYY-MM-DD 字符串
#   data['抬头对象']：list[str]，自动用顿号拼接
#   data['完成情况'] / data['下月计划']：可空——空时该节不输出（首期简报无上月对照）
#
# 维护：项目组 · 2026-05-17 · v1.3
#
# === END OF FILE ===


