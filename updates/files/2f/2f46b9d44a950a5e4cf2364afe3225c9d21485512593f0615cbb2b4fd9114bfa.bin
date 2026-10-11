# -*- coding: utf-8 -*-
"""数据与内容分析引擎：把 dataset.json 变成可判断结论。

输出：
  <out>/analysis.json      结构化分析结论（报告渲染 / 二次加工的数据源）
  <out>/notes_metrics.csv  逐条笔记指标表（Excel 可直接打开）

设计原则：**只算事实，不做空话**。每个结论都带可追溯的数值证据，
报告阶段的判断必须引用这里的字段，不允许凭印象下结论。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from xhs_common import fmt_num, human_num, log, read_json, write_json

# --------------------------------------------------------------------------- #
# 词典
# --------------------------------------------------------------------------- #
#: 词典必须跨赛道覆盖。早期版本只写了美妆/穿搭词，
#: 遇到家居、装修、房产、宠物等赛道会全军覆没（命中率 0%），进而把好账号判成没结构。
AUDIENCE = [
    # 通用人群
    "打工人", "上班族", "学生党", "宝妈", "孕妈", "新手", "小白", "男生", "女生", "姐妹",
    "家人们", "闺蜜", "情侣", "铲屎官", "新手爸妈", "银发", "懒人", "手残党", "普通人",
    # 美妆穿搭
    "油皮", "干皮", "混油", "敏感肌", "痘肌", "方圆脸", "微胖", "小个子", "高个子",
    "梨形", "苹果型", "黄皮",
    # 家居/房产/生活方式
    "独居", "一个人住", "租客", "租房党", "房东", "刚需", "沪漂", "北漂", "深漂",
    "小户型", "大户型", "有房", "无房", "首套", "二房东", "合租", "搬家人", "装修人",
]

PAIN = [
    # 通用
    "踩坑", "翻车", "焦虑", "崩溃", "后悔", "太难", "没时间", "太贵", "智商税", "割韭菜",
    "避坑", "无效", "失败", "差评", "鸡肋", "劝退", "难用", "踩雷", "乱花", "白买",
    "将就", "凑合", "委屈", "不甘", "崩了", "坚持不住", "撑不住",
    # 美妆
    "失眠", "脱发", "黑头", "毛孔", "卡粉", "脱妆", "显胖", "显矮", "显黑",
    # 家居/房产
    "老破小", "太小", "拥挤", "脏乱", "采光差", "漏水", "隔音差", "买不起", "房贷",
    "首付", "装修坑", "甲醛", "收纳难", "乱糟糟", "破旧", "昏暗", "阴暗", "潮湿",
]

FORMAT = ["清单", "合集", "盘点", "测评", "实测", "教程", "攻略", "对比", "拆解", "干货", "模板",
          "保姆级", "一条龙", "三步", "五招", "七个", "指南", "手把手", "速成", "入门", "进阶",
          "复盘", "总结", "VS", "开箱", "vlog", "记录", "日记",
          # 家居/装修
          "改造", "装修", "一镜到底", "收纳", "布置", "前后对比", "爆改", "翻新", "好物",
          "roomtour", "RoomTour", "入住", "搬家", "软装", "硬装", "设计", "平价改造"]

CTA = ["评论区", "扣1", "扣 1", "私信", "关注", "收藏", "点赞", "主页", "链接", "店铺", "橱窗",
       "小清单", "蹲", "免费领", "送", "留言", "告诉我", "下期", "持续更新", "关注我",
       "一起", "留言区", "评论区见", "主页还有", "后续", "催更"]

MONETIZE = {
    "电商带货": ["店铺", "橱窗", "小清单", "下单", "已购", "购物车", "优惠券", "团购", "链接在",
                 "同款", "货号", "限时", "补货", "开团"],
    "品牌广告": ["报备", "赞助", "广告", "合作", "品牌", "星图", "蒲公英", "体验官", "试用",
                 "礼盒", "PR", "寄样", "官方"],
    "私域引流": ["微信", "加V", "vx", "V我", "私信", "进群", "群聊", "领取资料", "暗号", "扣1"],
    "知识付费": ["课程", "训练营", "陪跑", "咨询", "付费", "报名", "社群", "打卡", "直播课",
                 "资料包", "教程包", "带教", "一对一"],
    "服务接单": ["接单", "定制", "约拍", "设计", "代运营", "装修", "代办", "预约", "上门", "报价"],
}

STOPWORDS = set("""的 了 是 我 你 他 她 它 们 在 有 和 就 不 也 都 很 到 说 要 去 会 着 没 没有
看 好 自己 这 那 个 之 与 及 或者 一个 什么 怎么 为什么 可以 这个 那个 真的 太 超 巨 绝 但 而
因为 所以 如果 还是 已经 一些 这些 那些 大家 我们 你们 他们 后 前 里 中 上 下 时 年 月 日 号
把 被 给 让 从 对 向 第 只 又 更 最 吧 呢 啊 呀 哦 嗯 哈 然后 就是 不是 一定 真的 感觉 觉得
今日 今天 分享 打卡 日常 记录""".split())

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2190-\u21FF\u2B00-\u2BFF]")
NUM_RE = re.compile(r"\d+")
QUESTION_RE = re.compile(r"[?？]|吗|呢|如何|怎样|怎么|为什么|是不是|有没有")
COMMAND_RE = re.compile(r"^(快|赶紧|一定|必须|别|不要|建议|记得|试试|收藏|抄作业|码住|直接)")
EXCLAIM_RE = re.compile(r"[!！]")


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return float(ordered[idx])


def _safe_div(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


EDGE_CHARS = set("的了我是你他她它们这那个之与就在有和不也很都到说要去会着把被给让从对第只又更最"
                 "吧呢啊呀哦嗯哈上下里中后前时们再来出行做得看过叫让")


def top_keywords(texts: list[str], n: int = 25, min_count: int = 3) -> list[dict]:
    """无依赖中文关键词抽取：n-gram 频次 → 边界虚词过滤 → 长短词择优合并。

    关键处理：频次接近时保留更长的词（"别再踩坑" 优于 "别再"），
    避免出现「我把 / 照着做就」这类无意义的切片段。
    """
    counter: Counter = Counter()
    for text in texts:
        clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text or "")
        for seg in clean.split():
            if re.match(r"^[\u4e00-\u9fff]+$", seg):
                for size in (2, 3, 4):
                    for i in range(len(seg) - size + 1):
                        gram = seg[i:i + size]
                        if gram in STOPWORDS:
                            continue
                        if gram[0] in EDGE_CHARS or gram[-1] in EDGE_CHARS:
                            continue
                        counter[gram] += 1
            elif len(seg) >= 2 and not seg.isdigit() and not re.fullmatch(r"([a-zA-Z])\1+", seg):
                counter[seg.lower()] += 1

    # 长度加权排序：4 字词优先于同频的 2 字词
    ranked = sorted(counter.items(),
                    key=lambda kv: (kv[1] * (1 + 0.3 * (len(kv[0]) - 2)), len(kv[0])),
                    reverse=True)
    picked: list[dict] = []
    for word, count in ranked:
        if count < min_count:
            continue
        handled = False
        for i, prev in enumerate(picked):
            if prev["word"] in word and count >= 0.7 * prev["count"]:
                picked[i] = {"word": word, "count": count}   # 用更长的词替换短词
                handled = True
                break
            if word in prev["word"]:
                handled = True                                # 已被更长的词覆盖
                break
        if not handled:
            picked.append({"word": word, "count": count})
    picked.sort(key=lambda d: -d["count"])
    return picked[:n]


def match_lexicon(text: str, lexicon: list[str]) -> list[str]:
    """词典匹配。忽略空格差异，避免「扣 1」匹配不到「扣1」这类漏判。"""
    flat = re.sub(r"\s+", "", text or "")
    return sorted({w for w in lexicon if w and re.sub(r"\s+", "", w) in flat})


# --------------------------------------------------------------------------- #
# 分析模块
# --------------------------------------------------------------------------- #
def enrich_notes(notes: list[dict]) -> list[dict]:
    for note in notes:
        title = note.get("title") or ""
        desc = note.get("desc") or ""
        full = f"{title} {desc}"
        liked = human_num(note.get("liked"))
        collected = human_num(note.get("collected"))
        commented = human_num(note.get("commented"))
        shared = human_num(note.get("shared"))
        note["liked"] = liked
        note["collected"] = collected
        note["commented"] = commented
        note["shared"] = shared
        note["total_engage"] = liked + collected + commented + shared
        note["collect_like"] = _safe_div(collected, liked)
        note["comment_like"] = _safe_div(commented, liked)
        note["share_like"] = _safe_div(shared, liked)
        note["title_len"] = len(re.sub(r"\s", "", title))
        note["desc_len"] = len(re.sub(r"\s", "", desc))
        note["emoji_count"] = len(EMOJI_RE.findall(full))
        note["has_number"] = bool(NUM_RE.search(title))
        note["is_question"] = bool(QUESTION_RE.search(title))
        note["is_command"] = bool(COMMAND_RE.search(title.strip()))
        note["has_exclaim"] = bool(EXCLAIM_RE.search(title))
        note["audience_words"] = match_lexicon(full, AUDIENCE)
        note["pain_words"] = match_lexicon(full, PAIN)
        note["format_words"] = match_lexicon(full, FORMAT)
        note["cta_words"] = match_lexicon(full, CTA)
        note["duration_sec"] = round((note.get("duration_ms") or 0) / 1000, 1)
        note["image_count"] = len(note.get("images") or [])
    return notes


def engagement_block(notes: list[dict], fans: int) -> dict:
    liked = [n["liked"] for n in notes]
    collected = [n["collected"] for n in notes]
    commented = [n["commented"] for n in notes]
    shared = [n["shared"] for n in notes]
    total = [n["total_engage"] for n in notes]
    med = _median(liked)
    if med <= 0:
        med = max(1, _mean(liked))
    viral = [n for n in notes if n["liked"] >= max(med * 3, 10)]
    dead = [n for n in notes if n["liked"] <= max(med * 0.3, 1)]
    # 免登录通道（SSR 列表）只下发点赞数。收藏/评论全为 0 时不是"账号差"，
    # 而是"没采到"——必须标记出来，否则下游会把缺失当成低分并误报刷量。
    has_collected = any(n["collected"] for n in notes)
    has_commented = any(n["commented"] for n in notes)
    has_shared = any(n["shared"] for n in notes)
    return {
        "sample": len(notes),
        "data_completeness": {
            "liked": any(n["liked"] for n in notes),
            "collected": has_collected,
            "commented": has_commented,
            "shared": has_shared,
            "full": has_collected and has_commented,
            "missing": [k for k, ok in (("收藏", has_collected), ("评论", has_commented),
                                        ("分享", has_shared)) if not ok],
        },
        "liked": {"median": _median(liked), "mean": _mean(liked), "p90": _pct(liked, 0.9), "max": max(liked or [0])},
        "collected": {"median": _median(collected), "mean": _mean(collected),
                      "p90": _pct(collected, 0.9), "max": max(collected or [0])},
        "commented": {"median": _median(commented), "mean": _mean(commented),
                      "p90": _pct(commented, 0.9), "max": max(commented or [0])},
        "shared": {"median": _median(shared), "mean": _mean(shared),
                   "p90": _pct(shared, 0.9), "max": max(shared or [0])},
        "total_median": _median(total),
        "collect_like_ratio": _safe_div(sum(collected), sum(liked)),
        "comment_like_ratio": _safe_div(sum(commented), sum(liked)),
        "share_like_ratio": _safe_div(sum(shared), sum(liked)),
        "engage_per_fan": _safe_div(_median(total), fans),
        "viral_count": len(viral),
        "viral_rate": _safe_div(len(viral), len(notes)),
        "dead_rate": _safe_div(len(dead), len(notes)),
        "top1_share": _safe_div(max(liked or [0]), sum(liked) or 1),
        "concentration": _safe_div(_pct(liked, 0.9), _median(liked) or 1),
    }


def cadence_block(notes: list[dict]) -> dict:
    stamps = sorted([n["timestamp"] for n in notes if n.get("timestamp")])
    if len(stamps) < 2:
        return {"posts": len(notes), "note": "样本不足或缺少时间戳"}
    stamps_sec = [s / 1000 for s in stamps]
    gaps = [round(b - a, 1) for a, b in zip(stamps_sec, stamps_sec[1:])]
    span_days = max((stamps_sec[-1] - stamps_sec[0]) / 86400, 1)
    hours, weekdays = [], []
    for s in stamps_sec:
        tl = time.localtime(s)
        hours.append(tl.tm_hour)
        weekdays.append(tl.tm_wday)
    return {
        "posts": len(notes),
        "span_days": round(span_days, 1),
        "posts_per_week": round(len(notes) / span_days * 7, 2),
        "median_gap_hours": round(_median([g / 3600 for g in gaps]), 1),
        "max_gap_days": round(max(gaps) / 86400, 1),
        "active_hours": Counter([h // 3 * 3 for h in hours]).most_common(4),
        "active_weekdays": Counter(weekdays).most_common(3),
        "first_post": time.strftime("%Y-%m-%d", time.localtime(stamps_sec[0])),
        "last_post": time.strftime("%Y-%m-%d", time.localtime(stamps_sec[-1])),
    }


def content_block(notes: list[dict]) -> dict:
    titles = [n.get("title") or "" for n in notes]
    descs = [n.get("desc") or "" for n in notes]
    tag_counter: Counter = Counter()
    for n in notes:
        for t in n.get("tags") or []:
            tag_counter[t] += 1
    # 小样本（十几条）下 min_count=3 会把关键词过滤到只剩几个，按样本量自适应
    keywords = top_keywords([f"{t} {d}" for t, d in zip(titles, descs)], n=30,
                            min_count=3 if len(notes) >= 20 else 2)
    return {
        "title_len": {"median": _median([n["title_len"] for n in notes]),
                      "mean": _mean([n["title_len"] for n in notes])},
        "desc_len": {"median": _median([n["desc_len"] for n in notes]),
                     "mean": _mean([n["desc_len"] for n in notes])},
        "emoji_per_note": _mean([n["emoji_count"] for n in notes]),
        "number_title_rate": _safe_div(sum(1 for n in notes if n["has_number"]), len(notes)),
        "question_title_rate": _safe_div(sum(1 for n in notes if n["is_question"]), len(notes)),
        "command_title_rate": _safe_div(sum(1 for n in notes if n["is_command"]), len(notes)),
        "exclaim_title_rate": _safe_div(sum(1 for n in notes if n["has_exclaim"]), len(notes)),
        "audience_rate": _safe_div(sum(1 for n in notes if n["audience_words"]), len(notes)),
        "pain_rate": _safe_div(sum(1 for n in notes if n["pain_words"]), len(notes)),
        "format_rate": _safe_div(sum(1 for n in notes if n["format_words"]), len(notes)),
        "cta_rate": _safe_div(sum(1 for n in notes if n["cta_words"]), len(notes)),
        "top_tags": [{"tag": t, "count": c} for t, c in tag_counter.most_common(20)],
        "tag_diversity": _safe_div(len(tag_counter), max(sum(tag_counter.values()), 1)),
        "avg_tags_per_note": _mean([len(n.get("tags") or []) for n in notes]),
        "keywords": keywords,
    }


def format_block(notes: list[dict]) -> dict:
    """图文 / 视频结构占比。

    `format_mix` 是下游报告与叙述**必须引用**的占比口径：
    rate 基于**全量笔记条数**（不是抽样），两种形式相加恒为 100%。
    """
    videos = [n for n in notes if n["type"] == "video"]
    images = [n for n in notes if n["type"] != "video"]
    total = len(notes)
    durations = [n["duration_sec"] for n in videos if n["duration_sec"] > 0]

    def stats(items: list[dict], label: str, key: str) -> dict:
        return {
            "key": key,
            "label": label,
            "count": len(items),
            "rate": _safe_div(len(items), total),
            "liked_median": _median([n["liked"] for n in items]),
            "liked_mean": _mean([n["liked"] for n in items]),
            "collected_median": _median([n["collected"] for n in items]),
            "commented_median": _median([n["commented"] for n in items]),
            "liked_sum": sum(n["liked"] for n in items),
            "top_note": (max(items, key=lambda n: n["liked"])["title"]
                         if items else ""),
        }

    video_stat = stats(videos, "视频", "video")
    image_stat = stats(images, "图文", "image")
    mix = [video_stat, image_stat]

    video_rate, image_rate = video_stat["rate"], image_stat["rate"]
    mix_label = (f"视频 {video_stat['count']} 条（{video_rate:.0%}） · "
                 f"图文 {image_stat['count']} 条（{image_rate:.0%}）")

    return {
        "total_notes": total,
        "video_count": len(videos),
        "image_count": len(images),
        "video_rate": video_rate,
        "image_rate": image_rate,
        "format_mix": mix,
        "mix_label": mix_label,
        "video_liked_median": video_stat["liked_median"],
        "image_liked_median": image_stat["liked_median"],
        "duration_sec": {"median": _median(durations), "mean": _mean(durations),
                         "min": min(durations or [0]), "max": max(durations or [0])},
        "images_per_note": _mean([n["image_count"] for n in images]),
        "winner_format": "video" if (videos and images and
                                     _median([n["liked"] for n in videos]) >
                                     _median([n["liked"] for n in images])) else (
            "image" if (videos and images) else ("video" if videos else "image")),
    }


def tier_block(eng: dict, fans: int, cadence: dict) -> dict:
    """流量层级推演：峰值决定天花板，中位数决定水位，浓度决定依赖度。"""
    peak = eng["liked"]["max"]
    water = eng["liked"]["median"]
    conc = eng["concentration"]
    if peak >= 100_000:
        level, ceiling = "S", "百万级爆发力"
    elif peak >= 30_000:
        level, ceiling = "A", "十万级稳定爆款"
    elif peak >= 8_000:
        level, ceiling = "B", "万级腰部"
    elif peak >= 1_000:
        level, ceiling = "C", "千级起步"
    else:
        level, ceiling = "D", "百级冷启动"
    if water >= max(peak * 0.35, 1):
        shape = "稳态型"
        shape_desc = "中位数贴近峰值，流量不靠单条爆款，属于可预期的稳定产出"
    elif conc >= 6:
        shape = "爆款依赖型"
        shape_desc = "单条爆款贡献绝大部分互动，日常内容水位低，增长高度不确定"
    else:
        shape = "波动爬坡型"
        shape_desc = "偶有跑量内容但尚未形成稳定水位，处于找爆点的阶段"
    return {
        "level": level,
        "ceiling": ceiling,
        "peak_liked": peak,
        "water_level": water,
        "concentration": conc,
        "water_ratio": _safe_div(water, peak),
        "steadiness": min(1.0, 3.0 / max(conc, 1.0)),
        "shape": shape,
        "shape_desc": shape_desc,
        "next_gate": {
            "S": "维持频次 + 做内容资产沉淀（系列化、可搜索）",
            "A": "把单次爆款转为系列，拉高中位数水位",
            "B": "锁定跑量选题做 3 条同结构复刻，验证可复制性",
            "C": "先提频次到 3-4 篇/周，再优化标题命中率",
            "D": "重做定位与选题库，当前样本不足以谈算法",
        }[level],
    }


def health_block(eng: dict, notes: list[dict], fans: int) -> dict:
    """注水/异常检测：小红书常见数据失真信号。

    关键：只对**实际采到**的指标下判断。收藏/评论缺失时不能算比值、更不能报刷量，
    否则会把"数据没采到"误判成"账号有问题"。
    """
    flags = []
    complete = eng.get("data_completeness", {})
    cl = eng["collect_like_ratio"]
    pl = eng["comment_like_ratio"]
    if complete.get("commented"):
        if pl < 0.01 and eng["liked"]["median"] > 200:
            flags.append({"level": "high", "item": "评论赞比 < 1%",
                          "meaning": "评论极少但点赞高，疑似刷赞或内容无讨论钩子"})
    if complete.get("collected"):
        if cl < 0.15 and eng["liked"]["median"] > 200:
            flags.append({"level": "mid", "item": "收藏赞比 < 15%",
                          "meaning": "缺少「值得存下来」的工具属性，内容偏消遣"})
        if cl > 1.2:
            flags.append({"level": "ok", "item": "收藏 > 点赞",
                          "meaning": "典型干货/清单型内容，搜索长尾流量潜力大"})
    if fans and eng["engage_per_fan"] < 0.005:
        flags.append({"level": "high", "item": "篇均互动 / 粉丝 < 0.5%",
                      "meaning": "粉丝活跃度极低，可能是买粉或早期爆款后停更导致僵尸粉"})
    if fans and eng["engage_per_fan"] > 0.2:
        flags.append({"level": "ok", "item": "篇均互动 / 粉丝 > 20%",
                      "meaning": "粉丝质量高，账号处于强信任关系，适合做转化"})
    if eng["top1_share"] > 0.5:
        flags.append({"level": "mid", "item": "单条占比 > 50%",
                      "meaning": "流量高度集中在一条，账号抗风险能力弱"})
    return {"flags": flags, "risk_level": "high" if any(f["level"] == "high" for f in flags)
            else ("mid" if any(f["level"] == "mid" for f in flags) else "low")}


def monetization_block(profile: dict, notes: list[dict]) -> dict:
    profile_text = f"{profile.get('nickname', '')} {profile.get('desc', '')}"
    corpus = profile_text + " " + " ".join(
        f"{n.get('title', '')} {n.get('desc', '')}" for n in notes)
    hits: dict[str, dict] = {}
    for model, words in MONETIZE.items():
        matched = match_lexicon(corpus, words)
        if matched:
            hits[model] = {"signals": matched[:12], "strength": min(10, len(matched))}
    notes_with_cta = [n for n in notes if n["cta_words"]]
    fan_stage = "头部" if profile.get("fans", 0) >= 500_000 else \
        "腰部" if profile.get("fans", 0) >= 50_000 else \
        "尾部" if profile.get("fans", 0) >= 5_000 else "素人"
    return {
        "detected": hits,
        "models": sorted(hits, key=lambda k: -hits[k]["strength"]),
        "cta_rate": _safe_div(len(notes_with_cta), len(notes)),
        "fan_stage": fan_stage,
        "fans": profile.get("fans", 0),
        "profile_desc": profile.get("desc", ""),
        "verdict_input": {
            "has_clear_model": len(hits) > 0,
            "model_count": len(hits),
            "cta_coverage": _safe_div(len(notes_with_cta), len(notes)),
        },
    }


def comments_block(notes: list[dict]) -> dict:
    all_comments: list[dict] = []
    for n in notes:
        for c in n.get("comments") or []:
            c = dict(c)
            c["note_id"] = n.get("note_id")
            c["note_title"] = n.get("title") or (n.get("desc") or "")[:24]
            all_comments.append(c)
    if not all_comments:
        return {"count": 0}
    intents = {
        "求链接/求购买": ["链接", "哪里买", "求", "买", "多少钱", "价格", "同款", "店铺", "橱窗"],
        "求教程/求细节": ["怎么", "如何", "教程", "步骤", "配方", "方法", "详细", "参数", "尺寸"],
        "共鸣/夸赞": ["好看", "喜欢", "太美", "绝了", "爱了", "厉害", "牛", "感谢", "有用", "收藏了"],
        "质疑/吐槽": ["不", "假的", "广告", "智商税", "没用", "骗", "差", "一般", "踩雷"],
        "求更新/催更": ["更新", "下期", "还想看", "再来", "多出", "催更"],
    }
    buckets = {k: [] for k in intents}
    for c in all_comments:
        text = c.get("content", "")
        for intent, words in intents.items():
            if any(w in text for w in words):
                buckets[intent].append(text)
    top = sorted(all_comments, key=lambda c: -(c.get("like_count") or 0))[:15]
    return {
        "count": len(all_comments),
        "covered_notes": len({c["note_id"] for c in all_comments}),
        "intent_distribution": {k: len(v) for k, v in buckets.items()},
        "intent_rate": {k: _safe_div(len(v), len(all_comments)) for k, v in buckets.items()},
        "intent_samples": {k: v[:6] for k, v in buckets.items() if v},
        "top_comments": [{"content": c.get("content", "")[:120],
                          "like_count": c.get("like_count", 0),
                          "note_title": c.get("note_title", "")} for c in top],
        "keywords": top_keywords([c.get("content", "") for c in all_comments], n=20,
                                 min_count=3 if len(all_comments) >= 20 else 2),
    }


def score_block(eng: dict, tier: dict, content: dict, monet: dict, health: dict,
                cadence: dict, profile: dict) -> dict:
    def clamp(v: float) -> int:
        return max(0, min(100, int(round(v))))

    fans = profile.get("fans", 0) or 0
    # 商业价值：粉丝体量(30) + 互动效率(30) + 变现清晰度(25) + 更新稳定性(15)
    fan_score = min(30, 30 * (min(fans, 1_000_000) / 1_000_000) ** 0.45)
    eff = eng.get("engage_per_fan", 0)
    eff_score = 30 * min(1.0, eff / 0.15) if fans else 15
    money_score = 25 * min(1.0, monet["verdict_input"]["model_count"] / 2) if monet["verdict_input"][
        "has_clear_model"] else 0
    money_score = max(money_score, 25 * min(1.0, monet["cta_rate"] / 0.5))
    stable_score = 15 * min(1.0, (cadence.get("posts_per_week", 0) or 0) / 4)
    business = clamp(fan_score + eff_score + money_score + stable_score)

    # 内容力：结构完整度（人群/痛点/形式命中）为主，互动效率为辅
    structure = 100 * (0.35 * min(1, content["audience_rate"] / 0.6) +
                       0.3 * min(1, content["pain_rate"] / 0.5) +
                       0.35 * min(1, content["format_rate"] / 0.5))
    content_score = clamp(0.75 * structure + 0.25 * 100 * min(1.0, eff / 0.03))

    # 爆款确定性：水位占峰值比例（能否稳定复现）+ 流量结构稳态 + 爆款率
    water_ratio = tier.get("water_ratio", 0)
    steadiness = tier.get("steadiness", 0)
    certainty = clamp(100 * (0.45 * min(1.0, water_ratio / 0.25) +
                             0.30 * steadiness +
                             0.25 * min(1.0, eng["viral_rate"] / 0.15)))

    # 可复制性：标签聚焦 + 套路稳定 + 爆款可复现 + 流量稳态
    focus = 1 - min(1, content["tag_diversity"])
    replicability = clamp(100 * (0.30 * focus +
                                 0.25 * min(1, content["format_rate"] / 0.5) +
                                 0.20 * min(1, eng["viral_rate"] / 0.15) +
                                 0.25 * steadiness))

    health_penalty = {"high": 25, "mid": 10, "low": 0}[health["risk_level"]]
    return {
        "business_value": business,
        "content_strength": content_score,
        "viral_certainty": certainty,
        "replicability": replicability,
        "health_score": clamp(100 - health_penalty),
        "overall": clamp((business * 0.3 + content_score * 0.25 + certainty * 0.2 +
                          replicability * 0.15 + (100 - health_penalty) * 0.1)),
        "formula_note": "商业价值=粉丝体量30+互动效率30+变现清晰度25+更新稳定15；"
                        "内容力=结构命中75+互动效率25；爆款确定性=水位占峰值45+流量稳态30+爆款率25；"
                        "可复制性=标签聚焦30+套路稳定25+爆款率20+流量稳态25。均为本技能自定义指标，非官方数据",
    }


def gaps_block(content: dict, eng: dict, cadence: dict, monet: dict, tier: dict) -> list[dict]:
    gaps = []
    if content["audience_rate"] < 0.4:
        gaps.append({"gap": "标题缺少明确人群锚点", "evidence": f"命中率 {content['audience_rate']:.0%}",
                     "action": "每条标题前置人群词（如「油皮」「租房党」「新手」）"})
    if content["pain_rate"] < 0.35:
        gaps.append({"gap": "缺少痛点钩子", "evidence": f"命中率 {content['pain_rate']:.0%}",
                     "action": "在标题或前 2 行加入失败场景词（踩坑/翻车/太贵/没时间）"})
    if content["tag_diversity"] > 0.7:
        gaps.append({"gap": "标签过于分散，赛道不聚焦", "evidence": f"标签离散度 {content['tag_diversity']:.2f}",
                     "action": "收敛到 3 个核心标签 + 2 个流量标签，连续 10 篇不变"})
    complete = eng.get("data_completeness", {})
    # 基准：家居/生活方式类账号收藏/点赞常态约 8-15%，教程干货类 25-40%。
    # 旧阈值 0.3 会把 25% 的健康账号误判成"收藏率低"（真实案例：冰镇小豆奶 24.7%）。
    if complete.get("collected") and eng["collect_like_ratio"] < 0.2:
        gaps.append({"gap": "收藏率低，缺工具属性", "evidence": f"收藏/点赞 {eng['collect_like_ratio']:.0%}（行业常态 8-15%）",
                     "action": "正文加清单化结构：步骤 / 清单 / 参数表 / 可直接抄的模板"})
    if complete.get("commented") and eng["comment_like_ratio"] < 0.02:
        gaps.append({"gap": "评论区没有讨论钩子", "evidence": f"评论/点赞 {eng['comment_like_ratio']:.2%}",
                     "action": "结尾抛二选一问题或留一个「故意的小错误」引导纠正"})
    if missing := complete.get("missing"):
        gaps.append({"gap": f"数据缺失：{'、'.join(missing)}未采集到",
                     "evidence": "列表页 SSR 只下发点赞数",
                     "action": "详情页 SSR 可补齐收藏/评论/分享（xhs_crawl --detail-top >0 已自动抓取）；评论原文需登录态"})
    if (cadence.get("posts_per_week") or 0) < 2:
        gaps.append({"gap": "更新频次过低", "evidence": f"{cadence.get('posts_per_week', 0)} 篇/周",
                     "action": "先提频次到 3 篇/周，算法才有足够样本识别账号标签"})
    if not monet["verdict_input"]["has_clear_model"]:
        gaps.append({"gap": "变现路径不清晰", "evidence": "未识别到稳定变现信号",
                     "action": "在简介与每篇结尾固定同一个转化动作（店铺 / 私域 / 课程）"})
    return gaps


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def analyze(dataset: dict) -> dict:
    profile = dataset.get("profile", {})
    notes = enrich_notes(list(dataset.get("notes", [])))
    if not notes:
        raise SystemExit("dataset.json 中没有笔记数据，先执行 xhs_crawl.py")

    fans = human_num(profile.get("fans"))
    profile["fans"] = fans
    notes.sort(key=lambda n: n.get("timestamp") or 0, reverse=True)

    eng = engagement_block(notes, fans)
    cadence = cadence_block(notes)
    content = content_block(notes)
    formats = format_block(notes)
    tier = tier_block(eng, fans, cadence)
    health = health_block(eng, notes, fans)
    monet = monetization_block(profile, notes)
    comments = comments_block(notes)
    scores = score_block(eng, tier, content, monet, health, cadence, profile)
    gaps = gaps_block(content, eng, cadence, monet, tier)

    ranked = sorted(notes, key=lambda n: -n["liked"])
    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "meta": dataset.get("meta", {}),
        "profile": profile,
        "engagement": eng,
        "cadence": cadence,
        "content": content,
        "formats": formats,
        "tier": tier,
        "health": health,
        "monetization": monet,
        "comments": comments,
        "scores": scores,
        "gaps": gaps,
        "top_notes": [{
            "note_id": n["note_id"], "title": n.get("title") or (n.get("desc") or "")[:30],
            "type": n["type"], "liked": n["liked"], "collected": n["collected"],
            "commented": n["commented"], "shared": n["shared"],
            "collect_like": n["collect_like"], "comment_like": n["comment_like"],
            "tags": n.get("tags", []), "note_url": n.get("note_url", ""),
            "timestamp": n.get("timestamp", 0),
            "date": time.strftime("%Y-%m-%d", time.localtime(n["timestamp"] / 1000)) if n.get("timestamp") else "",
            "duration_sec": n.get("duration_sec", 0), "image_count": n.get("image_count", 0),
        } for n in ranked[:20]],
        "notes_count": len(notes),
    }
    return result


def write_csv(notes: list[dict], path: Path) -> None:
    fields = ["date", "title", "type", "liked", "collected", "commented", "shared",
              "total_engage", "collect_like", "comment_like", "tags", "duration_sec",
              "image_count", "title_len", "emoji_count", "note_url"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for n in sorted(notes, key=lambda x: -(x.get("timestamp") or 0)):
            row = dict(n)
            row["date"] = time.strftime("%Y-%m-%d", time.localtime(n["timestamp"] / 1000)) if n.get("timestamp") else ""
            row["tags"] = " / ".join(n.get("tags") or [])
            writer.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default="", help="输出目录，默认与 dataset 同级")
    args = ap.parse_args()

    dataset_path = Path(args.dataset).resolve()
    dataset = read_json(dataset_path)
    if not dataset:
        raise SystemExit(f"读取失败：{dataset_path}")
    out_dir = Path(args.out).resolve() if args.out else dataset_path.parent

    result = analyze(dataset)
    write_json(out_dir / "analysis.json", result)
    write_csv(dataset.get("notes", []), out_dir / "notes_metrics.csv")

    s, t, e = result["scores"], result["tier"], result["engagement"]
    log.info("笔记 %s 条 | 层级 %s(%s) | 峰值赞 %s | 水位 %s | 浓度 %s",
             result["notes_count"], t["level"], t["shape"],
             fmt_num(t["peak_liked"]), fmt_num(t["water_level"]), t["concentration"])
    log.info("评分：商业价值 %s / 内容力 %s / 爆款确定性 %s / 可复制性 %s / 综合 %s",
             s["business_value"], s["content_strength"], s["viral_certainty"],
             s["replicability"], s["overall"])
    log.info("输出：%s", out_dir / "analysis.json")
    return 0


if __name__ == "__main__":
    from xhs_env import ensure_ready
    ensure_ready(need_browser=False)     # 纯分析，不需要 Chromium 内核
    raise SystemExit(main())
