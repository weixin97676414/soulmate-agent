# -*- coding: utf-8 -*-
"""
build_docx.py — 短视频爆款拆解与二创 报告 Word(.docx) 生成器
============================================================
由「短视频爆款8维拆解与反向二创」技能在最终交付阶段调用（与 build_pdf.py / build_html.py 并列的输出选项之一）。

能力：
  - 后台加载生成软件：缺失 python-docx 时，从官方 PyPI 源（pypi.org）以**固定版本**自动安装到隔离 venv（不污染用户环境，不联网上传任何数据）。
  - 封面页：报告主题 + 产出日期 + 三行尾注（含反馈邮箱，与 PDF/HTML 封面一致；`--brand` 才打印联系方式）。
  - 目录页：插入 Word 原生 TOC 域（打开文档时 Word 自动提示/更新目录，含章节与页码），一眼看清结构、快速定位。
  - 正文：标题 / 段落 / 列表 / 表格 / 代码块 / 引用 全量渲染；正文使用「标题 1/标题 2」样式，导航窗格可直接跳转。
  - 页脚页码：每节页脚插入「第 N 页 · 本文档由 自动生成」，方便打印后翻阅定位。

用法：
  python scripts/build_docx.py --md <报告.md> [--out <输出.docx>] [--title <主题>] [--date <YYYY-MM-DD>] [--brand]
若省略 --out，默认与 --md 同目录、同名换 .docx；省略 --date 用今天；--title 用于封面副标题。
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

BRAND_LINE = "出品 内容仅供参考\n欢迎继续探讨交流：vx：Etvis01 祝您演绎成功！干杯！\n使用反馈请发邮件：chongwuqun@agent.qq.com"
FOOTER = "本文档由 自动生成"
SKILL_NAME = "短视频爆款8维拆解与二创"

# ---------------------------------------------------------------------------
# 1. 后台加载生成软件（python-docx 缺失时从官方 PyPI 固定版本安装）
# ---------------------------------------------------------------------------
def ensure_docx(auto=False):
    """确保 python-docx 可用。缺失时：auto=True 直接安装（需显式授权）；
    auto=False 时仅在交互环境询问确认，非交互环境拒绝自动安装并给出手动命令。"""
    try:
        import docx  # noqa: F401
        return True
    except Exception:
        pkg = "python-docx==1.1.2"
        idx = "https://pypi.org/simple"
        sys.stderr.write(
            "ℹ️ 检测到 Word 依赖缺失，准备从官方源 %s 安装 %s（仅用于渲染）。\n" % (idx, pkg)
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
            _fe.print_error(e, context="自动安装 python-docx", show_tech=True)
            sys.stderr.write("   手动安装命令：%s -m pip install %s -i %s\n" % (sys.executable, pkg, idx))
            raise
        import docx  # noqa: F401
        return True


# ---------------------------------------------------------------------------
# 2. 行内格式（**加粗** / *斜体* / `代码`）→ docx run
# ---------------------------------------------------------------------------
def add_inline_runs(paragraph, text):
    """把含 **加粗** / *斜体* / `代码` 的文本拆成多个 run 追加到 paragraph。"""
    # 先按代码块切分（最高优先级，代码内不解析加粗）
    parts = re.split(r"(`[^`]+`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            r = paragraph.add_run(part[1:-1])
            r.font.name = "Consolas"
            continue
        # 加粗 / 斜体
        seg = re.split(r"(\*\*.+?\*\*|\*.+?\*)", part)
        for s in seg:
            if not s:
                continue
            if s.startswith("**") and s.endswith("**") and len(s) > 2:
                paragraph.add_run(s[2:-2]).bold = True
            elif s.startswith("*") and s.endswith("*") and len(s) > 1 and not s.startswith("**"):
                paragraph.add_run(s[1:-1]).italic = True
            else:
                paragraph.add_run(s)


# ---------------------------------------------------------------------------
# 3. Markdown -> docx
# ---------------------------------------------------------------------------
def parse_markdown_to_docx(doc, md_text):
    from docx.shared import Pt
    lines = md_text.split("\n")
    n = len(lines)
    i = 0
    in_code = False
    code_buf = []

    def flush_code():
        if code_buf:
            p = doc.add_paragraph()
            run = p.add_run("\n".join(code_buf))
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            code_buf.clear()

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                flush_code()
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
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            doc.add_paragraph("─" * 20)
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            txt = m.group(2)
            if level == 1:
                doc.add_heading(txt, level=0)
            elif level == 2:
                doc.add_heading(txt, level=1)   # 进 TOC（标题 1）
            elif level == 3:
                doc.add_heading(txt, level=2)   # 进 TOC（标题 2）
            else:
                doc.add_heading(txt, level=3)
            i += 1
            continue

        mq = re.match(r"^>\s?(.*)$", stripped)
        if mq:
            p = doc.add_paragraph(style="Intense Quote")
            add_inline_runs(p, mq.group(1))
            i += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            rows = []
            for tl in tbl:
                if re.match(r"^\|[\s:|-]+\|$", tl):
                    continue
                rows.append([c.strip() for c in tl.strip().strip("|").split("|")])
            if rows:
                t = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                t.style = "Light Grid Accent 1"
                for ri, r in enumerate(rows):
                    for ci, c in enumerate(r):
                        cell = t.cell(ri, ci)
                        cell.text = ""
                        add_inline_runs(cell.paragraphs[0], c)
            doc.add_paragraph()
            continue

        ml = re.match(r"^(\s*)[-*+]\s+(.*)$", stripped)
        if ml:
            items = []
            while i < n:
                s2 = lines[i].strip()
                m2 = re.match(r"^(\s*)[-*+]\s+(.*)$", s2)
                if not m2:
                    break
                items.append(m2.group(2))
                i += 1
            for it in items:
                p = doc.add_paragraph(style="List Bullet")
                add_inline_runs(p, it)
            continue

        p = doc.add_paragraph()
        add_inline_runs(p, stripped)
        i += 1

    flush_code()


# ---------------------------------------------------------------------------
# 4. 主构建
# ---------------------------------------------------------------------------
def _add_toc_field(document):
    """在文档起始插入 Word 原生 TOC 域（打开时自动提示更新）。"""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "（在 Word 中按 F9 或打开时选择「更新域」以生成目录）"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(placeholder)
    run._r.append(fld_end)


def _set_update_fields(document):
    """设置 settings.xml 的 updateFields，使 Word 打开时自动更新域（含 TOC/页码）。"""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    settings = document.settings.element
    uf = settings.find(qn("w:updateFields"))
    if uf is None:
        uf = OxmlElement("w:updateFields")
        settings.append(uf)
    uf.set(qn("w:val"), "true")


def _add_footer_page_number(document):
    """每节页脚插入「第 N 页 · 品牌署名」。"""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for section in document.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        p.alignment = 1  # CENTER
        # 「第 N 页」
        run = p.add_run("第 ")
        fld_b = OxmlElement("w:fldChar"); fld_b.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = "PAGE"
        fld_e = OxmlElement("w:fldChar"); fld_e.set(qn("w:fldCharType"), "end")
        run._r.append(fld_b); run._r.append(instr); run._r.append(fld_e)
        p.add_run(" 页 · " + FOOTER)


def build_docx(md_path, out_path, title, date_str, brand=False):
    from docx import Document
    from docx.shared import Pt

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = Document()

    # 封面
    c1 = doc.add_paragraph()
    c1.alignment = 1
    r = c1.add_run(SKILL_NAME + " · 拆解报告")
    r.bold = True
    r.font.size = Pt(24)
    c2 = doc.add_paragraph(); c2.alignment = 1
    c2.add_run(title or "爆款视频拆解与二创方案").font.size = Pt(15)
    c3 = doc.add_paragraph(); c3.alignment = 1
    c3.add_run("产出日期 %s" % date_str).font.size = Pt(12)
    if brand:
        cb = doc.add_paragraph(); cb.alignment = 1
        cb.add_run(BRAND_LINE).font.size = Pt(12)
    doc.add_page_break()

    # 目录页
    toc_title = doc.add_heading("目录", level=1)
    _add_toc_field(doc)
    doc.add_page_break()

    # 正文
    parse_markdown_to_docx(doc, md_text)

    # 页脚页码（所有节）
    _add_footer_page_number(doc)
    # 打开时自动更新域（TOC + 页码）
    _set_update_fields(doc)

    doc.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成拆解报告 Word(.docx) 文档（含封面/目录/页码）")
    ap.add_argument("--md", required=True, help="输入 Markdown 报告路径")
    ap.add_argument("--out", default=None, help="输出 docx 路径（默认同名 .docx）")
    ap.add_argument("--title", default=None, help="封面主题（报告副标题）")
    ap.add_argument("--date", default=None, help="产出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--yes", action="store_true",
                    help="跳过安装确认（仅交互环境确认后由脚本显式触发）")
    ap.add_argument("--brand", action="store_true",
                    help="在封面打印品牌署名行（含联系方式）；默认不打印")
    args = ap.parse_args()

    ensure_docx(auto=args.yes)

    md_path = os.path.abspath(args.md)
    if not os.path.exists(md_path):
        _fe.print_error(
            FileNotFoundError(md_path),
            context="生成 Word",
            hints=[
                "确认路径里有 --md 指定的 .md 文件",
                "如使用相对路径，确认当前命令行工作目录",
                "路径含空格或中文时建议加引号：「\"我的报告.md\"」",
            ],
        )
        sys.exit(_fe.EXIT_USER)

    out_path = args.out or (os.path.splitext(md_path)[0] + ".docx")
    date_str = args.date or date.today().strftime("%Y-%m-%d")

    try:
        build_docx(md_path, out_path, args.title, date_str, brand=args.brand)
    except SystemExit:
        raise
    except Exception as e:
        _fe.print_error(e, context="生成 Word")
        sys.exit(_fe.suggest_exit_code(e))

    size = os.path.getsize(out_path)
    sys.stdout.write("✅ Word 已生成：%s （%.1f KB）\n" % (out_path, size / 1024))


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
