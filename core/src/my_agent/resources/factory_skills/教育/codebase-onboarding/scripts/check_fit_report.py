#!/usr/bin/env python3
# -*- coding: utf-8 -*-
















import argparse
import os
import re
import sys

FR_PAT = re.compile(r"\bFR-\d{1,2}\b")
VERDICT_PAT = re.compile(r"(原生支持|改造支持|扩展支持|不涵盖)")
CAN_PAT = re.compile(r"\*\*能否实现\*\*|能否实现[:：]")
LOC_PAT = re.compile(r"[\w\-./]+\.(?:java|kt|kts|py|js|jsx|ts|tsx|go|rs|rb|cs|scala|"
                     r"vue|html|css|xml|yml|yaml|json|toml|gradle|properties|sql|md|sh)"
                     r"\s*:\s*\d+")
EFFORT_PAT = re.compile(r"\b(XS|S|M|L|XL)\s*[·|\-—~]?\s*"
                        r"(?:\d+(?:\.\d+)?\s*[-~]\s*)?\d+(?:\.\d+)?\s*(?:人日|人天|d\b)")
EFFORT_BASIS_PAT = re.compile(r"依据[:：]|（依据|\(依据")
PREMISE_PAT = re.compile(r"估算前提|前提[:：]")
GAP_PAT = re.compile(r"缺口\s*G-\d{1,2}")
PATH_ROW_PAT = re.compile(r"\|\s*(?:A|B|C)\s*[^|]*\|")
UPGRADE_PAT = re.compile(r"升级影响")
RECOMMEND_PAT = re.compile(r"推荐")
SUMMARY_PAT = re.compile(r"总(?:人日|工作量)|基准工作量")
CRITICAL_PAT = re.compile(r"关键路径")
RISK_PAT = re.compile(r"风险\s*Top\s*\d|风险\s*Top3")
CONCLUSION_PAT = re.compile(r"结论建议|建议[:：]")
BASELINE_PAT = re.compile(r"需求基线|基线")
CLARIFY_PAT = re.compile(r"澄清")
TODO_PAT = re.compile(r"\b(TODO|FIXME|待补充|待评估|TBD)\b")


def split_items(text):

    blocks = re.split(r"\n(?=#{2,4}\s*FR-\d)", text)
    return [b for b in blocks if re.match(r"\s*#{2,4}\s*FR-\d", b)]


def check(path):
    errors, warns, infos = [], [], []
    text = open(path, encoding="utf-8", errors="ignore").read()

    
    frs = sorted(set(FR_PAT.findall(text)))
    if not frs:
        errors.append("未发现原子需求项编号（FR-xx）——需求必须先拆成可独立判定的功能项")
        return errors, warns, infos
    infos.append(f"需求项 {len(frs)} 个: {', '.join(frs[:8])}"
                 + ("…" if len(frs) > 8 else ""))

    
    if CLARIFY_PAT.search(text):
        infos.append("含需求澄清记录")
    else:
        warns.append("缺少需求澄清记录——有歧义的需求应先走澄清表（≤5问/轮，≤3轮）")
    if BASELINE_PAT.search(text):
        infos.append("含需求基线")
    else:
        errors.append("缺少「需求基线」——基线未冻结就评估，结论不可复核")

    
    blocks = split_items(text)
    if not blocks:
        warns.append("未发现 `### FR-xx` 逐项段落，无法逐条校验（需求项 >3 条时应逐项展开）")
    for b in blocks:
        fid = FR_PAT.search(b).group(0)
        if not VERDICT_PAT.search(b):
            errors.append(f"{fid} 缺少四分类判定（原生支持/改造支持/扩展支持/不涵盖）")
        if not CAN_PAT.search(b):
            warns.append(f"{fid} 缺少「能否实现」档位（能/部分能/不能）")
        if not LOC_PAT.search(b):
            errors.append(f"{fid} 「修改位置」未精确到 文件:行号（只写目录等于没定位）")
        if not EFFORT_PAT.search(b):
            errors.append(f"{fid} 「工作量」缺档位+人日（应为 XS/S/M/L/XL · N 人日）")
        elif not EFFORT_BASIS_PAT.search(b):
            errors.append(f"{fid} 「工作量」只给了数字没给估算依据")

    
    if PREMISE_PAT.search(text):
        infos.append("已写明估算前提")
    else:
        errors.append("未写明「估算前提」（含什么/不含什么）——脱离前提的工时可当作废")

    
    gaps = GAP_PAT.findall(text)
    if "不涵盖" in text:
        if not gaps:
            errors.append("存在「不涵盖」项但没有缺口补充方案（G-xx）——只说不支持视为不合格")
        else:
            infos.append(f"缺口补充方案 {len(gaps)} 个")
            gblocks = re.split(r"\n(?=#{2,4}\s*缺口\s*G-\d)", text)
            for g in gblocks:
                if not GAP_PAT.match(re.sub(r"^#+\s*", "", g.strip())):
                    continue
                if len(PATH_ROW_PAT.findall(g)) < 2:
                    errors.append("缺口方案需 ≥2 条补齐路径对比（自建/第三方/调整需求）")
                if not UPGRADE_PAT.search(g):
                    warns.append("缺口方案缺少「升级影响」列——fork 后能否跟上游是核心成本")
                if not RECOMMEND_PAT.search(g):
                    errors.append("缺口方案缺少「推荐」——只列选项不给结论等于没评估")
    else:
        infos.append("无「不涵盖」项")

    
    for pat, name in ((SUMMARY_PAT, "总工作量"),
                      (CRITICAL_PAT, "关键路径"),
                      (RISK_PAT, "风险 Top3"),
                      (CONCLUSION_PAT, "结论建议")):
        if pat.search(text):
            infos.append(f"含{name}")
        else:
            warns.append(f"缺少{name}——汇总段不完整，无法支撑决策")

    
    todos = TODO_PAT.findall(text)
    if todos:
        errors.append(f"存在占位标记 {len(todos)} 处: " + "、".join(sorted(set(todos))[:4]))

    return errors, warns, infos


def main():
    ap = argparse.ArgumentParser(description="需求满足度评估报告自检")
    ap.add_argument("path", help="报告 markdown 文件")
    a = ap.parse_args()

    if not os.path.exists(a.path):
        sys.stderr.write(f"[错误] 文件不存在: {a.path}\n")
        sys.exit(1)

    errors, warns, infos = check(a.path)
    print("=" * 62)
    print(f"评估报告自检 · {os.path.basename(os.path.abspath(a.path))}")
    print("=" * 62)
    for i in infos:
        print(f"INFO  {i}")
    for w in warns:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print("-" * 62)
    if errors:
        print(f"结论：{len(errors)} 个 ERROR，不符合交付标准，修完再交付。")
        return 1
    print("结论：无 ERROR，可以交付。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
