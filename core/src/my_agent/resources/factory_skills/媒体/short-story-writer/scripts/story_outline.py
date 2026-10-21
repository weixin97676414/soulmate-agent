#!/usr/bin/env python3
# -*- coding: utf-8 -*-











import argparse, sys, json
from datetime import datetime


TYPE_ALIASES = {
    "悬疑": "suspense", "反转": "suspense", "惊悚": "suspense", "恐怖": "suspense",
    "复仇": "revenge", "逆袭": "revenge", "打脸": "revenge",
    "甜宠": "sweet", "掉马": "sweet", "甜文": "sweet", "总裁": "sweet", "霸总": "sweet",
    "重生": "rebirth", "穿越": "rebirth",
    "系统": "system", "金手指": "system",
    "催泪": "reality", "现实": "reality", "亲情": "reality", "真实": "reality",
    "suspense": "suspense", "revenge": "revenge", "sweet": "sweet",
    "rebirth": "rebirth", "system": "system", "reality": "reality",
}

GENRES = {
    "suspense": {
        "aliases": ["悬疑", "反转", "惊悚", "恐怖"],
        "name": "悬疑反转",
        "platform": "zhihu",
        "narrator": "第一人称「我」",
        "structure": [
            ("日常异常", "平静表面下发现一个反常细节", "200-400字"),
            ("调查深入", "好奇心驱使下开始探究，发现更多碎片", "500-800字"),
            ("第一次震惊", "第一条线索指向一个可怕的真相", "300-500字"),
            ("假象反转", "你以为你知道了——但你知道的是错的", "400-600字"),
            ("终极真相", "最后一块拼图落下，真相比想象的更恐怖", "300-400字"),
            ("余味结尾", "最后一句话推翻前面所有认知，或者留下无法回答的问题", "100-200字"),
        ],
        "hooks": [
            "「[日常事物] + [不合理细节]」——如「我家猫每晚11点蹲门口。我家在18楼。」",
            "「[平静陈述] + [恐怖暗示]」——如「我老公一直很完美。除了他从来不笑。」",
            "「[时间标记] + [异常重复]」——如「第三天的凌晨3点。他又出门了。」",
        ],
        "endings": [
            "最后一句话反转：「后来我才知道，那天晚上……」",
            "开放式恐惧：「我到现在还在想，那个蛋糕是给谁的。」",
            "循环暗示：「明天。又是凌晨三点。」",
        ],
    },
    "revenge": {
        "aliases": ["复仇", "逆袭", "打脸", "爽文"],
        "name": "复仇逆袭",
        "platform": "both",
        "narrator": "知乎：第一人称 / 番茄：第三人称",
        "structure": [
            ("伤害场景", "用最痛的一幕开场——被背叛/被羞辱/被夺走一切", "200-400字"),
            ("隐忍布局", "不哭不闹。开始安静地准备。细节暗示计划在进行", "600-800字"),
            ("第一次出手", "第一击。不大，但精准。对方开始慌了", "400-600字"),
            ("对方反扑", "反派察觉后反扑，造成一次挫折——但这是主角计划中的", "400-500字"),
            ("致命一击", "精心准备了很久的那一下。反派彻底溃败", "500-700字"),
            ("胜利独白", "安静地宣布胜利。不张扬——但对方知道是谁做的", "200-300字"),
        ],
        "hooks": [
            "「[公开羞辱场景] + [主角反常平静]」",
            "「[时间跨度] + [第一击的结果]」——如「婚礼后第三天。她家公司破产了。」",
            "「[对话开场] + [暗示复仇已完成]」——如「'你放过我爸——''我放过了。去年就放过了。'」",
        ],
    },
    "sweet": {
        "aliases": ["甜宠", "掉马", "甜文", "总裁", "霸总"],
        "name": "甜宠掉马",
        "platform": "fanqie",
        "narrator": "第三人称，女主视角",
        "structure": [
            ("平凡日常", "女主与「普通人」男主的甜蜜日常——穷但温暖的细节", "300-400字"),
            ("第一个破绽", "一个不起眼的细节暴露了男主不简单", "200-300字"),
            ("身份揭露", "意外发现男主的真实身份——反转要足够震撼", "400-500字"),
            ("闹别扭", "女主觉得被欺骗，冷战/离家出走", "300-400字"),
            ("追妻火葬场", "男主放下所有身份追回——甜度拉满", "400-500字"),
            ("甜蜜日常2.0", "身份揭晓后的新日常——比之前更甜", "300-400字"),
        ],
    },
    "rebirth": {
        "aliases": ["重生", "穿越"],
        "name": "重生打脸",
        "platform": "fanqie",
        "narrator": "第三人称，女主视角",
        "structure": [
            ("惨死闪回", "开篇简短回忆上一世的悲惨结局", "100-200字"),
            ("重生觉醒", "回到关键时间节点——婚礼/签字/选择的那一刻", "300-400字"),
            ("第一次改命", "做出和上一世不同的选择，避开第一个坑", "400-500字"),
            ("渣男/渣女落魄", "凭借前世记忆，看着反派一步步走向自己挖的坑", "500-600字"),
            ("新的人生", "遇到比上一世好100倍的人/机会", "400-500字"),
            ("巅峰对比", "女主站在高处，反派跪在低处", "300-400字"),
        ],
    },
    "system": {
        "aliases": ["系统", "金手指"],
        "name": "系统爽文",
        "platform": "fanqie",
        "narrator": "第三人称，主角视角",
        "structure": [
            ("绑定系统", "社死/社畜/被欺负的至暗时刻 → 系统激活", "200-300字"),
            ("新手任务", "第一个任务——离谱但奖励诱人。完成后账户到账", "400-500字"),
            ("连续任务", "任务越来越离谱，奖励越来越丰厚。爽感递增", "600-800字"),
            ("遇到对手", "出现系统无法直接解决的人/事——需要主角自己动脑", "400-500字"),
            ("系统升级", "关键时刻系统升级，解锁新功能", "300-400字"),
            ("终极逆袭", "曾经欺负主角的人全部被打脸", "400-500字"),
        ],
    },
    "reality": {
        "aliases": ["催泪", "现实", "亲情", "真实"],
        "name": "现实催泪",
        "platform": "zhihu",
        "narrator": "第一人称「我」",
        "structure": [
            ("平凡日常", "用具体的物件/气味/声音建立日常感", "300-400字"),
            ("隐藏的情感", "暗示主角和亲人之间存在未说出口的话", "400-500字"),
            ("关键事件", "一个突发事件打破日常——事故/疾病/发现真相", "500-600字"),
            ("真相揭露", "主角发现亲人一直在默默承受/付出的真相", "400-500字"),
            ("悔恨与和解", "来不及说的话/终于说出口的话", "500-600字"),
            ("余味", "回到开头的物件——物是人非。细节自己会哭", "200-300字"),
        ],
    },
}


