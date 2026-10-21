# -*- coding: utf-8 -*-


















import argparse
import os
import re
import sys
import subprocess
from datetime import date


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _friendly_error as _fe  

BRAND_LINE = "出品 内容仅供参考<br/>欢迎继续探讨交流：vx：Etvis01 祝您演绎成功！干杯！<br/>使用反馈请发邮件：chongwuqun@agent.qq.com"
FOOTER = "本文档由 自动生成"
SKILL_NAME = "短视频爆款8维拆解与二创"


from reportlab.platypus import Paragraph as _Paragraph


class TOCParagraph(_Paragraph):
    def __init__(self, text, style, toc_level=None, toc_text=None, toc_key=None, **kw):
        super().__init__(text, style, **kw)
        self._toc_level = toc_level      
        self._toc_text = toc_text        
        self._toc_key = toc_key          





def ensure_reportlab(auto=False):


    try:
        import reportlab  
        return reportlab.Version
    except Exception:
        
        
        pkg = "reportlab==4.2.5"
        idx = "https://pypi.org/simple"
        sys.stderr.write(
            "ℹ️ 检测到 PDF 依赖缺失，准备从官方源 %s 安装 %s（约 2MB，仅用于渲染）。\n"
            % (idx, pkg)
        )
        if not auto:
            if not sys.stdin.isatty():
                sys.stderr.write(
                    "⛔ 非交互环境已拒绝自动安装。请手动执行：\n"
                    "  %s -m pip install %s -i %s\n" % (sys.executable, pkg, idx)
                )
                raise SystemExit(2)
            ans = input("确认从官方源安装 %s 吗？(y/N): " % pkg).strip().lower()
            if ans not in ("y", "yes"):
                sys.stderr.write("已取消安装。请手动安装后重跑。\n")
                raise SystemExit(3)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg,
                 "-i", idx, "--no-cache-dir", "-q"],
                check=True,
            )
        except Exception as e:
            _fe.print_error(e, context="自动安装 reportlab", show_tech=True)
            sys.stderr.write("   手动安装命令：%s -m pip install %s -i %s\n" % (sys.executable, pkg, idx))
            raise
        import reportlab  
        return reportlab.Version





def register_chinese_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    candidates = [
        (r"C:/Windows/Fonts/msyh.ttc", 0),
        (r"C:/Windows/Fonts/simhei.ttf", 0),
        (r"C:/Windows/Fonts/simsun.ttc", 0),
        (os.path.join(os.path.expanduser("~"), "venv", "binaries", "python",
                       "envs", "default", "Lib", "site-packages", "reportlab",
                       "fonts", "Vera.ttf"), 0),
    ]
    normal = None
    for path, idx in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CJK", path, subfontIndex=idx))
                normal = "CJK"
                break
            except Exception:
                continue
    if normal is None:
        normal = "Helvetica"  

    bold = normal
    bold_candidates = [(r"C:/Windows/Fonts/msyhbd.ttc", 0)]
    for path, idx in bold_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CJKb", path, subfontIndex=idx))
                bold = "CJKb"
                break
            except Exception:
                pass
    try:
        registerFontFamily(normal, normal=normal, bold=bold, italic=normal, boldItalic=bold)
    except Exception:
        pass
    return normal, bold





def md_inline(text):

    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


