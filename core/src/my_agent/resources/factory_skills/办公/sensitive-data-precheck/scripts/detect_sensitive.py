#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_sensitive.py - 敏感字段自查脚本（办公技能配套）

用途：
  在把内部材料交给 AI 处理、或准备对外分享之前，先扫一遍里面有没有
  身份证号 / 手机号 / 银行卡号 / 统一社会信用代码（税号）/ 邮箱 / IP 等敏感字段。

设计原则：
  * 只报告，不改写 —— 绝不修改或重写你的原文。
  * 零依赖 —— 只用 Python 标准库，不联网，数据不出本机。
  * 询问式脱敏 —— 扫出来之后由你决定：保留原文（对内）/ 部分掩码（半公开）/ 完全脱敏（对外）。
                  本脚本不替你做这个决定，也不默认遮盖。

用法：
  python detect_sensitive.py 文件.txt
  python detect_sensitive.py ./导出目录
  python detect_sensitive.py 文件.txt --json
  cat 文件.txt | python detect_sensitive.py -

退出码：
  0 = 未发现敏感字段
  1 = 发现敏感字段
  2 = 输入错误
"""

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 校验算法

def _id_card_valid(s: str) -> bool:
    """18 位身份证校验位（ISO 7064 MOD 11-2）。"""
    s = s.upper()
    if len(s) != 18 or not re.fullmatch(r"\d{17}[\dX]", s):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    codes = "10X98765432"
    total = sum(int(s[i]) * weights[i] for i in range(17))
    return codes[total % 11] == s[17]


def _luhn_valid(s: str) -> bool:
    """银行卡号 Luhn 校验。"""
    if not s.isdigit():
        return False
    total, alt = 0, False
    for ch in reversed(s):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


# ---------------------------------------------------------------- 规则表

RULES = [
    {
        "name": "身份证号",
        "regex": re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)"),
        "validate": _id_card_valid,
        "risk": "高",
        "advice": "对外必须完全脱敏；对内入账/报销可保留原文",
    },
    {
        "name": "银行卡号",
        "regex": re.compile(r"(?<!\d)(\d{16,19})(?!\d)"),
        "validate": _luhn_valid,
        "risk": "高",
        "advice": "对外必须完全脱敏；对内对账可保留原文",
    },
    {
        "name": "统一社会信用代码",
        "regex": re.compile(r"(?<![0-9A-Za-z])([0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10})(?![0-9A-Za-z])"),
        "validate": lambda s: s.isupper() or s.isdigit(),
        "risk": "中",
        "advice": "对外建议部分掩码；合同/发票场景通常需保留",
    },
    {
        "name": "手机号",
        "regex": re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"),
        "validate": None,
        "risk": "中",
        "advice": "对外建议部分掩码（保留前 3 后 4）",
    },
    {
        "name": "邮箱",
        "regex": re.compile(r"(?<![0-9A-Za-z._%+-])([\w.+-]+@[\w-]+\.[\w.]{2,})(?![0-9A-Za-z])"),
        "validate": None,
        "risk": "低",
        "advice": "对外分享建议部分掩码；商务往来通常需保留",
    },
    {
        "name": "IPv4 地址",
        "regex": re.compile(r"(?<!\d)((?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})(?!\d)"),
        "validate": None,
        "risk": "低",
        "advice": "内网地址一般无需脱敏；公网服务器地址对外建议掩码",
    },
]

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".yml", ".yaml", ".xml", ".log", ".html", ".htm"}


def mask(value: str) -> str:
    """生成掩码预览，仅用于展示，不写入任何文件。"""
    n = len(value)
    if n <= 4:
        return "*" * n
    if n <= 8:
        return value[:1] + "*" * (n - 2) + value[-1:]
    return value[:3] + "*" * (n - 7) + value[-4:]


def scan_text(text: str, source: str = "<stdin>"):
    """扫描一段文本，返回命中列表。"""
    hits = []
    claimed = []  # 已归属更具体规则的区间，避免重复计数

    for rule in RULES:
        for m in rule["regex"].finditer(text):
            val = m.group(1)
            if rule["validate"] and not rule["validate"](val):
                continue
            start, end = m.span(1)
            if any(start < c[1] and end > c[0] for c in claimed):
                continue
            claimed.append((start, end))
            line_no = text.count("\n", 0, start) + 1
            hits.append(
                {
                    "source": source,
                    "type": rule["name"],
                    "risk": rule["risk"],
                    "line": line_no,
                    "masked": mask(val),
                    "advice": rule["advice"],
                }
            )
    return hits


def iter_files(path: str):
    if os.path.isfile(path):
        yield path
        return
    for root, _dirs, files in os.walk(path):
        for f in files:
            yield os.path.join(root, f)


def read_text(path: str):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return None, str(exc)
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return None, "跳过：非文本扩展名（本脚本只做文本层扫描，不解析 Office/二进制内部）"
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return None, "跳过：编码无法识别"


def main():
    ap = argparse.ArgumentParser(description="敏感字段自查（只报告，不改写原文）")
    ap.add_argument("path", help="文件或目录路径；传 - 表示从标准输入读取")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--show-value", action="store_true", help="同时输出完整原文（默认只显示掩码）")
    args = ap.parse_args()

    all_hits, skipped = [], []

    if args.path == "-":
        text = sys.stdin.read()
        all_hits = scan_text(text, "<stdin>")
    elif not os.path.exists(args.path):
        print(f"[FAIL] 路径不存在：{args.path}", file=sys.stderr)
        return 2
    else:
        for fp in iter_files(args.path):
            text, err = read_text(fp)
            if err:
                skipped.append((fp, err))
                continue
            all_hits.extend(scan_text(text, fp))

    if args.json:
        print(json.dumps({"hits": all_hits, "skipped": skipped}, ensure_ascii=False, indent=2))
        return 1 if all_hits else 0

    print("=" * 68)
    print("敏感字段自查报告（只报告，未修改任何文件）")
    print("=" * 68)

    if not all_hits:
        print("[OK] 未发现敏感字段。")
    else:
        print(f"[WARN] 发现 {len(all_hits)} 处敏感字段：\n")
        print(f"{'类型':<12}{'风险':<6}{'行号':<8}{'掩码预览':<24}{'来源'}")
        print("-" * 68)
        for h in all_hits:
            print(f"{h['type']:<12}{h['risk']:<6}{h['line']:<8}{h['masked']:<24}{os.path.basename(h['source'])}")
        print("\n处理建议：")
        seen = set()
        for h in all_hits:
            if h["type"] in seen:
                continue
            seen.add(h["type"])
            print(f"  - {h['type']}（风险{h['risk']}）：{h['advice']}")

    if skipped:
        print(f"\n[提示] 跳过 {len(skipped)} 个文件：")
        for fp, err in skipped[:10]:
            print(f"  - {os.path.basename(fp)}：{err}")
        if len(skipped) > 10:
            print(f"  ... 其余 {len(skipped) - 10} 个略")

    print("\n下一步：告诉我你要「对内用」还是「对外发」，我再决定保留原文 / 部分掩码 / 完全脱敏。")
    return 1 if all_hits else 0


if __name__ == "__main__":
    sys.exit(main())
