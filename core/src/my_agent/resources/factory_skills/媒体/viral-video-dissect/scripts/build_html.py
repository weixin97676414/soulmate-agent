# -*- coding: utf-8 -*-


















import argparse
import os
import re
import sys
from datetime import date
from html import escape


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _friendly_error as _fe  

BRAND_LINE = "出品 内容仅供参考<br/>欢迎继续探讨交流：vx：Etvis01 祝您演绎成功！干杯！<br/>使用反馈请发邮件：chongwuqun@agent.qq.com"
FOOTER = "本文档由 自动生成"
SKILL_NAME = "短视频爆款8维拆解与二创"

CSS = """
:root { --ink:#222; --dark:#1a1a1a; --navy:#2f3a4a; --gold:#b8860b; --line:#cccccc; --zebra:#f4f6f8; }
* { box-sizing: border-box; }
body { margin:0; font-family: "Microsoft YaHei","PingFang SC","Hiragino Sans GB","Heiti SC",sans-serif;
       color: var(--ink); line-height: 1.7; font-size: 15px; background:#fff; }
.wrap { max-width: 880px; margin: 0 auto; padding: 24px 28px 48px; }
/* 封面 */
.cover { height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center;
         text-align: center; page-break-after: always; }
.cover h1 { font-size: 30px; color: var(--dark); margin: 0 0 10px; font-weight: 700; }
.cover .sub { font-size: 20px; color: var(--navy); margin: 0 0 28px; }
.cover .date { font-size: 15px; color: #555; }
.cover .brand { margin-top: 22px; font-size: 15px; color: var(--gold); line-height: 1.8; }
/* 目录 */
.toc { page-break-after: always; }
.toc h2 { font-size: 22px; border-bottom: 2px solid var(--navy); padding-bottom: 8px; }
.toc ol { list-style: none; padding-left: 0; }
.toc li.lv0 { font-size: 16px; font-weight: 700; margin: 12px 0 4px; color: var(--dark); }
.toc li.lv1 { font-size: 14px; padding-left: 22px; margin: 3px 0; color: var(--navy); }
.toc a { color: inherit; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
/* 正文 */
h1 { font-size: 23px; color: var(--dark); margin: 22px 0 8px; }
h2 { font-size: 20px; color: var(--navy); margin: 20px 0 6px; border-left: 4px solid var(--navy); padding-left: 10px; }
h3 { font-size: 17px; color: var(--navy); margin: 16px 0 5px; }
h4 { font-size: 15px; color: #333; margin: 12px 0 4px; }
p { margin: 8px 0; }
ul { padding-left: 22px; margin: 8px 0; }
blockquote { margin: 8px 0; padding: 6px 14px; border-left: 4px solid #ddd; color: #555; background: #fafafa; }
pre { background: #f2f2f2; padding: 10px 12px; border-radius: 4px; overflow-x: auto; font-size: 13px;
      white-space: pre-wrap; word-break: break-all; }
code { font-family: Consolas,Menlo,monospace; font-size: 13px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
th, td { border: 1px solid #bbb; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: var(--navy); color: #fff; }
tbody tr:nth-child(even) { background: var(--zebra); }
hr { border: none; border-top: 1px solid var(--line); margin: 14px 0; }
.foot { margin-top: 36px; padding-top: 12px; border-top: 1px solid var(--line);
        text-align: center; color: #999; font-size: 13px; }
/* 屏幕浏览静态页脚 */
.screen-foot { display: block; }
/* 打印：用分页媒体自动生成页码 + 品牌页脚，隐藏屏幕静态页脚 */
@page { size: A4; margin: 18mm;
  @bottom-center { content: "第 " counter(page) " 页 · 本文档由 自动生成"; }
}
@media print {
  .cover { height: auto; min-height: 247mm; }
  .screen-foot { display: none; }
}
"""


