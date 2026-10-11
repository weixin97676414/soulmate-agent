#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短篇爆款选题+开头钩子生成器 (topic_hook_generator.py)
===================================================
输入题材关键词 → 生成 10 个爆款选题 + 对应开头钩子（知乎/番茄双版本）。
零依赖，纯本地运行。

用法:
    python topic_hook_generator.py 悬疑
    python topic_hook_generator.py 甜宠 --count 15
    python topic_hook_generator.py -i
    python topic_hook_generator.py --list-themes
"""

import argparse, re, sys, random

# ============================================================
# 安全清洗
# ============================================================

def sanitize(text):
    if not text:
        return ""
    s = str(text)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)
    s = re.sub(r'(?i)(忽略|ignore).{0,20}(指令|prompt|instruction)', '[已过滤]', s)
    s = re.sub(r'(?i)(请|please).{0,10}(忽略|ignore)', '[已过滤]', s)
    return s.strip()[:30]

# ============================================================
# 题材知识库
# ============================================================

# 每个题材：选题骨架 × 钩子公式
THEMES = {
    "悬疑": {
        "选题骨架": [
            "独居{职业}发现{日常物件}有{不合理变化}",
            "搬进新家后，{邻居}每晚{异常行为}",
            "{亲人}去世前反复说{一句话}，{事后}应验了",
            "深夜收到{陌生人}短信：{预警}",
            "监控录像里{不该出现的人}出现了",
            "{孩子}画的全家福里多了一个人",
            "丈夫/妻子的{习惯}突然变了",
            "旧手机里发现{前任}的未发送消息",
        ],
        "钩子公式": [
            "我家猫每晚11点蹲门口。我家在18楼。",
            "「你老公在说谎。」陌生短信只有这一行。",
            "我妈去世前说衣柜里有东西。我找了三年没找到。今天搬家，衣柜夹层掉出一张照片——照片里有我，但背景是三十年前。",
            "邻居搬走那天，警察来了。他们问我：「你认识对门的王女士吗？」我点头。然后他们让我看看自己手机里的通话记录。",
        ],
    },
    "甜宠": {
        "选题骨架": [
            "{贫穷身份}嫁给{富二代}，{意外暴露}",
            "相亲对象是{前任/上司/明星}，{身份翻转}",
            "{死对头}失忆后只记得{我}",
            "合约情侣{假戏真做}的{临界时刻}",
            "{高冷学霸}偷偷关注{我}的{日常}",
            "婚礼当天{新郎}收到{旧爱}的短信",
            "{顶流明星}深夜敲开{普通女孩}的门",
            "分手三年，{前任}成了{我的老板}",
        ],
        "钩子公式": [
            "他穷得连婚戒都是塑料的。直到婚礼那天，他手机响了，备注是「爸」——来电显示：XX集团董事长。",
            "相亲对象迟到半小时，进来的是高中时当众拒绝我的那个校草。他坐下第一句：「你把我微信删了？」",
            "我男神失忆了。医生问他记得谁，他指着我：「她，欠我520块钱。」",
        ],
    },
    "复仇": {
        "选题骨架": [
            "被{最信任的人}背叛后，{重回巅峰}",
            "婚礼上{闺蜜/兄弟}抢走{一切}，{反击}",
            "{公司}裁员只裁掉{功臣}，{多年后}",
            "被诬陷{罪名}，{十年后}真相大白",
            "{后妈/继姐}的{算计}被当场揭穿",
            "被{亲生父母}抛弃，{功成名就}后他们找来了",
            "{小透明}被{霸凌}，{老师/同学}的沉默",
            "{白月光}回国，{现任}是我复仇计划的一部分",
        ],
        "钩子公式": [
            "婚礼上，闺蜜穿着我的婚纱。全场安静，我爸说：「这门亲事，我替妍妍答应。」",
            "我被公司「优化」那天，是十年庆功宴。今天他们求我回去——因为当年抢我项目的总监，把公司做垮了。",
            "他们骂我是白眼狼。可他们忘了吗？把我赶出家门那天下着大雪，我只有十三岁。",
        ],
    },
    "重生": {
        "选题骨架": [
            "惨死后重生到{关键节点}，{改变命运}",
            "重生回到{高考/婚礼/入职}当天，{预知未来}",
            "前世{错付}的人，这一世{看清}",
            "重生后{不再讨好}任何人",
            "{恶毒配角}重生成{女配}，{不按剧本}",
            "重生到{被全网网暴}那天，{反杀}",
            "{家族破产}前夜重生，{保住一切}",
            "重生后发现{仇人}也重生了",
        ],
        "钩子公式": [
            "再睁眼，我回到了2018年。这一次，我不会救他。",
            "我从十八楼跳下去的那一刻，听见了闺蜜的笑声。再醒来，我躺在高三的教室里，同桌是那个害死我的人。",
            "重生第一天，我把「未婚夫」送我的定情信物扔进了垃圾桶。他追了我两世，这一世换我放过自己。",
        ],
    },
    "催泪": {
        "选题骨架": [
            "{平凡职业}的{父母/亲人}，{一个细节}",
            "{老人}的{固执}背后是{深情}",
            "{留守儿童}和{外出务工}父母的{通话}",
            "{宠物}的{最后一天}",
            "{失忆}亲人{记错}的事",
            "{单亲}父母{说不出口}的爱",
            "{老房子}拆迁前的{最后一次}",
            "{临终}前的{愿望清单}",
        ],
        "钩子公式": [
            "我妈是个清洁工。我考上大学那天，她请了全组同事吃饭，说是「庆祝我家大学生」。结账时我才知道，那顿饭花了她半个月工资。",
            "爷爷老年痴呆了，谁都不认识。可他每天下午四点准时出门，走到巷口站一会儿。我爸说，奶奶生前每天四点在那等他下班。",
            "我爸的手机里存着我的号码，备注是「老板」。他说这样骗子就不会打给他了。",
        ],
    },
}

# 通用钩子升级词（让钩子更抓人）
HOOK_BOOSTERS = ["凌晨三点", "监控里", "第108天", "最后一通电话", "没人知道", "从那天起"]

def generate_topics(theme, count=10):
    """生成选题 + 钩子"""
    if theme not in THEMES:
        return None
    data = THEMES[theme]
    topics = []
    skeletons = data["选题骨架"]
    hooks = data["钩子公式"]

    # 生成选题
    for i in range(count):
        skeleton = skeletons[i % len(skeletons)]
        booster = random.choice(HOOK_BOOSTERS)
        hook = hooks[i % len(hooks)] if i < len(hooks) else hooks[random.randint(0, len(hooks) - 1)]
        topics.append((skeleton, hook, booster))
    return topics

def render(theme, topics):
    lines = []
    lines.append("=" * 56)
    lines.append(f"  「{theme}」题材 · {len(topics)} 个爆款选题 + 开头钩子")
    lines.append("=" * 56)
    for i, (skeleton, hook, booster) in enumerate(topics, 1):
        lines.append(f"\n  【选题 {i}】{skeleton}")
        lines.append(f"     开头钩子：{hook}")
    lines.append("\n" + "=" * 56)
    lines.append("  💡 使用技巧：")
    lines.append("  1. 选题骨架里的 {变量} 替换成具体人设/物件/场景")
    lines.append("  2. 钩子可直接用，也可以和选题自由组合")
    lines.append("  3. 知乎选「第一人称+真实口吻」，番茄选「对话驱动+爽感」")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="短篇爆款选题+开头钩子生成器")
    parser.add_argument("theme", nargs="?", help="题材（悬疑/甜宠/复仇/重生/催泪）")
    parser.add_argument("--count", type=int, default=10, help="生成数量（默认10）")
    parser.add_argument("--list-themes", action="store_true", help="列出可用题材")
    parser.add_argument("-i", "--interactive", action="store_true")
    args = parser.parse_args()

    if args.list_themes:
        print("可用题材:")
        for k in THEMES:
            print(f"  {k}: {len(THEMES[k]['选题骨架'])} 个选题骨架 + {len(THEMES[k]['钩子公式'])} 个钩子")
        return

    theme = sanitize(args.theme or "")
    if args.interactive:
        theme = sanitize(input("题材（悬疑/甜宠/复仇/重生/催泪）: ") or "悬疑")

    if not theme:
        print("用法: python topic_hook_generator.py 悬疑 [--count 15]")
        print("      python topic_hook_generator.py --list-themes")
        sys.exit(0)

    topics = generate_topics(theme, args.count)
    if topics is None:
        print(f"❌ 未知题材: {theme}")
        print(f"   可用: {', '.join(THEMES.keys())}")
        sys.exit(1)
    print(render(theme, topics))

if __name__ == "__main__":
    main()
