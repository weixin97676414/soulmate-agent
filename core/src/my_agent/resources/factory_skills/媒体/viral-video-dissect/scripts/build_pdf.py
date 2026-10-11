# -*- coding: utf-8 -*-
"""
build_pdf.py — 短视频爆款拆解与二创 报告 PDF 生成器
========================================================
由「短视频爆款8维拆解与二创」技能在最终交付阶段调用。

能力：
  - 后台加载生成软件：缺失 reportlab 时，从官方 PyPI 源（pypi.org）以**固定版本**自动安装到隔离 venv（不污染用户环境，不联网上传任何数据）。
  - 中文渲染：自动注册 Windows 中文字体（微软雅黑 msyh.ttc 优先，回退黑体/宋体）。
  - 封面页：报告主题 + 产出日期 + 三行尾注（第一行「出品 内容仅供参考」，第二行「欢迎继续探讨交流：vx：Etvis01 祝您演绎成功！干杯！」，第三行「使用反馈请发邮件：chongwuqun@agent.qq.com」）——兼作对外宣传交流窗口。
  - 目录页：封面之后自动生成，依据 Markdown 报告的标题层级（## 一级节、### 二级节）抽取目录与页码，让用户一眼看清结构、快速定位内容。
  - 页脚/结尾：每页固定「本文档由 自动生成」；每页右下角附「第 N 页」页码（封面起计），方便打印后翻阅定位。
  - 正文：把技能产出的 Markdown 报告渲染为专业排版 PDF（标题/段落/列表/表格/代码块/引用）。
    ⚠️ 因此**报告 Markdown 本身需条理清晰、层级一致**：用 `##` 标主节、`###` 标子节，目录页才能生成有意义的内容导航。

用法：
  python scripts/build_pdf.py --md <报告.md> [--out <输出.pdf>] [--title <主题>] [--date <YYYY-MM-DD>]
若省略 --out，默认与 --md 同目录、同名换 .pdf；省略 --date 用今天；--title 用于封面副标题。
"""
import argparse
import os
import re
import sys
import subprocess
from datetime import date

# 统一错误友好化层（v2.21 新增）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _friendly_error as _fe  # noqa: E402

BRAND_LINE = "出品 内容仅供参考<br/>欢迎继续探讨交流：vx：Etvis01 祝您演绎成功！干杯！<br/>使用反馈请发邮件：chongwuqun@agent.qq.com"
FOOTER = "本文档由 自动生成"
SKILL_NAME = "短视频爆款8维拆解与二创"

# 标题锚点：带 TOC 元信息的段落（供目录页收集页码）
from reportlab.platypus import Paragraph as _Paragraph


class TOCParagraph(_Paragraph):
    def __init__(self, text, style, toc_level=None, toc_text=None, toc_key=None, **kw):
        super().__init__(text, style, **kw)
        self._toc_level = toc_level      # 目录层级（0=一级节，1=二级节）
        self._toc_text = toc_text        # 目录显示的纯文本
        self._toc_key = toc_key          # 唯一键，用于去重与定位


# ---------------------------------------------------------------------------
# 1. 后台加载生成软件（reportlab 缺失时从官方 PyPI 固定版本安装）
# ---------------------------------------------------------------------------
def ensure_reportlab(auto=False):
    """确保 reportlab 可用。缺失时：auto=True 直接安装（需显式授权）；
    auto=False 时仅在交互环境询问确认，非交互环境拒绝自动安装并给出手动命令。"""
    try:
        import reportlab  # noqa: F401
        return reportlab.Version
    except Exception:
        # 仅从官方 PyPI 源（pypi.org）、以固定版本安装到当前隔离 venv；
        # 不指定第三方镜像、不回退任意源，不联网上传任何数据。
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
        import reportlab  # noqa: F401
        return reportlab.Version


# ---------------------------------------------------------------------------
# 2. 注册中文字体（多候选回退）
# ---------------------------------------------------------------------------
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
        normal = "Helvetica"  # 无中文字体时仍可生成（中文会显示为方框）

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


# ---------------------------------------------------------------------------
# 3. Markdown -> reportlab flowables
# ---------------------------------------------------------------------------
def md_inline(text):
    """行内格式：转义 HTML 特殊字符后处理 **加粗** / *斜体*。"""
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
    toc_counter = [0]          # 目录条目唯一键计数器
    lines = md_text.split("\n")
    i = 0
    n = len(lines)
    in_code = False
    code_buf = []

    def flush_code():
        if code_buf:
            # 用 Paragraph + <br/> 保留换行，避免 Preformatted 对 CJK 字体支持不佳导致黑方块
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

        # 代码块
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

        # 去 HTML 注释
        if stripped.startswith("<!--"):
            i += 1
            continue

        # 空行
        if stripped == "":
            flow.append(Spacer(1, 4))
            i += 1
            continue

        # 分隔线
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flow.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cccccc"),
                                   spaceBefore=6, spaceAfter=6))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            raw_text = m.group(2)
            txt = md_inline(raw_text)
            st = {1: h1, 2: h2, 3: h3, 4: h4}.get(level, body)
            # ##(level2) 与 ###(level3) 进目录（level2→目录一级，level3→目录二级）；
            # # 报告标题与 #### 过深标题不进目录，避免与封面重复/过碎。
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

        # 引用
        mq = re.match(r"^>\s?(.*)$", stripped)
        if mq:
            flow.append(Paragraph(md_inline(mq.group(1)), quote_style))
            i += 1
            continue

        # 表格：连续以 | 开头且含分隔行
        if stripped.startswith("|") and "|" in stripped[1:]:
            tbl_lines = []
            while i < n and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i].strip())
                i += 1
            # 过滤分隔行 |---|
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

        # 列表
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

        # 普通段落
        flow.append(Paragraph(md_inline(stripped), body))
        i += 1

    flush_code()
    return flow


# ---------------------------------------------------------------------------
# 4. 主构建
# ---------------------------------------------------------------------------
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

    # 封面
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
        # 页脚（底部居中）：品牌署名
        canvas.drawCentredString(page_w / 2, 11 * mm, FOOTER)
        # 页码（底部右侧）：第 N 页，方便打印后翻阅定位
        canvas.drawRightString(page_w - margin, 11 * mm, "第 %d 页" % doc.page)
        canvas.restoreState()

    # 目录页（封面之后、正文之前）：依据报告标题层级自动抽取章节与页码
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
                # 为每个目录条目生成同名书签锚点，供目录页超链接跳转
                self.canv.bookmarkPage(flowable._toc_key)

    doc = _Doc(
        out_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=18 * mm,
        title=title or SKILL_NAME, author="",
    )
    frame = Frame(margin, 18 * mm, avail, page_h - margin - 18 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])

    # 封面 → 目录页 → 正文（multiBuild 两遍渲染以解析目录页码）
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
    """拒绝在系统 Python 中执行，强制要求隔离 venv。"""
    if sys.prefix == sys.base_prefix:
        sys.stderr.write(
            "⛔ 必须在隔离 venv 内运行（拒绝系统 Python）。\n"
            "请使用：python\n"
        )
        raise SystemExit(4)


if __name__ == "__main__":
    _check_isolated_venv()
    main()
