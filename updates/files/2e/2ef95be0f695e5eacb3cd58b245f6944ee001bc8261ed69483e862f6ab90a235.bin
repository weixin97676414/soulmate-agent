#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeChat Editorial Studio: standalone Markdown/HTML -> WeChat-friendly HTML."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
THEMES_FILE = ROOT / "themes" / "themes.json"
CONFIG_FILE = ROOT / "config.json"

with THEMES_FILE.open("r", encoding="utf-8") as f:
    THEMES = json.load(f)
with CONFIG_FILE.open("r", encoding="utf-8") as f:
    CONFIG = json.load(f)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def normalize_inline(text: str, theme: dict) -> str:
    # Protect inline code and images/links before simple emphasis transforms.
    stash: list[str] = []

    def hold(raw: str) -> str:
        stash.append(raw)
        return f"\x00H{len(stash)-1}\x00"

    s = text
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: hold(render_image(m.group(1), m.group(2))), s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: hold(render_link(m.group(1), m.group(2), theme)), s)
    s = re.sub(r"`([^`]+)`", lambda m: hold(f'<code class="wx-inline-code">{esc(m.group(1))}</code>'), s)
    s = esc(s)
    # Emphasis after escaping; placeholders survive.
    s = re.sub(r"\*\*(.+?)\*\*", rf'<strong style="font-weight:700;color:{theme["text"]}">\1</strong>', s)
    s = re.sub(r"__(.+?)__", rf'<strong style="font-weight:700;color:{theme["text"]}">\1</strong>', s)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", s)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)
    for i, raw in enumerate(stash):
        s = s.replace(f"\x00H{i}\x00", raw)
    return s


def render_link(text: str, target: str, theme: dict | None = None) -> str:
    parts = target.strip().split(maxsplit=1)
    href = parts[0]
    title = parts[1].strip().strip('"\'') if len(parts) > 1 else ""
    parsed = urlparse(href)
    safe = href if parsed.scheme in {"http", "https", "mailto", "#"} or not parsed.scheme else "#"
    title_attr = f' title="{esc(title)}"' if title else ""
    accent = (theme or THEMES["editorial-ink"])["accent"]
    accent_soft = (theme or THEMES["editorial-ink"])["accent_soft"]
    return f'<a href="{esc(safe)}"{title_attr} style="color:{accent};text-decoration:none;border-bottom:1px solid {accent_soft}">{esc(text)}</a>'


def render_image(alt: str, src: str) -> str:
    parts = src.strip().split(maxsplit=1)
    url = parts[0]
    title = parts[1].strip().strip('"\'') if len(parts) > 1 else ""
    title_attr = f' title="{esc(title)}"' if title else ""
    return f'<img src="{esc(url)}" alt="{esc(alt)}"{title_attr} class="wx-image">'


def classify_theme(text: str) -> str:
    s = text.lower()
    scores = {k: 0 for k in THEMES}
    groups = {
        "signal-blue": ["ai", "人工智能", "科技", "产品", "工具", "软件", "模型", "代码", "开发"],
        "executive-graphite": ["商业", "管理", "职场", "组织", "公司", "战略", "运营", "增长"],
        "newsroom-red": ["新闻", "周报", "月报", "速报", "资讯", "发布", "动态", "政策"],
        "utility-green": ["教程", "步骤", "方法", "效率", "指南", "操作", "技巧"],
        "warm-paper": ["散文", "生活", "旅行", "阅读", "人文", "故事", "随笔", "日常"],
        "modern-cream": ["品牌", "设计", "产品故事", "创意", "体验"],
        "museum-blue": ["历史", "文化", "博物馆", "知识", "考古", "艺术"],
        "soft-coral": ["社交", "时尚", "美食", "生活方式", "年轻", "社区"],
        "paper-orange": ["活动", "专题", "节日", "大会", "报名"],
        "fresh-mint": ["健康", "环保", "自然", "轻食", "运动"],
        "quiet-navy": ["高端", "精品", "奢侈", "品牌战略"],
        "forest-journal": ["自然", "户外", "森林", "生态", "观察"],
        "lavender-note": ["女性", "审美", "美学", "情绪", "文化"],
        "ceramic-blue": ["东方", "器物", "收藏", "瓷器", "传统"],
        "apricot-morning": ["早报", "晨读", "亲和", "阅读"],
        "midnight-tech": ["开发者", "数据", "未来", "算法", "工程"],
        "cocoa-lounge": ["随笔", "客厅", "咖啡", "生活方式"],
        "olive-studio": ["设计", "创意", "手作", "品牌设计"],
        "porcelain-red": ["节气", "东方审美", "专题", "传统文化"],
        "clear-sky": ["教育", "成长", "课程", "学习"],
        "rosewood-editorial": ["人物", "评论", "深度", "访谈"],
    }
    for theme, words in groups.items():
        scores[theme] = sum(s.count(w.lower()) for w in words)
    # Long-form analysis gets editorial if no specialized intent wins.
    if len(text) > 5000:
        scores["editorial-ink"] += 3
    return max(scores, key=scores.get)


