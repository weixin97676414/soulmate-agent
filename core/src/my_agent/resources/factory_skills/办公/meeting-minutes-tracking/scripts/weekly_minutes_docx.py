#!/usr/bin/env python3
# -*- coding: utf-8 -*-


















import argparse, json, re, sys
from docx import Document
from docx.shared import Pt, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT = "微软雅黑"

SAMPLE_CONTENT = {
    "title": "甲方A  项目验收与回款周会  会议纪要",
    "subtitle": "（2026 年第 23 周 · 2026-06-06）",
    "confidential_note": "内部留档 · 含真实客户名与金额，不对外发送",
    "meta": {
        "会议时间": "2026-06-06（周六）11:30—12:30",
        "会议地点": "腾讯会议（线上）",
        "会议类型": "项目管理会 · 每周验收与回款专题",
        "会议主持人": "P-管理-李",
        "与 会 者": "甲方A：张、王、陈、赵 / 我司：P-CON-钱、P-PM-孙",
    },
    "agenda": [
        "复盘上周待办事项进展，确认完成、延续、阻塞或取消状态；",
        "回顾在手项目验收进展，明确攻坚目标与节点；",
        "盘点新签与存量项目回款计划，研判现金流；",
        "部署在建项目安装调试与资源、外部协调事项。",
    ],
    "sections": [
        {"title": "（一）上半年已验收约300万元，下半年目标调整为3100万元，6月底前攻坚2400万元",
         "bullets": [
             "截至本周，上半年累计完成验收约300万元；经集团调整，上半年验收目标定为3100万元。",
             "6月30日前重点攻坚约2400万元在手项目，涉及多家客户。",
         ]},
        {"title": "（二）应回未回款项已逐一明确计划，大额项目预计6月底前启动",
         "bullets": [
             "本周已签订新合同，预付款将陆续到账。",
             "存量项目回款计划已明确。",
         ]},
    ],
    "prior_action_items": [
        {"编号": "上周-01", "事项": "完成项目验收准备", "负责人": "张",
         "原定时限": "2026-06-05 前", "进展状态": "已完成",
         "进展说明": "验收资料已提交并完成内部确认", "本周处理": "本项关闭"},
        {"编号": "上周-02", "事项": "推进银行授信资料提交", "负责人": "李",
         "原定时限": "2026-06-05 前", "进展状态": "进行中",
         "进展说明": "授信资料已提交，等待银行反馈", "本周处理": "承接至本周-01"},
    ],
    "action_items": [
        {"编号": "本周-01", "事项": "跟进银行授信审批反馈", "负责人": "李",
         "追踪人": "王", "完成时限": "2026-06-12 前",
         "来源": "承接上周-02", "备注": "如需补充资料，当日反馈"},
        {"编号": "本周-02", "事项": "协调推进新增项目验收计划", "负责人": "张",
         "追踪人": "陈", "完成时限": "2026-06-12 前",
         "来源": "本周新增", "备注": "形成项目节点清单"},
    ],
    "footer": {"整理人": "项目组", "抄送": "甲方A项目相关部门"},
}


def set_font(run, size=10.5, bold=False, color=None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), FONT)


