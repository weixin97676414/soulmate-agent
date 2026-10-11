#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin

class Extractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.images=[]; self.links=[]; self.title=[]; self._in_title=False
        self._skip=0
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in {"script","style","noscript","svg"}: self._skip += 1
        if tag == "title": self._in_title=True
        if tag == "img" and attrs.get("src"): self.images.append(attrs["src"])
        if tag == "a" and attrs.get("href"): self.links.append(attrs["href"])
        if tag in {"p","h1","h2","h3","h4","li","blockquote"} and self._skip == 0: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script","style","noscript","svg"} and self._skip: self._skip -= 1
        if tag == "title": self._in_title=False
        if tag in {"p","h1","h2","h3","h4","li","blockquote"} and self._skip == 0: self.parts.append("\n")
    def handle_data(self, data):
        if self._skip: return
        text=re.sub(r"\s+", " ", data).strip()
        if not text: return
        if self._in_title: self.title.append(text)
        self.parts.append(text)

def clean(lines):
    text=" ".join(lines)
    text=re.sub(r"\s+", " ", text)
    chunks=[x.strip() for x in re.split(r"\n+", text) if x.strip()]
    return "\n\n".join(chunks)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("--output", default="output"); args=ap.parse_args()
    req=Request(args.url, headers={"User-Agent":"Mozilla/5.0"})
    with urlopen(req, timeout=20) as r: raw=r.read(); ctype=r.headers.get_content_charset() or "utf-8"
    parser=Extractor(); parser.feed(raw.decode(ctype, errors="replace"))
    title=html.unescape(" ".join(parser.title)).strip() or "未命名文章"
    out=Path(args.output); out.mkdir(parents=True, exist_ok=True)
    safe=re.sub(r"[\\/:*?\"<>|]+", "-", title)[:80]
    md=out/f"{safe}.md"
    content=clean(parser.parts)
    image_lines="\n".join(f"- {urljoin(args.url, u)}" for u in parser.images[:100])
    body=f"# {title}\n\n> 来源：{args.url}\n\n{content}\n\n## 图片资源\n{image_lines}\n"
    md.write_text(body, encoding="utf-8")
    print(md.resolve())

if __name__ == "__main__": main()
