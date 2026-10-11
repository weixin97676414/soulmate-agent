# -*- coding: utf-8 -*-
"""
活人感原创短视频 · 拍摄方案半自动生成器
归属：video-script-dissect 技能（归属② 活人感拍摄建议确认门）
用法：
  python shoot_advisor.py --topic "主题" --scene "计划场景" --audience "观众" [--script "已有脚本"]
  python shoot_advisor.py --brief brief.json
输出：6 段活人感拍摄方案框架（段1/4/6 自动生成，段2/3/5 由 AI 结合本视频补写）
纯标准库，无第三方依赖。
"""
import argparse
import json
import sys


# 场景预制感风险词典
HIGH_RISK = ["坐", "固定", "室内", "棚", "口播", "书桌", "客厅", "工位", "绿幕", "背景墙", "沙发", "念稿"]
LOW_RISK = ["走", "外", "现场", "夜市", "工地", "停车场", "机房", "门店", "夜", "街", "菜市场", "厂区", "仓库", "展位", "咖啡馆"]


def scene_risk(scene: str):
    s = scene or ""
    has_high = any(k in s for k in HIGH_RISK)
    has_low = any(k in s for k in LOW_RISK)
    if has_high and not has_low:
        return "🔴 高危", "计划场景偏「固定/坐播/室内」，预制感重，用户一眼看出来。"
    if has_high and has_low:
        return "🟡 中危", "场景有关联但也有坐播痕迹，需靠真情绪+即兴毛边拉回。"
    if has_low:
        return "🟢 安全", "场景高关联（走动/夜间/真实经营），已是半即兴状态。"
    return "🟡 中危", "场景描述不足，无法判定关联度，建议补足「在哪拍、是否走动」。"


def device_tip(audience: str):
    a = audience or ""
    if "不自然" in a or "端着" in a or "敬畏" in a:
        return "建议 **pocket + 朋友抓拍**（你提到对镜头不自然/有敬畏感，抓拍能激发对象感）。"
    return "默认 **手机拍**（最快、最活）；若实拍时对镜头仍端着，随时切 pocket+抓拍。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="")
    ap.add_argument("--scene", default="")
    ap.add_argument("--audience", default="")
    ap.add_argument("--script", default="")
    ap.add_argument("--brief", default="")
    args = ap.parse_args()

    if args.brief:
        with open(args.brief, "r", encoding="utf-8") as f:
            b = json.load(f)
        topic = b.get("topic", "")
        scene = b.get("scene", "")
        audience = b.get("audience", "")
        script = b.get("script", "")
    else:
        topic, scene, audience, script = args.topic, args.scene, args.audience, args.script

    risk_level, risk_msg = scene_risk(scene)

    out = []
    out.append("# 活人感拍摄方案 · " + (topic or "（未填主题）"))
    out.append("")
    out.append("> 输入 brief：主题=`%s` 场景=`%s` 观众=`%s`" % (topic, scene, audience))
    out.append("")
    out.append("## 1. 场景关联诊断（自动）")
    out.append("- 预制感风险：**%s** —— %s" % (risk_level, risk_msg))
    out.append("- 改法：能走着不坐着 / 能晚上不白天 / 能去真实经营场景不固定摆拍。")
    out.append("")
    out.append("## 2. AI 备课清单（AI 补写）")
    out.append("- 去场景前 5–10 分跟 AI 聊：这场景能讲点啥？（名字由来/人文/数据/争议）")
    out.append("- 针对本主题待补 3–5 个具体问题：___")
    out.append("")
    out.append("## 3. 情绪锚点（AI 补写）")
    out.append("- 本条约露的真实情绪（惊/怒/喜/尬/顿悟）：___")
    out.append("- 在场景里怎么被「刺激」出来：___")
    out.append("")
    out.append("## 4. 设备建议（自动）")
    out.append("- " + device_tip(audience))
    out.append("")
    out.append("## 5. 即兴留白（AI 补写）")
    out.append("- 故意不准备好的那一处（口误/环境干扰/临时起意）：___")
    out.append("")
    out.append("## 6. 拍完 5 问自检（自动）")
    out.append("1. [ ] 真实场景被刺激后拍的？非纯摆拍？")
    out.append("2. [ ] 露了当下真实情绪（惊/怒/喜/尬）？")
    out.append("3. [ ] 对「眼前这人这事」说，不是对镜头念稿？")
    out.append("4. [ ] 有一处没准备好的即兴痕迹？")
    out.append("5. [ ] 专业里夹了「人味」（观点/态度/取舍）？")
    out.append("")
    out.append("> ≥3 个勾 = 这条有活人感，发。")

    print("\n".join(out))


if __name__ == "__main__":
    main()
