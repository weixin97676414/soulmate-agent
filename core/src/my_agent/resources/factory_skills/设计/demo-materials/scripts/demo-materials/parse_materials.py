# -*- coding: utf-8 -*-
"""
素材解析：把零散素材整理成带编号的素材库 materials.json（S-x）

支持四种来源：
  1) Markdown / 文本目录     python parse_materials.py 素材目录 -o materials.json
  2) 单个长文本或粘贴内容     python parse_materials.py 单文件.md
                             python parse_materials.py --text "粘贴的内容"
                             cat x.txt | python parse_materials.py --stdin
  3) Word 文档               目录或文件中含 .docx 时自动按标题切片
  4) 结构化 JSON 清单        python parse_materials.py --json-list list.json
"""
import argparse
import datetime
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_outline import (  # noqa: E402
    build_materials, make_materials, save_json, die, norm, split_long,
)


def from_json_list(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("materials", data if isinstance(data, list) else [])
    out = []
    for r in rows:
        out.append({
            "source": r.get("source", ""),
            "section": r.get("section", "") or r.get("title", ""),
            "text": r.get("text", "") or r.get("content", ""),
            "tags": r.get("tags", []),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="零散素材 → 素材库 materials.json")
    ap.add_argument("paths", nargs="*", help="素材文件或目录（可多个）")
    ap.add_argument("--text", help="直接传入的一段文本（粘贴内容）")
    ap.add_argument("--stdin", action="store_true", help="从标准输入读取文本")
    ap.add_argument("--text-name", default="粘贴内容", help="--text/--stdin 的来源名")
    ap.add_argument("--json-list", help="结构化 JSON 素材清单")
    ap.add_argument("--max-chars", type=int, default=300,
                    help="单条素材最大字数，超出按句二次切分（默认 300）")
    ap.add_argument("--name", default="", help="素材库名称")
    ap.add_argument("-o", "--out", required=True, help="输出 materials.json")
    args = ap.parse_args()

    raw = []

    if args.json_list:
        raw.extend(from_json_list(args.json_list))

    if args.stdin:
        txt = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="ignore").read()
        from lib_outline import slice_text
        raw.extend(slice_text(txt, args.text_name))
    elif args.text:
        from lib_outline import slice_text
        raw.extend(slice_text(args.text, args.text_name))

    if args.paths:
        missing = [p for p in args.paths if not os.path.exists(p)]
        if missing:
            die("路径不存在：%s" % "、".join(missing))
        raw.extend(build_materials(args.paths))

    if not raw:
        die("没有解析到任何素材，请检查输入路径或内容")

    raw = split_long(raw, args.max_chars)

    # 去重（完全相同的正文只保留一条）
    seen = {}
    uniq = []
    for r in raw:
        k = norm(r.get("text", ""))
        if not k or k in seen:
            continue
        seen[k] = 1
        uniq.append(r)

    mats = make_materials(uniq, args.name)
    mats["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(args.out, mats)

    print("素材库已生成：%s" % args.out)
    print("  条目数：%d（去重前 %d）" % (mats["total"], len(raw)))
    print("  来源：%s" % "、".join(sorted(set(m["source"] for m in mats["materials"]))))
    print()
    for m in mats["materials"][:8]:
        prev = m["text"].replace("\n", " ")[:46]
        print("  %s  [%s / %s] %s…" % (m["id"], m["source"], m["section"], prev))
    if mats["total"] > 8:
        print("  … 其余 %d 条" % (mats["total"] - 8))
    return 0


if __name__ == "__main__":
    sys.exit(main())
