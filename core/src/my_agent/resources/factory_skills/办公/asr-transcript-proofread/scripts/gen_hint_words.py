#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_hint_words.py · 上游预防：把客户专名/术语自动拼成转写命令的 --hint-words。

用途：转写前先跑本脚本，从客户代号表 + 客户术语表抽取真实专名（公司名/人名/项目名/
产品线/行业黑话/职务），生成一段 whisper initial_prompt 风格的热词串，喂给
转写命令的 --hint-words，让 ASR 在转写阶段就少错专名（源头预防）。

保密：热词串含甲方真名，仅本地用（whisperX 离线、数据不出域）。脚本默认把热词写到
本地文件，不在标准输出回显真名（除非 --print）。落盘路径用代号。

输入：
  --client   客户代号（如 甲方B）；用于在代号表里筛该客户的人员/项目
  --codename 客户代号映射表路径（默认 memory/doc/facts/client-codename.md）
  --glossary 客户术语表路径（默认 memory/projects/clients/{客户代号}/术语表.md，可选）
  --max-chars 热词串上限字符数（默认 200；whisper initial_prompt 不宜过长）
  --out      输出文件（默认 outputs/{客户代号}/hint-words.txt）
  --print    额外把热词串打到 stdout（含真名，慎用）

术语表约定：markdown，一行一个术语，形如 `- 术语` 或 `- 术语 | 说明`（取 | / ： 前部分）。

输出：热词文件 + 一行可拼进转写命令的提示。
"""
import argparse, os, re, sys

PLACEHOLDER = re.compile(r"(虚拟|占位|冒烟|示例|【.*?】|待.*?替换)")

def clean(s):
    return s.strip().strip("*` ").strip()

def is_noise(t):
    if not t or t in {"—", "-", "代号", "真实名称", "项目名称", "真实姓名", "备注"}:
        return True
    if len(t) < 2:                       # 单字噪声
        return True
    if PLACEHOLDER.search(t):
        return True
    return False

def parse_md_tables(path):
    """返回所有表格行（list of cell-list），跳过表头/分隔行。"""
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        if line.count("|") < 2:
            continue
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):   # |---|---| 分隔行
            continue
        cells = [clean(c) for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows

def collect_from_codename(path, client):
    """从代号表抽：公司真名 + 该客户人员真名 + 该客户项目名。"""
    terms = []
    for cells in parse_md_tables(path):
        if len(cells) < 2:
            continue
        head, name = cells[0], cells[1]
        # 公司行：代号==client 时取真名（cells[1]）
        if head == client and not is_noise(name):
            terms.append(name)
        # 人员行：cells = 代号 | 真实姓名 | 公司代号 | ...；公司代号==client
        if len(cells) >= 3 and cells[2] == client and not is_noise(name):
            terms.append(name)
        # 项目行：代号 | 项目名称 | 客户代号 | ...
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
    # 也吃术语表里的表格首列
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

    # 去重保序
    seen, uniq = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t); uniq.append(t)

    if not uniq:
        sys.stderr.write(f"[warn] 未从 {a.codename} / {gloss} 抽到 {a.client} 的专名；"
                         f"先登记代号表/术语表再跑。\n")
    # 拼 initial_prompt 风格：自然句包住术语，偏置 whisper
    body = "、".join(uniq)
    prompt = f"本次录音涉及：{body}。"
    if len(prompt) > a.max_chars:                 # 超长截断（保完整术语）
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
