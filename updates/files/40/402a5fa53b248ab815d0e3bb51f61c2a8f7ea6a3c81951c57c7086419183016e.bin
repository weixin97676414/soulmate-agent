# -*- coding: utf-8 -*-
"""
大纲骨架生成：素材库 → outline.json（页面 P-x + 要点占位）

骨架只给「结构」，不给「内容」：每页预置角色/标题/目标，并按素材相似度推荐候选，
要点需由 AI 依据候选素材填写（quote 必须逐字来自素材），填完跑 check_outline.py 校验。
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_outline import (  # noqa: E402
    DEFAULT_PAGES, ROLE_MINUTES, empty_outline, load_json, save_json,
    similarity, die,
)

# 三套主线预设
PRESETS = {
    "problem": DEFAULT_PAGES,  # 客户还不觉得痛：背景→痛点→方案→…
    "solution": [
        {"role": "封面", "title": "开场", "goal": "一句话讲清方案与价值"},
        {"role": "背景", "title": "需求回顾", "goal": "对齐客户已提出的需求"},
        {"role": "方案", "title": "整体方案", "goal": "讲清方案边界与形态"},
        {"role": "能力", "title": "核心能力", "goal": "展开关键能力"},
        {"role": "能力", "title": "差异化优势", "goal": "说明与备选方案的差别"},
        {"role": "案例", "title": "同类客户验证", "goal": "用同行数据佐证"},
        {"role": "路线", "title": "实施与交付", "goal": "说明周期与投入"},
        {"role": "保障", "title": "服务与保障", "goal": "回应交付风险"},
        {"role": "收尾", "title": "商务与下一步", "goal": "推进到下一步动作"},
    ],
    "internal": [
        {"role": "封面", "title": "结论先行", "goal": "先给结论与请求"},
        {"role": "背景", "title": "现状与问题", "goal": "说明为什么要做"},
        {"role": "方案", "title": "方案与选型", "goal": "讲清方案与备选对比"},
        {"role": "价值", "title": "投入与收益", "goal": "量化投入产出"},
        {"role": "路线", "title": "实施计划", "goal": "分阶段与里程碑"},
        {"role": "保障", "title": "风险与应对", "goal": "主动列出风险与预案"},
        {"role": "收尾", "title": "需要的支持", "goal": "明确要资源还是要决策"},
    ],
}

ROLE_HINTS = {
    "封面": "主题 价值 简介 概览 关于",
    "背景": "背景 现状 行业 趋势 市场 现状",
    "痛点": "问题 痛点 挑战 困难 风险 不足 瓶颈",
    "方案": "方案 整体 架构 设计 思路 总体 解决",
    "能力": "能力 功能 特性 模块 支持 提供 实现",
    "价值": "价值 收益 效果 提升 降本 效率 ROI 数据 指标",
    "案例": "案例 客户 实践 落地 效果 验证 试点",
    "路线": "计划 路线 阶段 里程碑 排期 实施 交付 时间",
    "保障": "保障 风险 合规 安全 应对 措施 支持 服务",
    "收尾": "总结 下一步 行动 联系 期待 合作",
}


def candidates_for(role, title, mats, topk=4):
    query = "%s %s %s" % (role, title, ROLE_HINTS.get(role, ""))
    scored = []
    for m in mats:
        s = similarity(query, (m.get("section", "") + " " + m.get("text", ""))[:400])
        s += 0.25 * similarity(ROLE_HINTS.get(role, ""), m.get("text", "")[:300])
        scored.append((round(s, 3), m))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    out = []
    for s, m in scored[:topk]:
        if s < 0.03:
            continue
        out.append({
            "sid": m["id"],
            "score": s,
            "section": m.get("section", ""),
            "excerpt": m["text"].replace("\n", " ")[:60],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="生成演示大纲骨架 outline.json")
    ap.add_argument("--materials", required=True, help="materials.json")
    ap.add_argument("--name", default="", help="演示材料名称")
    ap.add_argument("--audience", default="", help="受众（如：客户技术负责人）")
    ap.add_argument("--goal", default="", help="本次演示要达成的目标")
    ap.add_argument("--duration", type=int, default=30, help="讲稿总时长（分钟）")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="problem",
                    help="主线预设：problem 问题导向（默认）/ solution 方案导向 / internal 内部汇报")
    ap.add_argument("--pages", help="自定义页面，格式「角色:标题」逗号分隔；优先级高于 --preset")
    ap.add_argument("--topk", type=int, default=4, help="每页推荐候选素材数")
    ap.add_argument("-o", "--out", required=True, help="输出 outline.json")
    args = ap.parse_args()

    if not os.path.isfile(args.materials):
        die("素材库不存在：%s" % args.materials)
    mj = load_json(args.materials)
    mats = mj.get("materials", [])

    if args.pages:
        specs = []
        for seg in args.pages.split(","):
            seg = seg.strip()
            if not seg:
                continue
            if ":" in seg:
                role, title = seg.split(":", 1)
            elif "|" in seg:
                role, title = seg.split("|", 1)
            else:
                role, title = "", seg
            specs.append({"role": role.strip(), "title": title.strip(), "goal": ""})
    else:
        specs = [dict(p) for p in PRESETS[args.preset]]

    ol = empty_outline(args.name, args.audience, args.goal, args.duration)
    ol["meta"]["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ol["meta"]["materials"] = os.path.abspath(args.materials)
    ol["materials_total"] = len(mats)

    for i, sp in enumerate(specs, 1):
        page = {
            "id": "P-%d" % i,
            "role": sp.get("role", ""),
            "title": sp.get("title", ""),
            "goal": sp.get("goal", ""),
            "minutes": ROLE_MINUTES.get(sp.get("role", ""), 2),
            "points": [],
            "candidates": candidates_for(sp.get("role", ""), sp.get("title", ""),
                                         mats, args.topk),
        }
        ol["pages"].append(page)

    save_json(args.out, ol)

    print("大纲骨架已生成：%s" % args.out)
    print("  页面数：%d | 素材条目：%d | 计划时长：%d 分钟"
          % (len(ol["pages"]), len(mats), args.duration))
    print()
    for p in ol["pages"]:
        cds = "、".join(c["sid"] for c in p["candidates"][:3]) or "无"
        print("  %s [%s] %s —— 候选素材：%s" % (p["id"], p["role"] or "-", p["title"], cds))
    print()
    print("下一步：按候选素材填写每页 points（text / quote / sid），再跑 check_outline.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
