#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "assets" / "article.css"
if not CSS.exists(): CSS = Path("assets/article.css")

def inline_md(text: str) -> str:
    text=html.escape(text, quote=False)
    text=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text=re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text

def render(md: str) -> str:
    out=[]; in_list=False; paragraph=[]
    def flush():
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{inline_md(' '.join(paragraph))}</p>")
            paragraph=[]
    for raw in md.splitlines():
        line=raw.strip()
        if not line: flush(); continue
        if line.startswith("# "): flush(); out.append(f"<h1>{inline_md(line[2:])}</h1>"); continue
        if line.startswith("## "): flush(); out.append(f"<h2>{inline_md(line[3:])}</h2>"); continue
        if line.startswith("### "): flush(); out.append(f"<h3>{inline_md(line[4:])}</h3>"); continue
        if line.startswith("> "): flush(); out.append(f"<blockquote>{inline_md(line[2:])}</blockquote>"); continue
        if line.startswith("- "):
            if not in_list: flush(); out.append("<ul>"); in_list=True
            out.append(f"<li>{inline_md(line[2:])}</li>"); continue
        if in_list:
            out.append("</ul>"); in_list=False
        if line.startswith("![") and "](" in line:
            m=re.match(r"!\[(.*?)\]\((.*?)\)", line)
            if m: flush(); out.append(f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}">'); continue
        paragraph.append(line)
    flush()
    if in_list: out.append("</ul>")
    return "\n".join(out)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("-o","--output"); args=ap.parse_args()
    src=Path(args.input); md=src.read_text(encoding="utf-8"); css=CSS.read_text(encoding="utf-8") if CSS.exists() else ""
    body=render(md)
    out=Path(args.output) if args.output else src.with_suffix(".html")
    out.write_text(f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body>{body}</body></html>', encoding="utf-8")
    print(out.resolve())

if __name__ == "__main__": main()