def para(doc, text="", size=10.5, bold=False, align=None, line=1.2,
         before=0, after=4, color=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if text:
        set_font(p.add_run(text), size, bold, color)
    return p


def twip_w(cell, twips):
    cell.width = Pt(twips / 20.0)
    tcPr = cell._tc.get_or_add_tcPr()
    tcW = tcPr.find(qn("w:tcW"))
    if tcW is None:
        tcW = OxmlElement("w:tcW")
        tcPr.append(tcW)
    tcW.set(qn("w:w"), str(int(twips)))
    tcW.set(qn("w:type"), "dxa")


def fill_cell(cell, text, bold=False, size=10.5, line=1.2):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.line_spacing = line
    p.paragraph_format.space_after = Pt(1)
    for i, seg in enumerate(str(text).split("\n")):
        if i:
            p = cell.add_paragraph()
            p.paragraph_format.line_spacing = line
        set_font(p.add_run(seg), size, bold)


def fixed_layout(table, widths=None):
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    if widths:
        grid = table._tbl.tblGrid
        for child in list(grid):
            grid.remove(child)
        for width in widths:
            grid_col = OxmlElement("w:gridCol")
            grid_col.set(qn("w:w"), str(int(width)))
            grid.append(grid_col)


VALID_PRIOR_STATUSES = {"已完成", "进行中", "未启动", "阻塞", "取消"}
OPEN_PRIOR_STATUSES = {"进行中", "未启动", "阻塞"}


def responsible(item):

    return item.get("负责人", item.get("责任人", ""))


def join_parts(*parts):
    return "；".join(str(p).strip().rstrip("；") for p in parts if str(p).strip())


def validate_action_links(c):

    prior = c.get("prior_action_items", [])
    current = c.get("action_items", [])

    for i, item in enumerate(prior, 1):
        item.setdefault("编号", f"上周-{i:02d}")
    for i, item in enumerate(current, 1):
        item.setdefault("编号", f"本周-{i:02d}")
        if not prior:
            item.setdefault("来源", "本周新增")

    prior_by_id = {item["编号"]: item for item in prior}
    current_by_id = {item["编号"]: item for item in current}
    if len(prior_by_id) != len(prior):
        raise ValueError("上周待办编号重复")
    if len(current_by_id) != len(current):
        raise ValueError("本周待办编号重复")

    for item in prior:
        status = item.get("进展状态", "")
        if status not in VALID_PRIOR_STATUSES:
            raise ValueError(
                f"{item['编号']} 的进展状态必须是："
                + "/".join(sorted(VALID_PRIOR_STATUSES))
            )
        if not item.get("事项") or not responsible(item) or not item.get("原定时限"):
            raise ValueError(f"{item['编号']} 缺少事项、负责人或原定时限")

    for item in current:
        if not item.get("事项") or not responsible(item) or not item.get("完成时限"):
            raise ValueError(f"{item['编号']} 缺少事项、负责人或完成时限")
        source = item.get("来源", "")
        if prior and not source:
            raise ValueError(f"{item['编号']} 缺少来源（承接上周-XX/本周新增）")
        for prior_id in re.findall(r"上周-\d+", source):
            if prior_id not in prior_by_id:
                raise ValueError(f"{item['编号']} 引用了不存在的 {prior_id}")
            if prior_by_id[prior_id]["进展状态"] in {"已完成", "取消"}:
                raise ValueError(f"{prior_id} 已关闭，不应继续进入 {item['编号']}")

    for item in prior:
        if item["进展状态"] not in OPEN_PRIOR_STATUSES:
            continue
        linked_current = [
            cur_id for cur_id, cur in current_by_id.items()
            if item["编号"] in cur.get("来源", "")
        ]
        if not linked_current:
            raise ValueError(f"{item['编号']} 为开放状态，但未承接到本周待办")
        handling = item.get("本周处理", "")
        if not any(cur_id in handling for cur_id in linked_current):
            raise ValueError(
                f"{item['编号']} 的本周处理须写明承接编号："
                + "、".join(linked_current)
            )


def build_weekly_minutes(c, out):
    validate_action_links(c)
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Mm(30); sec.left_margin = Mm(30)
    sec.right_margin = Mm(30); sec.bottom_margin = Mm(25)
    
    st = doc.styles["Normal"]
    st.font.name = FONT; st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    
    para(doc, c["title"], size=18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER,
         line=2.4, after=2)
    if c.get("subtitle"):
        para(doc, c["subtitle"], size=11, align=WD_ALIGN_PARAGRAPH.CENTER, line=1.2, after=2)
    if c.get("confidential_note"):
        para(doc, c["confidential_note"], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
             line=1.2, after=6, color=(0x88, 0x88, 0x88))

    
    meta = c["meta"]
    t1 = doc.add_table(rows=len(meta), cols=2)
    t1.style = "Table Grid"; t1.autofit = False; fixed_layout(t1, [1700, 7922])
    for i, (k, v) in enumerate(meta.items()):
        fill_cell(t1.rows[i].cells[0], k, bold=True, line=2.0)
        fill_cell(t1.rows[i].cells[1], v, line=2.0)
        twip_w(t1.rows[i].cells[0], 1700)
        twip_w(t1.rows[i].cells[1], 7922)
    para(doc, after=2)

    
    para(doc, "一、会议议程", size=12, bold=True, line=1.4, before=4, after=2)
    for i, a in enumerate(c.get("agenda", []), 1):
        para(doc, f"{i}、{a}", size=10.5, line=1.4, after=1)

    
    para(doc, "二、会议小结与决议", size=12, bold=True, line=1.4, before=6, after=2)
    for s in c.get("sections", []):
        para(doc, s["title"], size=10.5, bold=True, line=1.4, before=3, after=1)
        for b in s.get("bullets", []):
            p = para(doc, "", size=10.5, line=1.3, after=1)
            p.paragraph_format.left_indent = Pt(12)
            set_font(p.add_run("· " + b), 10.5)

    
    para(doc, "三、待办事项跟踪", size=12, bold=True, line=1.4, before=8, after=2)

    prior_items = c.get("prior_action_items", [])
    if prior_items:
        para(doc, "（一）上周待办事项进展", size=10.5, bold=True,
             line=1.3, before=2, after=2)
        prior_cols = ["编号", "上周待办事项", "负责人", "原定时限", "进展状态", "进展说明及本周处理"]
        prior_widths = [1200, 2450, 900, 1250, 1050, 2772]
        prior_table = doc.add_table(rows=1 + len(prior_items), cols=6)
        prior_table.style = "Table Grid"; prior_table.autofit = False
        fixed_layout(prior_table, prior_widths)
        for j, col in enumerate(prior_cols):
            fill_cell(prior_table.rows[0].cells[j], col, bold=True, size=9.5)
            twip_w(prior_table.rows[0].cells[j], prior_widths[j])
        for i, item in enumerate(prior_items, 1):
            vals = [
                item["编号"], item.get("事项", ""), responsible(item),
                item.get("原定时限", ""), item.get("进展状态", ""),
                join_parts(item.get("进展说明", ""), item.get("本周处理", "")),
            ]
            for j, value in enumerate(vals):
                fill_cell(prior_table.rows[i].cells[j], value, size=9.5)
                twip_w(prior_table.rows[i].cells[j], prior_widths[j])
        para(doc, after=2)

    current_subtitle = "（二）本周待办事项" if prior_items else "（一）本周待办事项"
    para(doc, current_subtitle, size=10.5, bold=True, line=1.3, before=2, after=2)
    cols = ["编号", "会议安排事项", "负责人", "追踪人", "完成时限", "来源/备注"]
    widths = [1200, 3000, 900, 900, 1450, 2172]
    items = c.get("action_items", [])
    t2 = doc.add_table(rows=1 + len(items), cols=6)
    t2.style = "Table Grid"; t2.autofit = False; fixed_layout(t2, widths)
    for j, col in enumerate(cols):
        fill_cell(t2.rows[0].cells[j], col, bold=True, size=9.5)
        twip_w(t2.rows[0].cells[j], widths[j])
    for i, it in enumerate(items, 1):
        vals = [
            it["编号"], it.get("事项", ""), responsible(it), it.get("追踪人", ""),
            it.get("完成时限", ""), join_parts(it.get("来源", ""), it.get("备注", "")),
        ]
        for j, v in enumerate(vals):
            fill_cell(t2.rows[i].cells[j], v, size=9.5)
            twip_w(t2.rows[i].cells[j], widths[j])
    para(doc, after=2)

    
    f = c.get("footer", {"整理人": "项目组", "抄送": "项目相关部门"})
    t3 = doc.add_table(rows=1, cols=4)
    fw = [1468, 3343, 1468, 3343]
    t3.style = "Table Grid"; t3.autofit = False; fixed_layout(t3, fw)
    pairs = [("整理人", f.get("整理人", "")), ("抄送", f.get("抄送", ""))]
    cells = t3.rows[0].cells
    fill_cell(cells[0], pairs[0][0], bold=True); fill_cell(cells[1], pairs[0][1])
    fill_cell(cells[2], pairs[1][0], bold=True); fill_cell(cells[3], pairs[1][1])
    for j in range(4):
        twip_w(cells[j], fw[j])

    doc.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", help="内容 JSON 路径")
    ap.add_argument("--out", help="输出 docx 路径")
    ap.add_argument("--sample", action="store_true", help="打印内容 JSON 模板")
    args = ap.parse_args()
    if args.sample:
        print(json.dumps(SAMPLE_CONTENT, ensure_ascii=False, indent=2))
        return
    if not args.content or not args.out:
        print("需 --content 与 --out（或 --sample）", file=sys.stderr); sys.exit(2)
    with open(args.content, encoding="utf-8-sig") as fh:
        c = json.load(fh)
    print(build_weekly_minutes(c, args.out))


if __name__ == "__main__":
    main()
