#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xhs_pdf.py — 把 HTML / Markdown 报告渲染成 PDF（A4，可打印归档）。

为什么自己写而不用现成转换库：
  1. 报告是「单文件 HTML + 内联 SVG 图表」，图片是本地绝对路径。
     wkhtmltopdf / weasyprint 对 Windows 绝对路径、中文字体、CSS 变量的支持都很差。
  2. 报告的配色用 CSS 变量 + `prefers-color-scheme` 做明暗自适应，
     直接打印会跟随系统主题，夜间模式的报告会印出一整张黑纸。
     这里用 Playwright 的 `emulate_media(color_scheme=...)` 强制浅色变量。
  3. 需要控制分页（卡片/表格不被切断）、加页眉页脚页码。

用法：
  python xhs_pdf.py --html report.html --out report.pdf
  python xhs_pdf.py --dir  <案例目录>            # 自动找 report.html / report.md
  python xhs_pdf.py --md   report.md  --out r.pdf --title "账号拆解报告"
  python xhs_pdf.py --html report.html --landscape
  python xhs_pdf.py --html report.html --theme dark
"""
from __future__ import annotations

import argparse
import html as html_mod
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xhs_common import get_logger  

log = get_logger("xhs_pdf")

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "report_template.html"

SRC_RE = re.compile(r"""src\s*=\s*(['"])(.+?)\1""", re.I)





PRINT_CSS = """
<style id="xhs-print-fix">
@page { size: __PAGESIZE__ __ORIENT__; margin: 15mm 13mm 17mm; }
html, body { background:#fff !important; }
* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }

/* 报告模板是流式布局(max-width:1180px)，打印时纸宽固定，去掉外框让内容吃满 */
.wrap { max-width:none !important; margin:0 !important; padding:0 !important; }

/* 关键：A4 纸宽约 794px，会误触发模板里的 @media(max-width:900px) 响应式断点，
   导致 5 列指标卡全塌成 2 列、一页放不下。这里强制按纸宽重排。 */
.g5 { grid-template-columns:repeat(3,1fr) !important; }
.g4 { grid-template-columns:repeat(2,1fr) !important; }
.g3 { grid-template-columns:repeat(3,1fr) !important; }
.g2 { grid-template-columns:repeat(2,1fr) !important; }
.gallery { grid-template-columns:repeat(4,1fr) !important; }

/* 纸面字号微调，避免单元格内换行撑破卡片 */
body { font-size:13px !important; line-height:1.65 !important; }
h1 { font-size:22px !important; }
h2 { font-size:17px !important; margin:20px 0 10px !important; }
h3 { font-size:14px !important; margin:16px 0 8px !important; }
.card .v { font-size:19px !important; }
table { font-size:11.5px !important; }
th, td { padding:6px 7px !important; }

/* 分页控制：标题不落单、小块不被切断、表头每页重复。
   注意 .panel 不能加 break-inside:avoid —— 长 panel（整张评论表）会被整体
   推到下一页，留下大半页空白。只保护小块。 */
h1, h2, h3 { break-after:avoid; break-inside:avoid; page-break-after:avoid; }
.card, figure, .todo, .badge, svg { break-inside:avoid; page-break-inside:avoid; }
tr, td, th { break-inside:avoid; page-break-inside:avoid; }
thead { display:table-header-group; }
img { max-width:100%; }
a { color:inherit; text-decoration:none; }
p { orphans:2; widows:2; }
</style>
"""

HEADER_TPL = """
<div style="width:100%;font-size:8px;color:#8a93a3;padding:0 13mm;
            font-family:'Microsoft YaHei','PingFang SC',sans-serif;
            display:flex;justify-content:space-between;">
  <span>__TITLE__</span>
  <span>小红书账号深度拆解</span>
</div>
"""

FOOTER_TPL = """
<div style="width:100%;font-size:8px;color:#8a93a3;padding:0 13mm;
            font-family:'Microsoft YaHei','PingFang SC',sans-serif;
            display:flex;justify-content:space-between;">
  <span>__DATE__</span>
  <span>第 <span class="pageNumber"></span> / <span class="totalPages"></span> 页</span>
</div>
"""





def _compress_copy(p: Path, cache_dir: Path, max_w: int = 440, quality: int = 82) -> Path | None:



    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        out = cache_dir / (hashlib.md5(str(p).encode("utf-8")).hexdigest()[:12] + ".jpg")
        if out.exists() and out.stat().st_size > 0:
            return out
        with Image.open(p) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w > max_w:
                im = im.resize((max_w, round(h * max_w / w)), Image.LANCZOS)
            im.save(out, "JPEG", quality=quality, optimize=True)
        return out
    except Exception as e:
        log.warning("图片压缩失败，使用原图：%s（%s）", p.name, e)
        return None


def fix_local_images(
    html: str, base: Path, compress: bool = False, cache_dir: Path | None = None
) -> str:

    seen: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        q, raw = m.group(1), m.group(2)
        raw = html_mod.unescape(raw).strip()
        if raw.startswith(("http://", "https://", "data:", "file:")):
            return m.group(0)
        if raw in seen:
            return f"src={q}{seen[raw]}{q}"

        p = Path(raw)
        if not p.is_absolute():
            p = (base / p).resolve()
        if not (p.exists() and p.is_file()):
            log.warning("图片缺失，PDF 中将留空：%s", raw)
            return m.group(0)

        target = p
        if compress and cache_dir is not None:
            
            cp = _compress_copy(p, cache_dir)
            if cp is not None:
                target = cp
        try:
            uri = target.as_uri()
        except Exception:
            uri = "file:///" + str(target).replace("\\", "/")
        seen[raw] = uri
        return f"src={q}{uri}{q}"

    html = SRC_RE.sub(repl, html)
    
    html = re.sub(r"""loading\s*=\s*(['"])lazy\1""", "loading='eager'", html, flags=re.I)
    return html


def inject_print_css(html: str, page_size: str, landscape: bool) -> str:
    css = PRINT_CSS.replace("__PAGESIZE__", page_size)
    css = css.replace("__ORIENT__", "landscape" if landscape else "portrait")
    if re.search(r"</head\s*>", html, re.I):
        return re.sub(r"</head\s*>", css + "</head>", html, count=1, flags=re.I)
    return css + html


def md_to_standalone_html(md: str, title: str) -> str:

    from xhs_report import md_to_html  

    style = ""
    if TEMPLATE.exists():
        tpl = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r"<style>(.*?)</style>", tpl, re.S)
        if m:
            style = f"<style>{m.group(1)}</style>"
    body = md_to_html(md)
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{html_mod.escape(title)}</title>{style}</head>"
        f"<body><div class='wrap'>{body}</div></body></html>"
    )





