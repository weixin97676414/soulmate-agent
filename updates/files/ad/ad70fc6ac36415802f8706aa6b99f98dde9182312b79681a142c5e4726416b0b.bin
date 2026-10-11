# -*- coding: utf-8 -*-
"""图模型校验：id 唯一 / 边引用有效 / 无孤立节点 / type 合法 / 说明齐全。

有 ERROR 时退出码 1，阻断后续产出。
用法: python check_graph.py graph.json [--md 报告.md]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_graph import (load, VALID_TYPES, GRAPH_TYPES, MAX_LABEL,  # noqa: E402
                       node_size, text_width)


def check(g):
    errors, warns = [], []
    nodes, edges, groups = g.get("nodes", []), g.get("edges", []), g.get("groups", [])
    meta = g.get("meta") or {}
    gtype = meta.get("graph_type")

    def E(code, detail):
        errors.append({"code": code, "detail": detail})

    def W(code, detail):
        warns.append({"code": code, "detail": detail})

    # --- meta ---
    for f, label in (("title", "标题"), ("purpose", "图的目的")):
        if not (meta.get(f) or "").strip():
            E("E1", "meta.%s（%s）缺失" % (f, label))
    if not gtype:
        E("E1", "meta.graph_type 缺失")
    elif gtype not in GRAPH_TYPES:
        E("E1", "meta.graph_type 非法：%s（应为 %s）"
          % (gtype, " / ".join(sorted(GRAPH_TYPES))))

    # --- id 唯一 ---
    for kind, items in (("node", nodes), ("edge", edges), ("group", groups)):
        seen, dup = set(), []
        for x in items:
            i = x.get("id")
            if not i:
                E("E2", "%s 缺少 id：%s" % (kind, json.dumps(x, ensure_ascii=False)[:60]))
                continue
            if i in seen:
                dup.append(i)
            seen.add(i)
        if dup:
            E("E2", "%s id 重复：%s" % (kind, "、".join(sorted(set(dup)))))

    ids = {n.get("id") for n in nodes}
    gids = {x.get("id") for x in groups}

    # --- 节点 ---
    for n in nodes:
        nid = n.get("id")
        if not (n.get("label") or "").strip():
            E("E3", "节点 %s 缺 label" % nid)
        t = n.get("type")
        if not t:
            W("W3", "节点 %s 缺 type，已按 component 处理" % nid)
        elif t not in VALID_TYPES:
            W("W3", "节点 %s 的 type「%s」不在类型表内" % (nid, t))
        if not (n.get("desc") or "").strip():
            W("W4", "节点 %s 缺 desc（图形说明会无内容可写）" % nid)
        lb = (n.get("label") or "")
        if len(lb) > MAX_LABEL:
            W("W6", "节点 %s 标签 %d 字，超过 %d 字建议上限，可能撑破图元"
              % (nid, len(lb), MAX_LABEL))
        gg = n.get("group")
        if gg and gg not in gids:
            E("E2", "节点 %s 引用了不存在的 group：%s" % (nid, gg))
        # 文本溢出：所需行数超过节点高度会压边（等于打开乱版）
        if n.get("label"):
            w, h = node_size(n)
            need = math.ceil(text_width(n["label"], 12) / max(40, w - 20))
            if need * 16 > h:
                W("W7", "节点 %s 标签需 %d 行（%dpx）超出节点高度 %dpx，会压边，"
                  "建议缩短至 %d 字内" % (nid, need, need * 16, h, MAX_LABEL))

    # --- 边 ---
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in ids:
            E("E0", "边 %s 的 source「%s」不存在（悬挂连线）" % (e.get("id"), s))
        if t not in ids:
            E("E0", "边 %s 的 target「%s」不存在（悬挂连线）" % (e.get("id"), t))
        if gtype in ("architecture", "flowchart", "er") and not (e.get("label") or "").strip():
            W("W5", "边 %s 缺 label，建议写清传什么/为什么" % e.get("id"))
        if gtype == "sequence" and not isinstance(e.get("seq"), int):
            E("E5", "时序图消息 %s 缺 seq，无法确定时序" % e.get("id"))

    # --- 孤立节点 ---
    linked = set()
    for e in edges:
        linked.add(e.get("source"))
        linked.add(e.get("target"))
    for n in nodes:
        if n.get("id") not in linked:
            W("W1", "孤立节点：%s（%s）——既无入边也无出边"
              % (n.get("id"), (n.get("label") or "")[:20]))

    # --- 类型专有规则 ---
    types = [n.get("type") for n in nodes]
    if gtype == "flowchart":
        if "start" not in types:
            E("E4", "流程图缺少 start 节点")
        if "end" not in types:
            W("W2", "流程图没有 end 节点")
        for n in nodes:
            if n.get("type") == "decision":
                outs = [e for e in edges if e.get("source") == n.get("id")]
                if len(outs) < 2:
                    W("W2", "判断节点 %s 只有 %d 条出边，分支可能不全"
                      % (n.get("id"), len(outs)))
                for e in outs:
                    if not (e.get("label") or "").strip():
                        E("E6", "判断节点 %s 的出边 %s 缺 label，无法区分分支"
                          % (n.get("id"), e.get("id")))
    if gtype == "er":
        for e in edges:
            lb = (e.get("label") or "").strip()
            if lb and not any(ch.isdigit() for ch in lb):
                W("W2", "ER 关系 %s 的 label「%s」未标基数（如 1:N）"
                  % (e.get("id"), lb))
    if gtype == "c4" and not groups:
        W("W2", "C4 图未定义 groups，系统边界无法体现")
    if gtype == "architecture" and not groups:
        W("W2", "架构图未定义 groups，建议用分组表达分层边界")
    if gtype == "state":
        if not any("init" in (n.get("id") or "").lower() for n in nodes):
            W("W2", "状态图未标识初态（建议 id 含 init）")
        if not any("final" in (n.get("id") or "").lower()
                   or (n.get("type") == "end") for n in nodes):
            W("W2", "状态图未标识终态")

    return errors, warns


def to_markdown(g, errors, warns, path):
    meta = g.get("meta") or {}
    L = ["# 图模型校验报告\n",
         "**图名**：%s　|　**类型**：%s　|　**节点** %d　**连线** %d　**分组** %d\n"
         % (meta.get("title") or "-", meta.get("graph_type") or "-",
            len(g.get("nodes", [])), len(g.get("edges", [])),
            len(g.get("groups", []))),
         "## 结论\n"]
    if errors:
        L.append("❌ **不通过** —— %d 个 ERROR，修复后重跑\n" % len(errors))
    else:
        L.append("✅ **通过** —— 无 ERROR%s\n"
                 % ("（%d 个 WARN 建议处理）" % len(warns) if warns else ""))
    if errors:
        L += ["## ERROR（必须修复）\n",
              "| 代码 | 问题 |", "|------|------|"]
        L += ["| %s | %s |" % (e["code"], e["detail"]) for e in errors]
        L.append("")
    if warns:
        L += ["## WARN（建议处理）\n", "| 代码 | 问题 |", "|------|------|"]
        L += ["| %s | %s |" % (w["code"], w["detail"]) for w in warns]
        L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--md", help="输出 Markdown 报告")
    a = ap.parse_args()
    g = load(a.graph)
    errors, warns = check(g)
    title = (g.get("meta") or {}).get("title") or os.path.basename(a.graph)
    print("图模型校验：%s" % title)
    print("  节点 %d / 连线 %d / 分组 %d"
          % (len(g.get("nodes", [])), len(g.get("edges", [])),
             len(g.get("groups", []))))
    if errors:
        print("\n  ERROR (%d)：" % len(errors))
        for e in errors:
            print("    [%s] %s" % (e["code"], e["detail"]))
    if warns:
        print("\n  WARN (%d)：" % len(warns))
        for w in warns:
            print("    [%s] %s" % (w["code"], w["detail"]))
    print("\n  结论：%s" % ("❌ 不通过，修复后重跑" if errors
                          else "✅ 通过%s" % ("（有 WARN）" if warns else "")))
    if a.md:
        to_markdown(g, errors, warns, a.md)
        print("  报告：%s" % a.md)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