def parse_markdown(md_text, styles):
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, Preformatted,
        ListFlowable, ListItem, HRFlowable,
    )
    from reportlab.lib import colors

    body = styles["body"]
    h1, h2, h3, h4 = styles["h1"], styles["h2"], styles["h3"], styles["h4"]
    code_style = styles["code"]
    quote_style = styles["quote"]
    avail = styles["_avail"]

    flow = []
    toc_counter = [0]          
    lines = md_text.split("\n")
    i = 0
    n = len(lines)
    in_code = False
    code_buf = []

    def flush_code():
        if code_buf:
            
            out_lines = []
            for ln in code_buf:
                esc = ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                stripped = esc.lstrip(" ")
                leading = len(esc) - len(stripped)
                out_lines.append("&nbsp;" * leading + stripped)
            flow.append(Paragraph("<br/>".join(out_lines), code_style))
            flow.append(Spacer(1, 4))

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        
        if stripped.startswith("```"):
            if in_code:
                flush_code()
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(raw.rstrip("\n"))
            i += 1
            continue

        
        if stripped.startswith("<!--"):
            i += 1
            continue

        
        if stripped == "":
            flow.append(Spacer(1, 4))
            i += 1
            continue

        
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flow.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cccccc"),
                                   spaceBefore=6, spaceAfter=6))
            i += 1
            continue

        
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            raw_text = m.group(2)
            txt = md_inline(raw_text)
            st = {1: h1, 2: h2, 3: h3, 4: h4}.get(level, body)
            
            
            if level in (2, 3):
                toc_counter[0] += 1
                plain = re.sub(r"<[^>]+>", "", raw_text)
                flow.append(TOCParagraph(
                    txt, st,
                    toc_level=level - 2,
                    toc_text=plain,
                    toc_key="h%d" % toc_counter[0],
                ))
            else:
                flow.append(Paragraph(txt, st))
            i += 1
            continue

        
        mq = re.match(r"^>\s?(.*)$", stripped)
        if mq:
            flow.append(Paragraph(md_inline(mq.group(1)), quote_style))
            i += 1
            continue

        
        if stripped.startswith("|") and "|" in stripped[1:]:
            tbl_lines = []
            while i < n and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i].strip())
                i += 1
            
            rows = []
            for tl in tbl_lines:
                if re.match(r"^\|[\s:|-]+\|$", tl):
                    continue
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                rows.append(cells)
            if rows:
                ncol = max(len(r) for r in rows)
                for r in rows:
                    while len(r) < ncol:
                        r.append("")
                data = [[Paragraph(md_inline(c), styles["cell"]) for c in r] for r in rows]
                col_w = avail / ncol
                t = Table(data, colWidths=[col_w] * ncol, repeatRows=1)
                t.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3a4a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), styles["bold"]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
                ]))
                flow.append(t)
                flow.append(Spacer(1, 6))
            continue

        
        ml = re.match(r"^(\s*)[-*+]\s+(.*)$", stripped)
        if ml:
            items = []
            while i < n:
                s2 = lines[i].strip()
                m2 = re.match(r"^(\s*)[-*+]\s+(.*)$", s2)
                if not m2:
                    break
                items.append(ListItem(Paragraph(md_inline(m2.group(2)), body), leftIndent=10))
                i += 1
            flow.append(ListFlowable(items, bulletType="bullet", start="•",
                                     leftIndent=12, bulletColor=colors.HexColor("#2f3a4a")))
            flow.append(Spacer(1, 4))
            continue

        
        flow.append(Paragraph(md_inline(stripped), body))
        i += 1

    flush_code()
    return flow