def render_pdf(
    html: str,
    out: Path,
    title: str,
    page_size: str = "A4",
    landscape: bool = False,
    theme: str = "light",
    base_dir: Path | None = None,
) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "缺少 playwright。先跑一次环境自检：\n"
            f"  {sys.executable} {SKILL_DIR / 'scripts' / 'bootstrap.py'} --install"
        )

    base_dir = base_dir or out.parent
    assets = out.parent / ".pdf_assets"
    html = fix_local_images(html, base_dir, compress=True, cache_dir=assets)
    html = inject_print_css(html, page_size, landscape)

    tmp = out.with_suffix(".print.html")
    tmp.write_text(html, encoding="utf-8")

    date_str = datetime.now().strftime("%Y-%m-%d")
    header = HEADER_TPL.replace("__TITLE__", html_mod.escape(title))
    footer = FOOTER_TPL.replace("__DATE__", date_str)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--allow-file-access-from-files", "--font-render-hinting=none"]
        )
        page = browser.new_page()
        
        page.emulate_media(color_scheme=theme)
        page.goto(tmp.as_uri(), wait_until="load")

        
        try:
            page.wait_for_function(
                "() => Array.from(document.images).every(i => i.complete)",
                timeout=20000,
            )
        except Exception:
            log.warning("部分图片加载超时，继续导出（可能留空）")

        page.pdf(
            path=str(out),
            format=page_size,
            landscape=landscape,
            print_background=True,
            display_header_footer=True,
            header_template=header,
            footer_template=footer,
            margin={"top": "15mm", "bottom": "17mm", "left": "13mm", "right": "13mm"},
        )
        browser.close()

    try:
        tmp.unlink(missing_ok=True)
        if assets.exists():
            import shutil
            shutil.rmtree(assets, ignore_errors=True)
    except Exception:
        pass
    return out


def pdf_pages(path: Path) -> int:
    try:
        data = path.read_bytes()
        return len(re.findall(rb"/Type\s*/Page[^s]", data))
    except Exception:
        return -1



def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="把小红书账号拆解报告（HTML/Markdown）导出为 PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--html", help="输入 report.html")
    src.add_argument("--md", help="输入 report.md（会套用报告样式表）")
    src.add_argument("--dir", help="案例目录，自动找 report.html / report.md")
    ap.add_argument("--out", help="输出 PDF 路径（默认与输入同目录同名 .pdf）")
    ap.add_argument("--title", default="小红书账号深度拆解报告", help="页眉标题")
    ap.add_argument("--page-size", default="A4", choices=["A4", "Letter", "A3", "Legal"])
    ap.add_argument("--landscape", action="store_true", help="横向（宽表格多时更合适）")
    ap.add_argument("--theme", default="light", choices=["light", "dark"],
                    help="light=白底打印（推荐）；dark=保留深色配色")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    if args.dir:
        d = Path(args.dir).expanduser().resolve()
        if not d.is_dir():
            raise SystemExit(f"目录不存在：{d}")
        cand = next((d / n for n in ("report.html", "report.md") if (d / n).exists()), None)
        if not cand:
            raise SystemExit(f"目录里没找到 report.html 或 report.md：{d}")
        source, base_dir = cand, d
    elif args.html:
        source = Path(args.html).expanduser().resolve()
        base_dir = source.parent
    else:
        source = Path(args.md).expanduser().resolve()
        base_dir = source.parent

    if not source.exists():
        raise SystemExit(f"输入文件不存在：{source}")

    out = Path(args.out).expanduser().resolve() if args.out else source.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() in (".md", ".markdown"):
        html = md_to_standalone_html(source.read_text(encoding="utf-8"), args.title)
    else:
        html = source.read_text(encoding="utf-8")

    log.info("渲染 %s → %s", source.name, out.name)
    render_pdf(
        html, out,
        title=args.title,
        page_size=args.page_size,
        landscape=args.landscape,
        theme=args.theme,
        base_dir=base_dir,
    )

    size_kb = out.stat().st_size / 1024
    pages = pdf_pages(out)
    log.info("完成：%s  (%.1f KB, %s 页)", out, size_kb, pages if pages > 0 else "?")
    print(f"\nPDF 已生成：{out}")
    print(f"  {size_kb:.1f} KB · {'约 ' + str(pages) + ' 页' if pages > 0 else '页数未知'}")
    return 0


if __name__ == "__main__":
    from xhs_env import ensure_ready
    ensure_ready(need_browser=True)      
    sys.exit(main())
