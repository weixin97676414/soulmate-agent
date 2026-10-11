#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

BAD = ["在这个快速变化的时代", "赋能", "抓手", "全方位", "闭环", "毋庸置疑", "不难发现"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("project"); args=ap.parse_args(); root=Path(args.project)
    errors=[]; warns=[]
    md=list((root/"02_draft").glob("*.md")) + list((root/"04_layout").glob("*.html"))
    if not md: errors.append("no draft or HTML output found")
    text="\n".join(p.read_text(encoding="utf-8",errors="ignore") for p in md)
    if len(text.strip()) < 100: errors.append("content is too short for a normal article")
    for term in BAD:
        n=text.count(term)
        if n >= 3: warns.append(f"overused phrase: {term} x{n}")
    for heading in re.findall(r"(?m)^## +(.+)$", text):
        if len(heading)>32: warns.append(f"long section heading: {heading[:32]}…")
    assets = root/"03_visual"
    if not any(assets.glob("cover.*")) and not any(assets.glob("*.png")) and not any(assets.glob("*.jpg")):
        warns.append("no local cover/visual asset found")
    report=root/"06_report"/"preflight.md"; report.parent.mkdir(parents=True,exist_ok=True)
    status="FAIL" if errors else ("WARN" if warns else "PASS")
    lines=[f"# Preflight: {status}","",f"Errors: {len(errors)}",f"Warnings: {len(warns)}","",*([f"- ERROR: {x}" for x in errors]),*([f"- WARN: {x}" for x in warns]),"","> This report is a quality gate, not a guarantee of factual correctness."]
    report.write_text("\n".join(lines),encoding="utf-8")
    print(report.resolve())
    return 1 if errors else 0

if __name__ == "__main__": raise SystemExit(main())
