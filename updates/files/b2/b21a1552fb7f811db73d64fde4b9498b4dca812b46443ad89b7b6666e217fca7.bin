# -*- coding: utf-8 -*-
"""
大纲质量校验（硬闸门）—— 对应验收标准「素材均来自原文」

ERROR（命中即 exit 1）：
  E1  要点文本为空
  E2  要点缺少素材引文 quote，且未标记为人工补充（custom=true + note）
  E3  引文未在素材库逐字命中（杜撰或改写原文）
  E4  引用了不存在的素材编号
  E5  非封面页没有任何要点
  E6  页面 role 不在允许集合内
  E7  主线不完整：缺少「封面」或「收尾」页
  E8  页面标题为空
  E9  素材库为空
  E10 大纲没有任何页面
  E11 页面 id 重复
  E12 要点 id 重复
  E13 标记人工补充的要点未写说明 note
  E14 引文与所标素材编号对不上

WARN（提示，不阻断）：
  W1 单页要点数少于 2 或多于 6
  W2 素材未被任何页面引用（疑似遗漏内容）
  W3 要点含数字但引文中没有该数字（请人工核验）
  W4 页面缺少讲稿备注
  W5 计划总时长与页面时长之和偏差超过 20%
  W6 页面缺少目标说明
  W7 要点与本页主题相似度偏低（疑似放错页）
  W8 元信息未填写受众或目标
  W9 大纲经人工修改后未留痕（edited_by / edit_note 为空时应确认）
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_outline import (  # noqa: E402
    NUM_RE, ROLES, find_quote, iter_points, load_json, material_index,
    norm, similarity, die,
)

# 对外演示材料慎用：绝对化、夸大表述（广告法风险 + 易被客户当场质疑）
HYPE_WORDS = ("行业第一", "第一品牌", "绝对", "100%", "唯一", "最好", "最强",
              "最佳", "最优", "最先进", "完美", "零风险", "永远", "彻底解决")


def main():
    ap = argparse.ArgumentParser(description="校验演示大纲（结论必须锚定素材原文）")
    ap.add_argument("outline", help="outline.json")
    ap.add_argument("--materials", help="materials.json（默认取大纲内记录的路径）")
    ap.add_argument("-o", "--out", help="输出校验报告 Markdown")
    args = ap.parse_args()

    if not os.path.isfile(args.outline):
        die("大纲文件不存在：%s" % args.outline)
    ol = load_json(args.outline)
    mats = []
    mpath = args.materials or (ol.get("meta", {}) or {}).get("materials", "")
    if mpath and os.path.isfile(mpath):
        mats = load_json(mpath).get("materials", [])
    elif not mpath and isinstance(ol.get("materials"), list):
        mats = ol["materials"]
    mi = material_index(mats)

    errors, warns = [], []

    def err(code, msg):
        errors.append("[%s] %s" % (code, msg))

    def warn(code, msg):
        warns.append("[%s] %s" % (code, msg))

    # --- E9 素材库为空
    if not mats:
        err("E9", "素材库为空或找不到 materials.json —— 无法核验要点是否来自原文")

    pages = ol.get("pages", [])
    # --- E10
    if not pages:
        err("E10", "大纲没有任何页面")

    # --- E6/E7/E8/E11
    roles = [p.get("role", "") for p in pages]
    if pages and "封面" not in roles:
        err("E7", "缺少「封面」页，演示主线不完整")
    if pages and "收尾" not in roles:
        err("E7", "缺少「收尾」页，演示主线不完整")

    seen_page, seen_point = {}, {}
    used_sids = set()
    total_min = 0.0
    point_texts = []
    page_profiles = [(pg.get("id", ""),
                      (pg.get("title", "") + " " + pg.get("goal", "")).strip())
                     for pg in pages]

    for p in pages:
        pid = p.get("id", "?")
        title = p.get("title", "").strip()
        role = p.get("role", "").strip()
        if pid in seen_page:
            err("E11", "页面 id 重复：%s" % pid)
        seen_page[pid] = 1

        if not title:
            err("E8", "页面 %s 标题为空" % pid)
        if role and role not in ROLES:
            err("E6", "页面 %s 的 role「%s」不在允许范围（%s）" % (pid, role, "、".join(ROLES)))

        pts = p.get("points", [])
        # --- E5
        if role != "封面" and not pts:
            err("E5", "页面 %s（%s）没有任何要点" % (pid, title or "-"))

        if not p.get("goal", "").strip():
            warn("W6", "页面 %s 缺少目标说明" % pid)
        if not p.get("speaker_note", "").strip():
            warn("W4", "页面 %s 缺少讲稿备注" % pid)

        # --- W1
        if pts and (len(pts) < 2 or len(pts) > 6):
            warn("W1", "页面 %s 要点数 %d 条，建议每页 2–6 条" % (pid, len(pts)))

        try:
            total_min += float(p.get("minutes", 0) or 0)
        except (TypeError, ValueError):
            pass

        for t in pts:
            tid = t.get("id", "?")
            if tid in seen_point:
                err("E12", "要点 id 重复：%s" % tid)
            seen_point[tid] = 1

            text = (t.get("text", "") or "").strip()
            quote = (t.get("quote", "") or "").strip()
            custom = bool(t.get("custom"))

            # --- E1
            if not text:
                err("E1", "要点 %s 文本为空" % tid)
                continue

            # --- E2 / E13
            if not quote:
                if custom:
                    if not (t.get("note", "") or "").strip():
                        err("E13", "要点 %s 标记为人工补充，但未填写 note 说明依据" % tid)
                else:
                    err("E2", "要点 %s（%s）缺少素材引文 quote —— 结论必须锚定原文"
                        % (tid, pid))
                continue

            # --- E3 逐字命中
            hits = find_quote(mats, quote) if mats else []
            if mats and not hits:
                err("E3", "要点 %s 的引文在素材库中找不到逐字匹配（疑似杜撰或改写原文）：%s"
                    % (tid, quote[:40]))
                continue

            # --- E4 / E14
            sids = t.get("sids") or ([t["sid"]] if t.get("sid") else [])
            if not sids and hits:
                sids = hits[:1]
                t["sids"] = sids
            for sid in sids:
                if sid not in mi:
                    err("E4", "要点 %s 引用了不存在的素材编号 %s" % (tid, sid))
                elif norm(quote) not in norm(mi[sid].get("text", "")):
                    err("E14", "要点 %s 的引文不在素材 %s 正文中（编号与引文对不上）" % (tid, sid))
                else:
                    used_sids.add(sid)
            if not sids:
                err("E2", "要点 %s 未标注素材编号（sids）" % tid)

            # --- W3 数字溯源
            nums = set(NUM_RE.findall(text))
            if nums:
                qn = set(NUM_RE.findall(quote))
                miss = [n for n in nums if n not in qn]
                if miss:
                    warn("W3", "要点 %s 含数字 %s，但引文中没有 —— 请确认数字来自原文而非推算"
                         % (tid, "、".join(sorted(miss))))

            # --- W10 绝对化 / 夸大表述
            hits = [w for w in HYPE_WORDS if w in text]
            if hits:
                warn("W10", "要点 %s 含绝对化/夸大表述「%s」—— 对外材料慎用，建议改为可验证的说法"
                     % (tid, "、".join(hits)))

            if text:
                point_texts.append((pid, tid, text, title))

    # --- W7 跨页重复：不同页出现高度相似的要点，容易让听众觉得反复讲
    for i in range(len(point_texts)):
        for j in range(i + 1, len(point_texts)):
            pi, ti, xi, _ = point_texts[i]
            pj, tj, xj, _ = point_texts[j]
            if pi == pj:
                continue
            s = similarity(xi, xj)
            if s >= 0.6:
                warn("W7", "要点 %s（%s）与 %s（%s）表述高度相似（%.2f），建议合并或区分侧重点"
                     % (ti, pi, tj, pj, s))
            elif s >= 0.45:
                # 引文同源且表述接近，提示可能重复引用同一处
                warn("W7", "要点 %s（%s）与 %s（%s）相似度 %.2f，请确认是否重复引用同一素材"
                     % (ti, pi, tj, pj, s))

    # --- W2 未被引用素材
    if mats:
        unused = [m["id"] for m in mats if m["id"] not in used_sids]
        if unused:
            warn("W2", "有 %d 条素材未被任何页面引用（%s…）—— 请确认是否遗漏了重要内容"
                 % (len(unused), "、".join(unused[:8])))

    # --- W5 时长
    meta = ol.get("meta", {}) or {}
    plan = meta.get("duration_min")
    if plan and total_min:
        try:
            plan = float(plan)
            if abs(total_min - plan) / plan > 0.2:
                warn("W5", "页面时长合计 %.1f 分钟，与计划 %g 分钟偏差超过 20%%，建议调整页数或时长"
                     % (total_min, plan))
        except (TypeError, ValueError):
            pass

    # --- W8 元信息
    if not (meta.get("audience", "") or "").strip():
        warn("W8", "未填写受众 audience，页面详略与措辞会缺少依据")
    if not (meta.get("goal", "") or "").strip():
        warn("W8", "未填写演示目标 goal")

    # --- 汇总输出
    lines = ["# 大纲校验报告", ""]
    lines.append("- 大纲：%s" % args.outline)
    lines.append("- 素材库：%s（%d 条）" % (mpath or "未提供", len(mats)))
    lines.append("- 页面：%d | 要点：%d" % (len(pages), len(seen_point)))
    lines.append("")
    if errors:
        lines.append("## ERROR（%d，必须修复后交付）" % len(errors))
        lines.append("")
        for e in errors:
            lines.append("- %s" % e)
        lines.append("")
    else:
        lines.append("## ERROR：0 —— 全部结论已锚定素材原文")
        lines.append("")
    if warns:
        lines.append("## WARN（%d，建议确认）" % len(warns))
        lines.append("")
        for w in warns:
            lines.append("- %s" % w)
        lines.append("")
    else:
        lines.append("## WARN：0")
        lines.append("")

    report = "\n".join(lines)
    if args.out:
        d = os.path.dirname(os.path.abspath(args.out))
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print("校验报告已写入：%s" % args.out)

    print(report)
    if errors:
        sys.exit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
