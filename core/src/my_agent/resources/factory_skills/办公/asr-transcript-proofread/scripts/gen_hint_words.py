#!/usr/bin/env python3
# -*- coding: utf-8 -*-






















import argparse, os, re, sys

PLACEHOLDER = re.compile(r"(虚拟|占位|冒烟|示例|【.*?】|待.*?替换)")

def clean(s):
    return s.strip().strip("*` ").strip()

def is_noise(t):
    if not t or t in {"—", "-", "代号", "真实名称", "项目名称", "真实姓名", "备注"}:
        return True
    if len(t) < 2:                       
        return True
    if PLACEHOLDER.search(t):
        return True
    return False

def parse_md_tables(path):

    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        if line.count("|") < 2:
            continue
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):   
            continue
        cells = [clean(c) for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows

def collect_from_codename(path, client):

    terms = []
    for cells in parse_md_tables(path):
        if len(cells) < 2:
            continue
        head, name = cells[0], cells[1]
        
        if head == client and not is_noise(name):
            terms.append(name)
        
        if len(cells) >= 3 and cells[2] == client and not is_noise(name):
            terms.append(name)
        
        if len(cells) >= 3 and cells[2] == client and not is_noise(cells[1]):
            terms.append(cells[1])
    return terms

def collect_from_glossary(path):
    terms = []
    if not os.path.exists(path):
        return terms
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith(("- ", "* ", "+ ")):
            t = re.split(r"[|｜：:]", line[2:])[0]
            t = clean(t)
            if not is_noise(t):
                terms.append(t)
    
    for cells in parse_md_tables(path):
        if cells and not is_noise(cells[0]):
            terms.append(cells[0])
    return terms

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--codename", default="memory/doc/facts/client-codename.md")
    ap.add_argument("--glossary", default="")
    ap.add_argument("--max-chars", type=int, default=200)
    ap.add_argument("--out", default="")
    ap.add_argument("--print", dest="do_print", action="store_true")
    a = ap.parse_args()

    gloss = a.glossary or f"memory/projects/clients/{a.client}/术语表.md"
    terms = collect_from_codename(a.codename, a.client) + collect_from_glossary(gloss)

    
    seen, uniq = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t); uniq.append(t)

    if not uniq:
        sys.stderr.write(f"[warn] 未从 {a.codename} / {gloss} 抽到 {a.client} 的专名；"
                         f"先登记代号表/术语表再跑。\n")
    
    body = "、".join(uniq)
    prompt = f"本次录音涉及：{body}。"
    if len(prompt) > a.max_chars:                 
        kept = []
        for t in uniq:
            trial = "、".join(kept + [t])
            if len(f"本次录音涉及：{trial}。") > a.max_chars:
                break
            kept.append(t)
        prompt = f"本次录音涉及：{'、'.join(kept)}。"
        sys.stderr.write(f"[warn] 术语超 {a.max_chars} 字，截断保留 {len(kept)}/{len(uniq)} 条。\n")

    out = a.out or f"outputs/{a.client}/hint-words.txt"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(prompt)
    sys.stderr.write(f"[ok] {len(uniq)} 条专名 → {out}\n")
    sys.stderr.write(f'[next] 把热词串传给转写命令：'
                     f'--hint-words "$(cat {out})"\n')
    if a.do_print:
        print(prompt)

if __name__ == "__main__":
    main()