def md_inline(text):

    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def parse_markdown(md_text):

    lines = md_text.split("\n")
    n = len(lines)
    body = []
    toc = []
    i = 0
    sec = [0]
    in_code = False
    code_buf = []

    def flush_code():
        if code_buf:
            body.append("<pre>%s</pre>" % escape("\n".join(code_buf)))
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
            body.append("<hr/>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            txt_esc = md_inline(m.group(2))
            plain = re.sub(r"<[^>]+>", "", m.group(2))
            if level == 1:
                body.append("<h1>%s</h1>" % txt_esc)
            elif level in (2, 3):
                sec[0] += 1
                anchor = "sec-%d" % sec[0]
                toc_lv = 0 if level == 2 else 1
                toc.append((toc_lv, anchor, plain))
                tag = "h2" if level == 2 else "h3"
                body.append('<h%d id="%s">%s</h%s>' % (level, anchor, txt_esc, tag))
            else:
                body.append("<h4>%s</h4>" % txt_esc)
            i += 1
            continue

        mq = re.match(r"^>\s?(.*)$", stripped)
        if mq:
            body.append("<blockquote>%s</blockquote>" % md_inline(mq.group(1)))
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
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                rows.append(cells)
            if rows:
                head = rows[0]
                body.append("<table><thead><tr>%s</tr></thead><tbody>" %
                            "".join("<th>%s</th>" % md_inline(c) for c in head))
                for r in rows[1:]:
                    body.append("<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in r))
                body.append("</tbody></table>")
            continue

        ml = re.match(r"^(\s*)[-*+]\s+(.*)$", stripped)
        if ml:
            items = []
            while i < n:
                s2 = lines[i].strip()
                m2 = re.match(r"^(\s*)[-*+]\s+(.*)$", s2)
                if not m2:
                    break
                items.append("<li>%s</li>" % md_inline(m2.group(2)))
                i += 1
            body.append("<ul>%s</ul>" % "".join(items))
            continue

        body.append("<p>%s</p>" % md_inline(stripped))
        i += 1

    flush_code()
    return "\n".join(body), toc


def build_html(md_path, out_path, title, date_str, brand=False):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    body_html, toc = parse_markdown(md_text)

    cover = ['<div class="cover">',
             '<h1>%s · 拆解报告</h1>' % escape(SKILL_NAME),
             '<div class="sub">%s</div>' % escape(title or "爆款视频拆解与二创方案"),
             '<div class="date">产出日期 %s</div>' % escape(date_str)]
    if brand:
        cover.append('<div class="brand">%s</div>' % BRAND_LINE)
    cover.append('</div>')

    toc_html = ['<div class="toc"><h2>目录</h2><ol>']
    for lv, anchor, text in toc:
        cls = "lv0" if lv == 0 else "lv1"
        toc_html.append('<li class="%s"><a href="#%s">%s</a></li>' % (cls, anchor, escape(text)))
    toc_html.append('</ol></div>')

    foot = '<div class="foot screen-foot">%s</div>' % escape(FOOTER)

    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>%s</title>
<style>%s</style>
</head>
<body>
<div class="wrap">
%s
%s
%s
%s
</div>
</body>
</html>
""" % (escape(title or SKILL_NAME), CSS, "\n".join(cover), "\n".join(toc_html),
       body_html, foot)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成拆解报告 HTML 文档（含封面与目录，单文件可打印）")
    ap.add_argument("--md", required=True, help="输入 Markdown 报告路径")
    ap.add_argument("--out", default=None, help="输出 HTML 路径（默认同名 .html）")
    ap.add_argument("--title", default=None, help="封面主题（报告副标题）")
    ap.add_argument("--date", default=None, help="产出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--brand", action="store_true",
                    help="在封面打印品牌署名行（含联系方式）；默认不打印")
    args = ap.parse_args()

    md_path = os.path.abspath(args.md)
    if not os.path.exists(md_path):
        _fe.print_error(
            FileNotFoundError(md_path),
            context="生成 HTML",
            hints=[
                "确认路径里有 --md 指定的 .md 文件",
                "如使用相对路径，确认当前命令行工作目录",
                "路径含空格或中文时建议加引号：「\"我的报告.md\"」",
            ],
        )
        sys.exit(_fe.EXIT_USER)

    out_path = args.out or (os.path.splitext(md_path)[0] + ".html")
    date_str = args.date or date.today().strftime("%Y-%m-%d")

    try:
        build_html(md_path, out_path, args.title, date_str, brand=args.brand)
    except SystemExit:
        raise
    except Exception as e:
        _fe.print_error(e, context="生成 HTML")
        sys.exit(_fe.suggest_exit_code(e))

    size = os.path.getsize(out_path)
    sys.stdout.write("✅ HTML 已生成：%s （%.1f KB）\n" % (out_path, size / 1024))


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