def check_premise(premise):

    warnings = []
    if not premise or premise == "待填充" or len(premise) < 6:
        warnings.append("⚠️ 设定太短（<6字）。试试描述「谁 + 发现/遭遇了什么反常事件」")
    if premise.count("的") > 5:
        warnings.append("💡 设定偏抽象。改成「[人物] + [具体反常事件]」更易展开")
    cliches = ["重生复仇", "霸道总裁爱上我", "系统激活", "穿越到古代", "被闺蜜抢走"]
    for c in cliches:
        if c in premise:
            warnings.append(f"💡 「{c}」是高频设定——加一个独特转折让它脱颖而出")
            break
    if len(premise) > 60:
        warnings.append("💡 设定偏长。尝试精简到一句话（30字以内最利于展开）")
    return warnings


def generate_outline(genre_key, premise, platform="auto"):
    
    genre = GENRES.get(genre_key)
    if not genre:
        resolved = TYPE_ALIASES.get(genre_key)
        if resolved:
            genre = GENRES.get(resolved)
            if genre:
                print(f"💡 「{genre_key}」→ 已匹配类型「{genre['name']}」\n")
        else:
            print(f"❌ 未识别类型: 「{genre_key}」\n")
            print("📚 支持的类型（输入任一即可）:")
            for k, v in GENRES.items():
                a = "、".join(v.get("aliases", []))
                print(f"  · {v['name']} — 输入: {k} 或 {a}")
            print(f"\n💡 提示: --list-types 查看完整列表，或用中文名如「悬疑」「甜宠」")
            sys.exit(1)

    
    pwarnings = check_premise(premise)

    lines = []
    lines.append(f"# {genre['name']} · 故事大纲")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 设定: {premise}")
    lines.append(f"> 目标平台: {platform} | 推荐平台: {genre['platform']}")
    lines.append(f"> 叙事人称: {genre['narrator']}")
    lines.append("")

    
    lines.append("## 情节骨架")
    lines.append("")
    for i, (title, desc, length) in enumerate(genre["structure"], 1):
        lines.append(f"### 第{i}幕：{title}（{length}）")
        lines.append(f"> {desc}")
        lines.append("")
        lines.append(f"【场景提示】")
        lines.append(f"【需要铺垫的伏笔】")
        lines.append(f"【本幕结尾钩子】")
        lines.append("")

    
    if "hooks" in genre:
        lines.append("## 开头钩子建议（选一个最契合的）")
        for i, h in enumerate(genre["hooks"], 1):
            lines.append(f"{i}. {h}")
        lines.append("")

    
    if "endings" in genre:
        lines.append("## 结尾方式（选一个）")
        for i, e in enumerate(genre["endings"], 1):
            lines.append(f"{i}. {e}")
        lines.append("")

    
    if pwarnings:
        lines.append("## ⚠️ 设定检查")
        lines.append("")
        for w in pwarnings:
            lines.append(f"- {w}")
        lines.append("")

    
    lines.append("## 平台适配提示")
    if genre["platform"] == "zhihu" or platform == "zhihu":
        lines.append("- 知乎体：每段2-3句，大量留白，对话简短")
        lines.append("- 第一人称「我」，语气像在跟朋友讲一个刚发生的事")
        lines.append("- 结尾必须有余味——不是总结，是让你想了又想的那句话")
    if genre["platform"] == "fanqie" or platform == "fanqie":
        lines.append("- 番茄体：对话驱动，60%以上是对话")
        lines.append("- 每2000字内至少一个爽点或甜点")
        lines.append("- 章节结尾留钩子——读者不翻下一页睡不着")
    lines.append("")

    
    lines.append("## 写作提醒")
    lines.append("- 第一句话就进入故事——不要铺垫")
    lines.append("- 短段。多断句。手机屏3-4行即换段")
    lines.append(f"- 目标字数：{'3000-8000' if genre['platform'] == 'zhihu' else '2000-5000'} 字")
    lines.append("- 写完第一遍后放一小时再读——改掉所有读起来像AI写的句子")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="短篇小说大纲生成器")
    parser.add_argument("--type", "-t", default=None, help="故事类型（支持中英文：悬疑/甜宠/复仇/重生/系统/催泪 或 suspense/sweet/revenge等）")
    parser.add_argument("--premise", "-p", default="待填充", help="故事核心设定（一句话）")
    parser.add_argument("--platform", choices=["zhihu", "fanqie", "both", "auto"], default="auto", help="目标平台")
    parser.add_argument("--list-types", action="store_true", help="列出所有支持的类型")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()

    if args.list_types:
        print("📚 支持的故事类型:\n")
        for k, v in GENRES.items():
            aliases_str = "、".join(v.get("aliases", []))
            print(f"  {v['name']}（{k}）")
            print(f"    平台: {v['platform']:6s} | 叙事: {v['narrator']}")
            print(f"    可用名称: {aliases_str}")
            print()
        return

    if not args.type:
        print("❌ 请指定故事类型。\n")
        print("📚 支持的类型:")
        for k, v in GENRES.items():
            a = "、".join(v.get("aliases", []))
            print(f"  · {v['name']} — 输入: {k} 或 {a}")
        print(f"\n示例: python story_outline.py -t 悬疑 -p '独居女孩收到神秘纸条'")
        sys.exit(1)

    genre_key = TYPE_ALIASES.get(args.type, args.type)
    outline = generate_outline(genre_key, args.premise, args.platform)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(outline)
        print(f"✅ 大纲已生成: {args.output}")
    else:
        print(outline)


if __name__ == "__main__":
    main()