def copy_local_assets(md_text: str, input_path: Path, output_dir: Path) -> tuple[str, list[str], list[str]]:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    copied: list[str] = []

    def repl(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2).strip()
        if re.match(r"^(?:https?:|data:|#)", src, re.I):
            return match.group(0)
        path = (input_path.parent / src).resolve()
        if not path.exists() or not path.is_file():
            missing.append(src)
            return match.group(0)
        target = assets / path.name
        if not target.exists():
            shutil.copy2(path, target)
        copied.append(str(target.relative_to(output_dir)).replace(os.sep, "/"))
        return f"![{alt}]({('assets/' + path.name)})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, md_text), sorted(set(copied)), sorted(set(missing))


def parse_table(lines: list[str], start: int) -> tuple[str, int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not cells:
            break
        if i == start + 1 and all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            i += 1
            continue
        rows.append(cells)
        i += 1
    if len(rows) < 2:
        return "", start
    head = rows[0]
    body = rows[1:]
    out = ['<section class="wx-table-wrap"><table class="wx-table"><thead><tr>']
    for c in head:
        out.append(f"<th>{normalize_inline(c, CURRENT_THEME)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for idx in range(len(head)):
            val = row[idx] if idx < len(row) else ""
            out.append(f"<td>{normalize_inline(val, CURRENT_THEME)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></section>")
    return "".join(out), i


def render_container(kind: str, title: str, body: list[str], theme: dict) -> str:
    title_html = f'<p class="wx-component-title">{esc(title)}</p>' if title else ""
    if kind == "callout":
        typ = "note"
        if "|" in title:
            title, typ = title.split("|", 1)
            title_html = f'<p class="wx-component-title">{esc(title)}</p>' if title else ""
        safe_typ = typ.strip() if typ.strip() in {"note", "tip", "important", "warning"} else "note"
        body_html = render_blocks(body, theme)
        return f'<section class="wx-callout wx-{safe_typ}">{title_html}{body_html}</section>'
    if kind == "steps":
        items = [x.strip() for x in body if x.strip()]
        inner = "".join(f'<section class="wx-step"><span class="wx-step-no">{i}</span><span>{normalize_inline(x, theme)}</span></section>' for i, x in enumerate(items, 1))
        return f'<section class="wx-steps">{title_html}{inner}</section>'
    if kind == "dialogue":
        inner = []
        for idx, line in enumerate([x for x in body if x.strip()]):
            m = re.match(r"^([^:：]{1,20})[:：]\s*(.+)$", line)
            if m:
                person, text = m.groups()
                inner.append(f'<section class="wx-dialogue wx-dialogue-{idx%2}"><b>{esc(person)}</b><span>{normalize_inline(text, theme)}</span></section>')
            else:
                inner.append(f'<p>{normalize_inline(line, theme)}</p>')
        return f'<section class="wx-dialogue-wrap">{title_html}{"".join(inner)}</section>'
    if kind == "timeline":
        inner = []
        for line in body:
            m = re.match(r"^(.+?)\s*[：:]\s*(.+)$", line.strip())
            if m:
                when, content = m.groups()
                inner.append(f'<section class="wx-time-item"><b>{esc(when)}</b><span>{normalize_inline(content, theme)}</span></section>')
        return f'<section class="wx-timeline">{title_html}{"".join(inner)}</section>'
    if kind == "compare":
        left, right = (title.split(" vs ", 1) + [""])[:2] if " vs " in title else ("方案 A", "方案 B")
        rows = []
        for line in body:
            if "|" in line:
                a, b = [x.strip() for x in line.split("|", 1)]
                rows.append(f'<tr><td>{normalize_inline(a, theme)}</td><td>{normalize_inline(b, theme)}</td></tr>')
        return f'<section class="wx-compare">{title_html}<table><thead><tr><th>{esc(left)}</th><th>{esc(right)}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>'
    if kind == "quote":
        return f'<section class="wx-quote">{title_html}<blockquote>{render_blocks(body, theme)}</blockquote></section>'
    if kind == "gallery":
        inner = render_blocks(body, theme)
        return f'<section class="wx-gallery">{title_html}{inner}</section>'
    return render_blocks(body, theme)


def render_blocks(lines: list[str], theme: dict) -> str:
    out: list[str] = []
    i = 0
    paragraph: list[str] = []
    list_mode: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            txt = " ".join(x.strip() for x in paragraph).strip()
            if txt:
                out.append(f'<p class="wx-p">{normalize_inline(txt, theme)}</p>')
            paragraph = []

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None

    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            flush_paragraph(); close_list(); i += 1; continue

        cm = re.match(r"^:::(callout|steps|dialogue|timeline|compare|quote|gallery)\[(.*?)\]\s*$", line)
        if cm:
            flush_paragraph(); close_list()
            kind, title = cm.groups(); body: list[str] = []; i += 1
            depth = 1
            while i < len(lines):
                if re.match(r"^:::(callout|steps|dialogue|timeline|compare|quote|gallery)\[.*?\]\s*$", lines[i].rstrip()):
                    depth += 1
                elif lines[i].strip() == ":::":
                    depth -= 1
                    if depth == 0:
                        i += 1; break
                body.append(lines[i]); i += 1
            out.append(render_container(kind, title, body, theme)); continue

        if re.match(r"^#{1,3}\s+", line):
            flush_paragraph(); close_list()
            m = re.match(r"^(#{1,3})\s+(.*)$", line)
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                out.append(f'<p class="wx-kicker">{normalize_inline(text, theme)}</p>')
            else:
                out.append(f'<h{level} class="wx-h{level}"><span>{normalize_inline(text, theme)}</span></h{level}>')
            i += 1; continue

        if re.match(r"^[-*_](?:\s*[-*_]){2,}\s*$", line):
            flush_paragraph(); close_list(); out.append('<hr class="wx-hr">'); i += 1; continue

        if line.startswith(">"):
            flush_paragraph(); close_list()
            q: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(re.sub(r"^>\s?", "", lines[i])); i += 1
            out.append(f'<blockquote class="wx-blockquote">{render_blocks(q, theme)}</blockquote>'); continue

        if line.startswith("```") or line.startswith("~~~"):
            flush_paragraph(); close_list()
            fence = line[:3]; lang = line[3:].strip(); i += 1; code: list[str] = []
            while i < len(lines) and not lines[i].startswith(fence):
                code.append(lines[i]); i += 1
            if i < len(lines): i += 1
            lang_attr = f' data-lang="{esc(lang)}"' if lang else ""
            out.append(f'<pre class="wx-code"{lang_attr}><code>{esc("\n".join(code))}</code></pre>'); continue

        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[i+1]):
            flush_paragraph(); close_list()
            table, nxt = parse_table(lines, i)
            if table:
                out.append(table); i = nxt; continue

        lm = re.match(r"^\s*([-*+] |\d+[.)] )(.+)$", line)
        if lm:
            flush_paragraph()
            marker, text = lm.groups()
            typ = "ol" if marker[0].isdigit() else "ul"
            if list_mode != typ:
                close_list(); list_mode = typ; out.append(f"<{typ} class=\"wx-list\">")
            out.append(f'<li>{normalize_inline(text, theme)}</li>'); i += 1; continue
        else:
            close_list()

        if re.match(r"^!\[[^\]]*\]\([^)]+\)$", line.strip()):
            flush_paragraph(); out.append(f'<section class="wx-figure">{normalize_inline(line.strip(), theme)}</section>'); i += 1; continue

        # Short italic line after image -> likely caption. Keep as caption rather than generic paragraph.
        if re.match(r"^\*[^*\n]+\*$", line.strip()) and out and 'class="wx-figure"' in out[-1]:
            caption = line.strip()[1:-1].strip()
            out.append(f'<p class="wx-caption">{esc(caption)}</p>'); i += 1; continue

        paragraph.append(line); i += 1

    flush_paragraph(); close_list()
    return "\n".join(out)


def wrap_html(body: str, theme_id: str, title: str, preview: bool = False) -> str:
    theme = THEMES[theme_id]
    root_pad = theme.get("shell_padding", "28px 18px 56px")
    radius = theme.get("radius", "12px")
    image_radius = theme.get("image_radius", radius)
    body_size = theme.get("body_size", "16px")
    line_height = theme.get("line_height", "1.86")
    h2_gap = theme.get("heading_gap", "30px")
    paragraph_gap = theme.get("paragraph_gap", "1.05em")
    h2_size = theme.get("h2_size", "22px")
    h3_size = theme.get("h3_size", "18px")
    heading_style = theme.get("heading_style", "underline")
    heading_rules = {
        "underline": "display:inline-block;padding-bottom:6px;border-bottom:2px solid var(--wx-accent);",
        "bar": "display:inline-block;padding:6px 10px 6px 12px;border-left:4px solid var(--wx-accent);background:var(--wx-accent-soft);border-radius:4px;",
        "dot": "display:inline-block;padding-left:14px;position:relative;",
        "rule": "display:inline-block;padding-bottom:7px;border-bottom:1px solid var(--wx-accent);",
        "soft": "display:inline-block;padding:5px 10px;background:var(--wx-accent-soft);border-radius:8px;",
        "block": "display:inline-block;padding:7px 11px;background:var(--wx-accent-soft);border-radius:5px;",
        "quiet": "display:inline-block;padding-bottom:7px;border-bottom:1px solid var(--wx-border);",
        "seal": "display:inline-block;padding:5px 11px;border:1px solid var(--wx-accent);border-radius:6px;background:var(--wx-accent-soft);",
        "toprule": "display:block;padding-top:8px;border-top:2px solid var(--wx-accent);",
        "double-rule": "display:block;padding:7px 0;border-top:1px solid var(--wx-accent);border-bottom:1px solid var(--wx-border);",
        "capsule": "display:inline-block;padding:5px 12px;border:1px solid var(--wx-border);border-radius:999px;background:var(--wx-accent-soft);",
        "corner": "display:inline-block;padding:5px 10px 7px;border-left:3px solid var(--wx-accent);border-bottom:1px solid var(--wx-border);",
        "frame": "display:inline-block;padding:7px 12px;border:1px solid var(--wx-accent);border-radius:4px;",
        "minimal": "display:inline-block;padding-bottom:5px;border-bottom:1px solid var(--wx-border);",
        "ink": "display:inline-block;padding:0 0 5px;border-bottom:3px solid var(--wx-accent);",
    }
    heading_span_style = heading_rules.get(heading_style, heading_rules["underline"])
    css = f"""
    :root{{--wx-accent:{theme['accent']};--wx-accent-soft:{theme['accent_soft']};--wx-text:{theme['text']};--wx-muted:{theme['muted']};--wx-bg:{theme['bg']};--wx-border:{theme['border']};--wx-code:{theme['code_bg']}}}
    *{{box-sizing:border-box}} body{{margin:0;background:{theme['bg']};color:{theme['text']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;line-height:{line_height};font-size:{body_size};word-break:break-word;-webkit-text-size-adjust:100%}} .wx-shell{{max-width:760px;margin:0 auto;padding:{root_pad}}} .wx-p{{margin:0 0 {paragraph_gap};text-align:left;letter-spacing:.01em}} .wx-kicker{{font-size:14px;color:var(--wx-accent);font-weight:700;margin:0 0 14px;letter-spacing:.04em}} .wx-h2{{font-size:{h2_size};line-height:1.42;margin:{h2_gap} 0 14px;font-weight:800;letter-spacing:-.01em}} .wx-h2 span{{{heading_span_style}}} .wx-h3{{font-size:{h3_size};line-height:1.52;margin:24px 0 10px;font-weight:750}} .wx-h3 span{{display:inline-block}} .wx-list{{margin:0 0 18px;padding-left:22px}} .wx-list li{{margin:7px 0;padding-left:3px}} .wx-blockquote{{margin:20px 0;padding:14px 16px;background:var(--wx-accent-soft);border-left:4px solid var(--wx-accent);color:var(--wx-text);border-radius:0 {radius} {radius} 0}} .wx-blockquote p:last-child{{margin-bottom:0}} .wx-hr{{height:1px;border:0;background:var(--wx-border);margin:30px 0}} .wx-image{{display:block;width:100%;height:auto;border-radius:{image_radius};margin:0 auto}} .wx-figure{{margin:24px 0 6px;text-align:center}} .wx-caption{{margin:5px 0 20px;text-align:center;color:var(--wx-muted);font-size:13px;line-height:1.65}} a{{color:var(--wx-accent);text-decoration:underline;text-underline-offset:2px}} mark{{background:var(--wx-accent-soft);color:inherit;padding:0 3px;border-radius:3px}} del{{opacity:.7}} .wx-inline-code{{background:var(--wx-code);border:1px solid var(--wx-border);padding:2px 6px;border-radius:5px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em}} .wx-code{{margin:22px 0;padding:16px;overflow-x:auto;background:var(--wx-code);border:1px solid var(--wx-border);border-radius:{radius};font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;tab-size:2}} .wx-table-wrap{{overflow-x:auto;margin:22px 0}} .wx-table,.wx-compare table{{width:100%;border-collapse:collapse;font-size:14px}} .wx-table th,.wx-table td,.wx-compare th,.wx-compare td{{border:1px solid var(--wx-border);padding:10px 10px;text-align:left;vertical-align:top;line-height:1.65}} .wx-table th,.wx-compare th{{background:var(--wx-accent-soft);font-weight:700}} .wx-component-title{{margin:0 0 11px;font-size:14px;font-weight:800;color:var(--wx-accent);letter-spacing:.02em}} .wx-callout,.wx-steps,.wx-dialogue-wrap,.wx-timeline,.wx-compare,.wx-quote,.wx-gallery{{margin:24px 0;padding:16px 16px;border:1px solid var(--wx-border);border-radius:{radius};background:{theme['bg']}}} .wx-important{{background:var(--wx-accent-soft);border-color:var(--wx-accent)}} .wx-warning{{background:#FFF8EE;border-color:#E6A23C}} .wx-tip{{background:#EFFAF5;border-color:#42A77A}} .wx-step{{display:flex;gap:11px;margin:11px 0;align-items:flex-start;line-height:1.72}} .wx-step-no{{display:inline-flex;align-items:center;justify-content:center;min-width:25px;height:25px;border-radius:50%;background:var(--wx-accent);color:#fff;font-weight:800;font-size:12px;flex:none}} .wx-dialogue{{display:flex;gap:10px;margin:11px 0;align-items:flex-start}} .wx-dialogue b{{min-width:60px;color:var(--wx-accent);font-size:13px;line-height:1.65}} .wx-dialogue span{{flex:1;padding:10px 12px;border-radius:9px;background:var(--wx-accent-soft);line-height:1.72}} .wx-time-item{{display:flex;gap:12px;padding:11px 0;border-left:2px solid var(--wx-accent);padding-left:14px;margin-left:7px;line-height:1.72}} .wx-time-item b{{min-width:74px;color:var(--wx-accent)}} .wx-quote blockquote{{margin:0;padding:5px 0 5px 15px;border-left:3px solid var(--wx-accent);font-size:18px;line-height:1.75}} .wx-gallery .wx-figure{{margin:9px 0}} .wx-gallery .wx-image{{border-radius:{max(6,int(radius.replace('px',''))-2) if radius.endswith('px') else '8px'}}} .wx-compare td{{width:50%}} .wx-shell img{{max-width:100%}}
    """
    if preview:
        return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title or "微信文章预览")}</title><style>{css}</style></head><body><main class="wx-shell">{body}</main></body></html>'
    # Inline styles are intentionally approximated by style attributes in a second pass for common elements.
    # WeChat preserves inline styles more consistently than a <style> block when pasted.
    inline = body
    inline = inline.replace('class="wx-p"', f'style="margin:0 0 {paragraph_gap};line-height:{line_height};color:{theme["text"]};font-size:{body_size}"')
    inline = inline.replace('class="wx-kicker"', f'style="font-size:14px;color:{theme["accent"]};font-weight:700;margin:0 0 16px"')
    inline_h2_style = f'font-size:{h2_size};line-height:1.42;margin:{h2_gap} 0 14px;font-weight:800;color:{theme["text"]}'
    inline_h2_span = heading_span_style.replace("var(--wx-accent)", theme["accent"]).replace("var(--wx-accent-soft)", theme["accent_soft"]).replace("var(--wx-border)", theme["border"])
    inline = re.sub(r'<h2 class="wx-h2"><span>', f'<h2 style="{inline_h2_style}"><span style="{inline_h2_span}">', inline)
    inline = inline.replace('class="wx-h3"', f'style="font-size:{h3_size};line-height:1.52;margin:24px 0 10px;font-weight:750;color:{theme["text"]}"')
    inline = inline.replace('class="wx-image"', f'style="display:block;width:100%;height:auto;border-radius:{image_radius};margin:0 auto"')
    inline = inline.replace('class="wx-caption"', f'style="margin:4px 0 18px;text-align:center;color:{theme["muted"]};font-size:13px;line-height:1.6"')
    inline = re.sub(r'class="wx-figure"', 'style="margin:22px 0 6px;text-align:center"', inline)
    inline = re.sub(r'class="wx-blockquote"', f'style="margin:20px 0;padding:13px 16px;background:{theme["accent_soft"]};border-left:4px solid {theme["accent"]}"', inline)
    inline = inline.replace('class="wx-inline-code"', f'style="background:{theme["code_bg"]};border:1px solid {theme["border"]};padding:2px 6px;border-radius:4px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14px"')
    inline = inline.replace('class="wx-list"', 'style="margin:0 0 18px;padding-left:22px"')
    inline = inline.replace('class="wx-hr"', f'style="height:1px;border:0;background:{theme["border"]};margin:28px 0"')
    inline = inline.replace('class="wx-code"', f'style="margin:20px 0;padding:16px;overflow-x:auto;background:{theme["code_bg"]};border:1px solid {theme["border"]};border-radius:10px;font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap"')
    inline = inline.replace('class="wx-table-wrap"', 'style="overflow-x:auto;margin:20px 0"')
    inline = inline.replace('class="wx-table"', f'style="width:100%;border-collapse:collapse;font-size:14px"')
    inline = re.sub(r'<th>(.*?)</th>', f'<th style="border:1px solid {theme["border"]};padding:9px 10px;text-align:left;vertical-align:top;background:{theme["accent_soft"]};font-weight:700">\1</th>', inline, flags=re.S)
    inline = re.sub(r'<td>(.*?)</td>', f'<td style="border:1px solid {theme["border"]};padding:9px 10px;text-align:left;vertical-align:top">\1</td>', inline, flags=re.S)
    inline = inline.replace('class="wx-component-title"', f'style="margin:0 0 10px;font-size:14px;font-weight:800;color:{theme["accent"]}"')
    inline = re.sub(r'class="wx-callout(?: wx-(?:important|tip|warning))?"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]}"', inline)
    inline = inline.replace('class="wx-steps"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]}"')
    inline = inline.replace('class="wx-step"', 'style="display:flex;gap:11px;margin:10px 0;align-items:flex-start"')
    inline = inline.replace('class="wx-step-no"', f'style="display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;border-radius:50%;background:{theme["accent"]};color:#fff;font-weight:800;font-size:12px"')
    inline = inline.replace('class="wx-dialogue-wrap"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]}"')
    inline = inline.replace('class="wx-dialogue"', 'style="display:flex;gap:10px;margin:10px 0;align-items:flex-start"')
    inline = inline.replace('class="wx-time-item"', f'style="display:flex;gap:12px;padding:10px 0;border-left:2px solid {theme["accent"]};padding-left:14px;margin-left:7px"')
    inline = inline.replace('class="wx-quote"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]}"')
    inline = inline.replace('class="wx-gallery"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]}"')
    inline = inline.replace('class="wx-compare"', f'style="margin:22px 0;padding:15px 16px;border:1px solid {theme["border"]};border-radius:{radius};background:{theme["bg"]};overflow:auto"')
    return f'<section style="max-width:760px;margin:0 auto;padding:{root_pad};color:{theme["text"]};font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'PingFang SC\',\'Microsoft YaHei\',sans-serif;font-size:16px;line-height:1.82">{inline}</section>'


