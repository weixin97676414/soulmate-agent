#!/usr/bin/env python3
import argparse, csv, html, json, math, re
from collections import Counter, defaultdict
from pathlib import Path

def read_text(path):
    return Path(path).read_text(encoding="utf-8").strip()

def ensure_out(path):
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def words(text):
    zh = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    en = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
    return zh + en

def sentences(text):
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [p.strip(" \t\r\n-•") for p in parts if len(p.strip()) >= 4]

def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def md_table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(h, "")).replace("|", "/") for h in headers) + " |")
    return "\n".join(out)

def render(md):
    body=[]
    for line in md.splitlines():
        s=line.strip()
        if not s: body.append("<br>"); continue
        if s.startswith("# "): body.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith("## "): body.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("- "): body.append(f"<p class='li'>• {html.escape(s[2:])}</p>")
        else: body.append(f"<p>{html.escape(s)}</p>")
    return "\n".join(body)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("--out", default="wechat-preview-output"); args=ap.parse_args()
    md=read_text(args.input); out=ensure_out(args.out)
    css="body{background:#f5f5f5;margin:0}.page{max-width:720px;margin:24px auto;padding:32px;background:white;color:#222;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;line-height:1.8}h1{font-size:28px}h2{font-size:22px;border-left:4px solid #07c160;padding-left:10px}p{font-size:16px}.li{padding-left:8px;color:#333}"
    html_doc=f"<!doctype html><meta charset='utf-8'><style>{css}</style><div class='page'>{render(md)}</div>"
    (out/"wechat_preview.html").write_text(html_doc, encoding="utf-8")
    print(f"Rendered preview: {out/'wechat_preview.html'}")
if __name__ == "__main__": main()
