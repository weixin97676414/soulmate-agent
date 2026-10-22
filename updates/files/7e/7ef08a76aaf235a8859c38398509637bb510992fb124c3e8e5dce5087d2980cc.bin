#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_previous_actions.py — 定位上一期周期性例会纪要并提取该期待办，供本期复盘承接。

用法：
  python extract_previous_actions.py --root <项目根> --before 20260725 --json
  python extract_previous_actions.py --file <上一期会议纪要.docx> --json

可选：
  --archive-subdir 指定归档子目录（如 "项目管理/每周验收和回款会议"），
                    缺省时在 --root 下递归搜索 "*会议纪要*.docx"。

输出 prior_action_items 草稿。进展状态、进展说明和本周处理必须再根据本周转写填写，
本脚本不推断任务进展。
"""
import argparse
import glob
import json
import os
import re
import sys

from docx import Document


DATE_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
NUMBER_RE = re.compile(r"^\s*(?:\d+[、.．]\s*|本周-\d+\s*)")


def norm(text):
    return re.sub(r"\s+", "", str(text or ""))


def date_from_name(path):
    dates = DATE_RE.findall(os.path.basename(path))
    return max(dates) if dates else ""


def archive_root(root, archive_subdir=None):
    root = os.path.abspath(root)
    if archive_subdir:
        candidate = os.path.join(root, archive_subdir)
        return candidate if os.path.isdir(candidate) else root
    return root


def find_previous_minutes(root, before, archive_subdir=None):
    archive = archive_root(root, archive_subdir)
    hits = glob.glob(os.path.join(archive, "**", "*会议纪要*.docx"), recursive=True)
    candidates = []
    for path in hits:
        name = os.path.basename(path)
        if name.startswith("~$"):
            continue
        date = date_from_name(path)
        if not date or date >= before:
            continue
        candidates.append((date, os.path.getmtime(path), path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def header_index(headers, *names):
    normalized = [norm(x) for x in headers]
    for name in names:
        key = norm(name)
        if key in normalized:
            return normalized.index(key)
    return None


def extract_actions(path):
    doc = Document(path)
    actions = []
    for table in doc.tables:
        for row_index, row in enumerate(table.rows):
            headers = [cell.text.strip() for cell in row.cells]
            item_idx = header_index(headers, "会议安排事项")
            owner_idx = header_index(headers, "负责人", "责任人")
            deadline_idx = header_index(headers, "完成时限")
            if item_idx is None or owner_idx is None or deadline_idx is None:
                continue

            id_idx = header_index(headers, "编号")
            tracker_idx = header_index(headers, "追踪人")
            note_idx = header_index(headers, "来源/备注", "备注")
            for data_row in table.rows[row_index + 1:]:
                values = [cell.text.strip() for cell in data_row.cells]
                if item_idx >= len(values):
                    continue
                item = NUMBER_RE.sub("", values[item_idx]).strip()
                if not item:
                    continue
                action_no = f"上周-{len(actions) + 1:02d}"
                actions.append({
                    "编号": action_no,
                    "事项": item,
                    "负责人": values[owner_idx] if owner_idx < len(values) else "",
                    "原定时限": values[deadline_idx] if deadline_idx < len(values) else "",
                    "上周追踪人": (
                        values[tracker_idx]
                        if tracker_idx is not None and tracker_idx < len(values)
                        else ""
                    ),
                    "上周备注": (
                        values[note_idx]
                        if note_idx is not None and note_idx < len(values)
                        else ""
                    ),
                    "进展状态": "",
                    "进展说明": "",
                    "本周处理": "",
                })
            if actions:
                return actions
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="项目根或会议归档目录")
    parser.add_argument("--archive-subdir", help="归档子目录（如 项目管理/每周验收和回款会议）")
    parser.add_argument("--before", help="本次会议日期 YYYYMMDD；自动检索时必填")
    parser.add_argument("--file", help="直接指定上一期会议纪要 docx")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    path = args.file
    if not path:
        if not args.before or not re.fullmatch(r"20\d{6}", args.before):
            parser.error("自动检索需提供 --before YYYYMMDD")
        path = find_previous_minutes(args.root, args.before, args.archive_subdir)
        if not path:
            print("[ERR] 未找到会议日前的上一期正式会议纪要。", file=sys.stderr)
            sys.exit(2)

    path = os.path.abspath(path)
    if not os.path.isfile(path):
        print(f"[ERR] 文件不存在：{path}", file=sys.stderr)
        sys.exit(2)

    actions = extract_actions(path)
    if not actions:
        print("[ERR] 上一期纪要中未找到待办事项表。", file=sys.stderr)
        sys.exit(3)

    result = {
        "source": path,
        "source_date": date_from_name(path),
        "prior_action_items": actions,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"# 上一期纪要：{path}")
    for item in actions:
        print(
            f"{item['编号']} | {item['事项']} | {item['负责人']} | "
            f"{item['原定时限']}"
        )


if __name__ == "__main__":
    main()