def build_pdf(md_path, out_path, title, date_str, brand=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    normal, bold = register_chinese_font()

    margin = 18 * mm
    page_w, page_h = A4
    avail = page_w - 2 * margin

    styles = {
        "body": ParagraphStyle("body", fontName=normal, fontSize=9.5, leading=15,
                               wordWrap="CJK", textColor=colors.HexColor("#222222")),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=15, leading=20, spaceBefore=10,
                             spaceAfter=6, textColor=colors.HexColor("#1a1a1a")),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=17, spaceBefore=8,
                             spaceAfter=4, textColor=colors.HexColor("#1f2d3d")),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=11, leading=15, spaceBefore=6,
                             spaceAfter=3, textColor=colors.HexColor("#2f3a4a")),
        "h4": ParagraphStyle("h4", fontName=bold, fontSize=10, leading=14, spaceBefore=4,
                             spaceAfter=2, textColor=colors.HexColor("#333333")),
        "code": ParagraphStyle("code", fontName=normal, fontSize=8.5, leading=12,
                               backColor=colors.HexColor("#f2f2f2"), leftIndent=6,
                               textColor=colors.HexColor("#333333"), wordWrap="CJK"),
        "quote": ParagraphStyle("quote", fontName=normal, fontSize=9.5, leading=14, leftIndent=10,
                               textColor=colors.HexColor("#555555"), wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=normal, fontSize=7.6, leading=10, wordWrap="CJK"),
        "bold": bold,
        "_avail": avail,
    }

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    body_flow = parse_markdown(md_text, styles)

    
    cover_title = ParagraphStyle("ct", fontName=bold, fontSize=22, leading=28,
                                 alignment=TA_CENTER, textColor=colors.HexColor("#1a1a1a"))
    cover_sub = ParagraphStyle("cs", fontName=normal, fontSize=13, leading=18,
                              alignment=TA_CENTER, textColor=colors.HexColor("#2f3a4a"))
    cover_meta = ParagraphStyle("cm", fontName=normal, fontSize=10.5, leading=15,
                               alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    cover_brand = ParagraphStyle("cb", fontName=normal, fontSize=10, leading=15,
                                alignment=TA_CENTER, textColor=colors.HexColor("#b8860b"))

    cover = [
        Spacer(1, 52 * mm),
        Paragraph(SKILL_NAME + " · 拆解报告", cover_title),
        Spacer(1, 8 * mm),
        Paragraph(title or "爆款视频拆解与二创方案", cover_sub),
        Spacer(1, 14 * mm),
        Paragraph("产出日期 %s" % date_str, cover_meta),
    ]
    if brand:
        cover.append(Spacer(1, 5 * mm))
        cover.append(Paragraph(BRAND_LINE, cover_brand))

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(normal, 8)
        canvas.setFillColor(colors.HexColor("#999999"))
        
        canvas.drawCentredString(page_w / 2, 11 * mm, FOOTER)
        
        canvas.drawRightString(page_w - margin, 11 * mm, "第 %d 页" % doc.page)
        canvas.restoreState()

    
    toc_title_style = ParagraphStyle("toct", fontName=bold, fontSize=16, leading=22,
                                     spaceAfter=10, textColor=colors.HexColor("#1a1a1a"))
    toc_heading = Paragraph("目录", toc_title_style)
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("tocL0", fontName=normal, fontSize=10.5, leading=19,
                       textColor=colors.HexColor("#1a1a1a")),
        ParagraphStyle("tocL1", fontName=normal, fontSize=9.5, leading=16,
                       leftIndent=16, textColor=colors.HexColor("#2f3a4a")),
    ]

    class _Doc(BaseDocTemplate):
        def afterFlowable(self, flowable):
            lvl = getattr(flowable, "_toc_level", None)
            if lvl is not None:
                self.notify("TOCEntry", (lvl, flowable._toc_text, self.page, flowable._toc_key))
                
                self.canv.bookmarkPage(flowable._toc_key)

    doc = _Doc(
        out_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=18 * mm,
        title=title or SKILL_NAME, author="",
    )
    frame = Frame(margin, 18 * mm, avail, page_h - margin - 18 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])

    
    story = cover + [PageBreak()] + [toc_heading, Spacer(1, 4), toc, PageBreak()] + body_flow
    doc.multiBuild(story)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成拆解报告 PDF（含封面与署名）")
    ap.add_argument("--md", required=True, help="输入 Markdown 报告路径")
    ap.add_argument("--out", default=None, help="输出 PDF 路径（默认同名 .pdf）")
    ap.add_argument("--title", default=None, help="封面主题（报告副标题）")
    ap.add_argument("--date", default=None, help="产出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--yes", action="store_true",
                    help="跳过安装确认（仅交互环境确认后由脚本显式触发）")
    ap.add_argument("--brand", action="store_true",
                    help="在封面打印品牌署名行（含联系方式）；默认不打印，避免对外分发时暴露联系方式")
    args = ap.parse_args()

    ensure_reportlab(auto=args.yes)

    md_path = os.path.abspath(args.md)
    if not os.path.exists(md_path):
        _fe.print_error(
            FileNotFoundError(md_path),
            context="生成 PDF",
            hints=[
                "确认路径里有 --md 指定的 .md 文件",
                "如使用相对路径，确认当前命令行工作目录",
                "路径含空格或中文时建议加引号：「\"我的报告.md\"」",
            ],
        )
        sys.exit(_fe.EXIT_USER)

    out_path = args.out or (os.path.splitext(md_path)[0] + ".pdf")
    date_str = args.date or date.today().strftime("%Y-%m-%d")

    try:
        build_pdf(md_path, out_path, args.title, date_str, brand=args.brand)
    except SystemExit:
        raise
    except Exception as e:
        _fe.print_error(e, context="生成 PDF")
        sys.exit(_fe.suggest_exit_code(e))

    size = os.path.getsize(out_path)
    sys.stdout.write("✅ PDF 已生成：%s （%.1f KB）\n" % (out_path, size / 1024))


def _check_isolated_venv():

    if sys.prefix == sys.base_prefix:
        sys.stderr.write(
            "⛔ 必须在隔离 venv 内运行（拒绝系统 Python）。\n"
            "请使用：python\n"
        )
        raise SystemExit(4)


if __name__ == "__main__":
    _check_isolated_venv()
    main()