def document_title(md: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else ""


def report_html(raw: str, output_html: str, missing_assets: list[str], copied_assets: list[str], theme_id: str) -> dict:
    issues: list[dict[str, str]] = []
    if missing_assets:
        issues.append({"level": "CHECK", "code": "MISSING_IMAGE", "message": f"发现 {len(missing_assets)} 个本地图片路径不存在。"})
    for tag in re.findall(r"<([A-Za-z][\w-]*)\b", raw):
        if tag.lower() in {"script", "iframe", "video", "audio", "form", "style", "link"}:
            issues.append({"level": "BLOCK", "code": "UNSUPPORTED_TAG", "message": f"检测到高风险标签 <{tag}>。"})
    if re.search(r"position\s*:\s*(?:fixed|absolute)|animation\s*:|@media", raw, re.I):
        issues.append({"level": "CHECK", "code": "COMPLEX_STYLE", "message": "检测到复杂定位、动画或响应式样式，复制到公众号后可能表现不一致。"})
    long_paras = [p for p in re.findall(r'<p[^>]*>(.*?)</p>', raw, flags=re.S) if len(re.sub(r'<[^>]+>', '', p)) > 260]
    if long_paras:
        issues.append({"level": "CHECK", "code": "LONG_PARAGRAPH", "message": f"发现 {len(long_paras)} 个较长段落，建议人工检查断句。"})
    emphasis_count = len(re.findall(r'<strong\b', raw))
    if emphasis_count > 24:
        issues.append({"level": "CHECK", "code": "EMPHASIS_OVERUSE", "message": f"粗体出现约 {emphasis_count} 次，可能削弱重点层级。"})
    table_count = len(re.findall(r'<table\b', raw))
    if table_count > 3:
        issues.append({"level": "CHECK", "code": "TABLE_DENSITY", "message": "表格较多，移动端建议拆成卡片或列表。"})
    risk = "BLOCK" if any(x["level"] == "BLOCK" for x in issues) else ("CHECK" if issues else "PASS")
    return {
        "version": "1.0.0",
        "theme": theme_id,
        "risk": risk,
        "stats": {
            "source_characters": len(re.sub(r"\s+", "", raw)),
            "html_characters": len(output_html),
            "headings_h2": len(re.findall(r'<h2\b', output_html)),
            "headings_h3": len(re.findall(r'<h3\b', output_html)),
            "images": len(re.findall(r'<img\b', output_html)),
            "tables": table_count,
            "strong": emphasis_count
        },
        "assets": {"copied": copied_assets, "missing": missing_assets},
        "issues": issues,
        "recommendations": [
            "复制到公众号后台后，优先检查图片与表格。",
            "标题、重点块和普通段落的视觉重量应保持明显差异。",
            "长文建议在最终发布前进行一次手机端预览。"
        ]
    }


def validate_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    checks = []
    checks.append(("无 script", not re.search(r"<script\b", text, re.I)))
    checks.append(("无 iframe", not re.search(r"<iframe\b", text, re.I)))
    checks.append(("img 有 src", all(bool(m.group(1)) for m in re.finditer(r'<img\b[^>]*src="([^"]*)"', text, re.I))))
    print(f"文件: {path}")
    failed = False
    for name, ok in checks:
        print(("PASS" if ok else "BLOCK") + "  " + name)
        failed |= not ok
    return 2 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="微信公众号全域排版引擎")
    parser.add_argument("--input", "-i", help="输入 Markdown 文件")
    parser.add_argument("--theme", "-t", default=CONFIG.get("default_theme", "auto"), help="主题 ID 或 auto")
    parser.add_argument("--output", "-o", default=CONFIG.get("output_dir", "./wechat-output"), help="输出目录")
    parser.add_argument("--safe", action="store_true", help="安全模式：只整理格式，不做内容层面的主动归类")
    parser.add_argument("--no-preview", action="store_true", help="不生成预览页")
    parser.add_argument("--open", action="store_true", help="生成预览后用默认浏览器打开")
    parser.add_argument("--list-themes", action="store_true", help="列出主题")
    parser.add_argument("--validate", metavar="HTML", help="校验已有 HTML")
    args = parser.parse_args()

    if args.list_themes:
        for k, v in THEMES.items():
            print(f"{k}\t{v['name']}\t{v['mood']}")
        return 0
    if args.validate:
        return validate_file(Path(args.validate).expanduser().resolve())
    if not args.input:
        parser.error("缺少 --input")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"错误：找不到输入文件：{input_path}", file=sys.stderr); return 2
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = input_path.read_text(encoding="utf-8")
    title = document_title(raw) or input_path.stem
    raw_with_assets, copied_assets, missing_assets = copy_local_assets(raw, input_path, output_dir) if CONFIG.get("assets", {}).get("copy_local_images", True) else (raw, [], [])
    theme_id = args.theme
    if theme_id == "auto":
        theme_id = classify_theme(raw_with_assets)
    if theme_id not in THEMES:
        print(f"错误：未知主题 {theme_id}。请使用 --list-themes 查看。", file=sys.stderr); return 2

    # Safe mode never invents containers; semantic containers are already explicit in source.
    global CURRENT_THEME
    CURRENT_THEME = THEMES[theme_id]
    body = render_blocks(raw_with_assets.splitlines(), CURRENT_THEME)
    html_out = wrap_html(body, theme_id, title, preview=False)
    preview_out = wrap_html(body, theme_id, title, preview=True)

    base = input_path.stem
    html_path = output_dir / f"{base}.wechat.html"
    preview_path = output_dir / f"{base}.preview.html"
    report_path = output_dir / f"{base}.report.json"
    html_path.write_text(html_out, encoding="utf-8")
    if not args.no_preview:
        preview_path.write_text(preview_out, encoding="utf-8")
        if args.open:
            webbrowser.open(preview_path.as_uri())
    report = report_html(raw_with_assets, html_out, missing_assets, copied_assets, theme_id)
    report["mode"] = "safe" if args.safe or CONFIG.get("default_mode") == "safe" else "standard"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"主题: {theme_id} ({THEMES[theme_id]['name']})")
    print(f"HTML: {html_path}")
    if not args.no_preview:
        print(f"预览: {preview_path}")
    print(f"报告: {report_path}")
    print(f"校验结果: {report['risk']}")
    for issue in report["issues"]:
        print(f"- {issue['level']}: {issue['message']}")
    return 0


CURRENT_THEME = THEMES["editorial-ink"]

if __name__ == "__main__":
    raise SystemExit(main())
