#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""video_audit.py — AI电影级短视频总导演 · 确定性裁决工具

把 SKILL.md 里可判定的规则固化成命令，避免同一句需求每次裁决出不同模板。

子命令：
  template <文本>   模板适配裁决（品类词 > 形式词 > 渠道词 > 兜底）
  spec <渠道>       技术参数裁决（宽高比 / 帧率 / 时长上限）
  checklist         打印交付前 10 项质量门
  demo              跑一个完整实战案例
  selftest          跑内置断言

退出码：0=成功  2=输入/用法错误  3=内部错误
零第三方依赖，仅用 Python 标准库。
"""

import argparse
import io
import json
import os
import sys

# ---- Windows 控制台 GBK 兜底：任何环境下都不因编码炸掉 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ============================================================
# 规则表（全部取自 references/templates.md 的「适用场景」与 SKILL.md §Step 2）
# ============================================================

# 第一层：品类词 —— 决定画面主体与材质美学，优先级最高
CATEGORY_WORDS = {
    "D": ["科技出海", "企业品宣", "跨境展会", "B2B", "工业", "制造", "机械",
          "新能源", "芯片"],
    "A": ["中药美妆", "东方文化", "高净值", "奢侈品", "高奢", "珠宝", "瓷器",
          "丝绸", "茶"],
    "B": ["美妆", "食品", "家居", "母婴"],
}

# 第二层：形式词 —— 决定叙事方式与情绪弧线
FORM_WORDS = {
    "C": ["微短剧", "剧情号", "剧情", "带货", "情感", "快手"],
    "A": ["出海TVC", "高净值"],
    "B": ["种草", "生活方式", "生活", "温暖", "美妆日常"],
}

# 第三层：渠道词 —— 只决定投放端，不决定美学模板
CHANNEL_WORDS = ["视频号", "小红书", "TikTok", "tiktok", "抖音", "B站", "b站",
                 "YouTube", "youtube", "LinkedIn", "linkedin", "官网"]

# 兜底：品类与形式都未命中时
FALLBACK_LUX = ["奢侈", "高端", "珠宝", "瓷器", "丝绸"]
FALLBACK_CONSUMER = ["美妆", "食品", "家居", "母婴", "日用", "消费"]

TEMPLATE_NAME = {
    "A": "东方美学·高奢品牌出海",
    "B": "小红书/TikTok 视觉种草",
    "C": "短视频情感/剧情带货",
    "D": "跨境/B2B 工业科技出海",
}

# 渠道 → 宽高比（SKILL.md §风险与边界 3 给了 TikTok/抖音=9:16、B站/官网=16:9；
# 其余按平台实际主形态补齐，与 tags 承诺的「适配抖音、小红书、TikTok、视频号」一致）
RATIO_PORTRAIT = ["抖音", "TikTok", "tiktok", "小红书", "视频号", "快手"]
RATIO_LANDSCAPE = ["B站", "b站", "官网", "YouTube", "youtube", "LinkedIn", "linkedin"]

MAX_SEC = 60  # SKILL.md §风险与边界 3：单条短视频建议 ≤60s


# ============================================================
# 裁决逻辑
# ============================================================

def _longest_hit(text, words):
    """返回 (最长命中词, 长度)；无命中返回 (None, 0)。"""
    best, best_len = None, 0
    for w in words:
        if w in text and len(w) > best_len:
            best, best_len = w, len(w)
    return best, best_len


def decide_template(text):
    """模板裁决：品类词 > 形式词 > 渠道词 > 兜底。

    返回 dict：template / name / reason / hit / fallback
    """
    if text is None or not str(text).strip():
        raise ValueError("需求文本为空，无法裁决模板")

    text = str(text)
    lowered = text + " " + text.lower()  # 兼容 TikTok / B站 等大小写变体

    # 第一层：品类词（最长命中优先；并列时按 D > A > B，工业与出海企业形态最明确）
    hits = []
    for tpl in ("D", "A", "B"):
        w, ln = _longest_hit(lowered, CATEGORY_WORDS[tpl])
        if w:
            hits.append((ln, tpl, w))
    if hits:
        hits.sort(key=lambda x: (-x[0], {"D": 0, "A": 1, "B": 2}[x[1]]))
        ln, tpl, w = hits[0]
        return {
            "template": "Template " + tpl,
            "code": tpl,
            "name": TEMPLATE_NAME[tpl],
            "hit": w,
            "layer": "品类词",
            "reason": "命中品类词「%s」（%d 字），品类决定画面主体与材质美学，优先级高于投放形式" % (w, ln),
            "fallback": False,
        }

    # 第二层：形式词
    hits = []
    for tpl in ("C", "A", "B"):
        w, ln = _longest_hit(lowered, FORM_WORDS[tpl])
        if w:
            hits.append((ln, tpl, w))
    if hits:
        hits.sort(key=lambda x: (-x[0], {"C": 0, "A": 1, "B": 2}[x[1]]))
        ln, tpl, w = hits[0]
        return {
            "template": "Template " + tpl,
            "code": tpl,
            "name": TEMPLATE_NAME[tpl],
            "hit": w,
            "layer": "形式词",
            "reason": "无品类词，命中形式词「%s」（%d 字），按叙事方式裁决" % (w, ln),
            "fallback": False,
        }

    # 第三层：只有渠道词
    ch = [c for c in CHANNEL_WORDS if c in lowered]
    if ch:
        return {
            "template": "Template B",
            "code": "B",
            "name": TEMPLATE_NAME["B"],
            "hit": "/".join(sorted(set(ch))),
            "layer": "渠道词",
            "reason": "仅命中渠道词（%s），无品类与形式信息，按消费品种草基线裁决，须在输出标注 [模板兜底]" % "/".join(sorted(set(ch))),
            "fallback": True,
        }

    # 第四层：完全无法判断 —— 按品类兜底
    if any(w in lowered for w in FALLBACK_LUX):
        tpl = "A"
        reason = "完全无特征词，命中奢侈/高端线索，兜底 Template A（高奢出海基线）"
    elif any(w in lowered for w in FALLBACK_CONSUMER):
        tpl = "B"
        reason = "完全无特征词，命中消费品线索，兜底 Template B（默认最高转化率）"
    else:
        tpl = "A"
        reason = "完全无特征词且无品类线索，兜底 Template A（高奢出海基线），须在输出标注 [模板兜底：默认A]"
    return {
        "template": "Template " + tpl,
        "code": tpl,
        "name": TEMPLATE_NAME[tpl],
        "hit": None,
        "layer": "兜底",
        "reason": reason,
        "fallback": True,
    }


def decide_spec(channel, sec=None):
    """技术参数裁决：宽高比 / 帧率 / 时长上限。"""
    if channel is None or not str(channel).strip():
        raise ValueError("渠道为空，无法裁决技术参数")

    ch = str(channel)
    lowered = ch + " " + ch.lower()

    portrait = [c for c in RATIO_PORTRAIT if c in lowered]
    landscape = [c for c in RATIO_LANDSCAPE if c in lowered]

    if portrait and landscape:
        ratio = "9:16"
        note = "同时命中竖屏（%s）与横屏（%s）渠道，按竖屏优先（短视频投放主形态）" % (
            "/".join(sorted(set(portrait))), "/".join(sorted(set(landscape))))
    elif portrait:
        ratio = "9:16"
        note = "命中竖屏渠道 %s" % "/".join(sorted(set(portrait)))
    elif landscape:
        ratio = "16:9"
        note = "命中横屏渠道 %s" % "/".join(sorted(set(landscape)))
    else:
        raise ValueError(
            "未识别渠道「%s」。已支持：竖屏(%s) / 横屏(%s)；"
            "1:1 仅在用户显式指定时使用" % (
                ch, "/".join(RATIO_PORTRAIT[:5]), "/".join(RATIO_LANDSCAPE[:4])))

    result = {
        "channel": ch,
        "ratio": ratio,
        "fps": "24fps" if ratio == "16:9" else "30fps",
        "max_sec": MAX_SEC,
        "note": note,
    }

    if sec is not None:
        try:
            s = int(sec)
        except (TypeError, ValueError):
            raise ValueError("时长必须是整数秒，收到「%s」" % sec)
        if s <= 0:
            raise ValueError("时长必须为正整数，收到 %d" % s)
        result["sec"] = s
        if s > MAX_SEC:
            result["over_limit"] = True
            result["split_into"] = (s + MAX_SEC - 1) // MAX_SEC
            result["advice"] = "超出单条 ≤%ds 上限，须拆分为 %d 条独立输出，每条独立走 Event 1-4 轴" % (
                MAX_SEC, result["split_into"])
        else:
            result["over_limit"] = False
            result["advice"] = "在 ≤%ds 上限内，可单条输出" % MAX_SEC
    return result


CHECKLIST = [
    (1, "触发正确", "属本 skill 范围，未误触非触发边界；命中 §Step 0 六条边界之一须转交"),
    (2, "输入解析完整", "三字段均处理；缺项已按 L1–L4 补全并标 [补全推断]"),
    (3, "模板正确激活", "由 video_audit.py template 裁决且与品类一致；兜底须标 [模板兜底]"),
    (4, "事件驱动语法", "无「第X秒」时间切片，使用 Event 1–4 轴"),
    (5, "双语提示词", "中文版（可灵/即梦/海螺）+ 英文版（Sora/Runway）均给出"),
    (6, "技术参数合理", "时长/比例/帧率/运动强度均填；由 video_audit.py spec 校验"),
    (7, "商业留白", "构图为 Logo/字幕留白说明"),
    (8, "绝对写实", "皮肤微观纹理等写实约束已注入"),
    (9, "反虚构", "无杜撰真实品牌/认证/数据；补全项标 [补全推断]"),
    (10, "零废话", "结构外无过渡语，直奔主题"),
]


def run_template(args):
    r = decide_template(args.text)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("需求：%s" % args.text)
        print("裁决：%s — %s" % (r["template"], r["name"]))
        print("依据：%s（%s）" % (r["reason"], r["layer"]))
        if r["fallback"]:
            print("提示：属兜底裁决，输出时须标注 [模板兜底]")
    return 0


def run_spec(args):
    r = decide_spec(args.channel, args.sec)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("渠道：%s" % r["channel"])
        print("宽高比：%s   帧率：%s   单条上限：≤%ds" % (r["ratio"], r["fps"], r["max_sec"]))
        print("依据：%s" % r["note"])
        if "sec" in r:
            print("时长：%ds → %s" % (r["sec"], r["advice"]))
    return 0


def run_checklist(args):
    print("交付前质量门（10 项 · 全过=完稿）")
    print("-" * 60)
    for n, name, std in CHECKLIST:
        print("%2d  %-8s %s" % (n, name, std))
    print("-" * 60)
    print("任一未达标 → 回补对应模块后重新输出（见 SKILL.md §异常与兜底）")
    return 0


DEMO_TEXT = "工业传感器，投放 LinkedIn，做企业出海形象片"


def run_demo(args):
    print("=" * 60)
    print("实战案例：%s" % DEMO_TEXT)
    print("=" * 60)
    r = decide_template(DEMO_TEXT)
    print("\n[Step 2 模板裁决]")
    print("  %s — %s" % (r["template"], r["name"]))
    print("  依据：%s" % r["reason"])

    s = decide_spec("LinkedIn", 75)
    print("\n[Step 4 技术参数]")
    print("  宽高比 %s / 帧率 %s / 单条上限 ≤%ds" % (s["ratio"], s["fps"], s["max_sec"]))
    print("  时长 75s → %s" % s["advice"])

    print("\n[质量门] 共 %d 项，逐条核对后交付（video_audit.py checklist）" % len(CHECKLIST))
    return 0


def run_selftest(args):
    cases = []

    def chk(name, got, want):
        cases.append((name, got == want, "got=%r want=%r" % (got, want)))

    # —— 冲突案例锁死：子串抢占（工业 + 出海，必须判 D 而非 A）——
    chk("工业设备出海 → D", decide_template("工业设备出海")["code"], "D")
    chk("机械零件出海TVC → D", decide_template("机械零件出海TVC")["code"], "D")
    chk("新能源企业品宣 → D", decide_template("新能源企业品宣")["code"], "D")
    chk("B2B芯片科技出海 → D", decide_template("B2B芯片科技出海")["code"], "D")
    # —— 泛化出海词在无工业线索时仍归 A ——
    chk("高奢手表出海TVC → A", decide_template("高奢手表出海TVC")["code"], "A")
    chk("东方茶器出海 → A", decide_template("东方茶器出海")["code"], "A")
    chk("珠宝品牌高净值 → A", decide_template("珠宝品牌高净值")["code"], "A")
    # —— 形式词层 ——
    chk("抖音剧情带货 → C", decide_template("抖音剧情带货")["code"], "C")
    chk("小红书种草 → B", decide_template("小红书种草")["code"], "B")
    chk("母婴食品种草 → B", decide_template("母婴食品种草")["code"], "B")
    # —— 兜底层 ——
    chk("只说TikTok → B 且兜底", decide_template("TikTok")["code"], "B")
    chk("只说TikTok 标兜底", decide_template("TikTok")["fallback"], True)
    chk("空泛需求 → A 且兜底", decide_template("做个视频")["code"], "A")
    # —— spec ——
    chk("抖音 → 9:16", decide_spec("抖音")["ratio"], "9:16")
    chk("小红书 → 9:16", decide_spec("小红书")["ratio"], "9:16")
    chk("LinkedIn → 16:9", decide_spec("LinkedIn")["ratio"], "16:9")
    chk("B站 → 16:9", decide_spec("B站")["ratio"], "16:9")
    chk("75s 超限需拆 2 条", decide_spec("抖音", 75)["split_into"], 2)
    chk("60s 不超限", decide_spec("抖音", 60)["over_limit"], False)
    chk("61s 超限", decide_spec("抖音", 61)["over_limit"], True)
    # —— 输入错误必须抛 ValueError（不是 sys.exit，保证调用方可捕获）——
    for bad in (lambda: decide_template(""), lambda: decide_template("   "),
                lambda: decide_spec(""), lambda: decide_spec("抖音", 0),
                lambda: decide_spec("抖音", -5), lambda: decide_spec("抖音", "abc"),
                lambda: decide_spec("不存在的渠道")):
        try:
            bad()
            cases.append(("输入错误应抛 ValueError", False, "未抛异常"))
        except ValueError:
            cases.append(("输入错误抛 ValueError", True, "ok"))
        except Exception as e:
            cases.append(("输入错误应抛 ValueError", False, "抛了 %s" % type(e).__name__))

    ok = sum(1 for _, p, _ in cases if p)
    for name, p, detail in cases:
        print("  %s %s%s" % ("PASS" if p else "FAIL", name, "" if p else "  << " + detail))
    print("-" * 60)
    print("selftest: %d/%d 通过" % (ok, len(cases)))
    return 0 if ok == len(cases) else 2


def build_parser():
    p = argparse.ArgumentParser(
        prog="video_audit.py",
        description="AI电影级短视频总导演 · 确定性裁决工具（零依赖）")
    sub = p.add_subparsers(dest="cmd")

    t = sub.add_parser("template", help="模板适配裁决")
    t.add_argument("text", help="需求文本")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=run_template)

    s = sub.add_parser("spec", help="技术参数裁决")
    s.add_argument("channel", help="投放渠道，如 抖音/TikTok/小红书/视频号/B站/官网/YouTube/LinkedIn")
    s.add_argument("--sec", type=int, default=None, help="计划时长（秒）")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=run_spec)

    c = sub.add_parser("checklist", help="打印交付前 10 项质量门")
    c.set_defaults(func=run_checklist)

    d = sub.add_parser("demo", help="完整实战案例")
    d.set_defaults(func=run_demo)

    st = sub.add_parser("selftest", help="跑内置断言")
    st.set_defaults(func=run_selftest)
    return p


def _main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.print_help()
        return 2
    return args.func(args)


def main(argv=None):
    try:
        return _main(argv)
    except SystemExit as e:
        # argparse 遇到未知子命令/参数会 sys.exit(2)，SystemExit 是 BaseException，
        # 不被 except Exception 捕获，会直接终止进程。这里转成返回值，保证退出码封闭。
        code = e.code
        if code is None or code == 0:
            return 0
        try:
            return int(code)
        except (TypeError, ValueError):
            return 2
    except ValueError as e:
        sys.stderr.write("[错误] %s\n" % e)
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("[中断] 用户取消\n")
        return 2
    except Exception as e:
        sys.stderr.write("[内部错误] %s: %s\n" % (type(e).__name__, e))
        return 3


if __name__ == "__main__":
    sys.exit(main())
