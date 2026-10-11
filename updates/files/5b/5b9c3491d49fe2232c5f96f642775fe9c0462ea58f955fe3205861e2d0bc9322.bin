#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Content Matrix — 一人公司/个人创作者全平台内容矩阵
把有限时间转成一周可执行的内容计划：定位、选题、拆解、排期、对标、合规、复盘、变现。

Run:
  python scripts/main.py
  python scripts/main.py --json
  python scripts/main.py --with-metrics
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


# 解决 Windows 控制台中文/emoji 乱码（非 Windows 上 reconfigure 不存在，忽略）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


VERSION = "1.0.0"


class Platform(Enum):
    DOUYIN = "抖音"
    XIAOHONGSHU = "小红书"
    BILIBILI = "B站"
    SHIPINHAO = "视频号"
    WECHAT = "公众号"
    ZHIHU = "知乎"
    WEIBO = "微博"
    KUAISHOU = "快手"
    TOUTIAO = "今日头条"
    XIGUA = "西瓜视频"
    BAIJIA = "百家号"
    DOUBAN = "豆瓣"


PLATFORM_KNOWLEDGE: Dict[Platform, Dict[str, Any]] = {
    Platform.BILIBILI: {
        "form": "中长视频",
        "positioning": "系统教程、案例实操、长期搜索资产",
        "prime_time": "周末、12:00-14:00、18:00-22:00",
        "solo_score": 4,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.45, "interaction_rate": 0.05},
        "monetization": "创作激励、花火商单、课程引流",
        "ad_threshold": 10000,
    },
    Platform.ZHIHU: {
        "form": "长图文/问答",
        "positioning": "专业回答、搜索流量、信任背书",
        "prime_time": "全天，优先抢新问题",
        "solo_score": 5,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.60, "interaction_rate": 0.04},
        "monetization": "好物推荐、付费咨询、私域引流",
        "ad_threshold": 0,
    },
    Platform.WECHAT: {
        "form": "长图文",
        "positioning": "私域沉淀、产品说明、长期复购",
        "prime_time": "工作日 07:00-09:00、12:00-14:00",
        "solo_score": 4,
        "coldstart": 4,
        "metrics": {"open_rate": 0.05, "interaction_rate": 0.03},
        "monetization": "流量主、课程、小册、社群",
        "ad_threshold": 500,
    },
    Platform.XIAOHONGSHU: {
        "form": "图文/短视频",
        "positioning": "攻略卡片、真实体验、收藏型内容",
        "prime_time": "20:00-23:00、07:00-09:00",
        "solo_score": 4,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.35, "interaction_rate": 0.05},
        "monetization": "蒲公英商单、资料包引流、低价产品",
        "ad_threshold": 1000,
    },
    Platform.SHIPINHAO: {
        "form": "短视频",
        "positioning": "1分钟可转发资产，承接微信生态",
        "prime_time": "12:00-14:00、20:00-22:00",
        "solo_score": 5,
        "coldstart": 2,
        "metrics": {"completion_rate": 0.40, "interaction_rate": 0.04},
        "monetization": "微信私域、直播、带货、服务咨询",
        "ad_threshold": 100,
    },
    Platform.DOUYIN: {
        "form": "短视频",
        "positioning": "强钩子、强节奏、强场景演示",
        "prime_time": "18:00-22:00",
        "solo_score": 2,
        "coldstart": 4,
        "metrics": {"completion_rate": 0.30, "interaction_rate": 0.04},
        "monetization": "星图商单、团购/带货、直播",
        "ad_threshold": 1000,
    },
    Platform.WEIBO: {
        "form": "短图文/热点",
        "positioning": "热点借势、观点扩散、事件评论",
        "prime_time": "热点发生时即时",
        "solo_score": 3,
        "coldstart": 2,
        # 微博无稳定完播/互动基准，不硬设 → 复盘时标注「暂无基准」
        "metrics": {},
        "monetization": "微任务、品牌曝光",
        "ad_threshold": 1000,
    },
    Platform.KUAISHOU: {
        "form": "短视频/直播",
        "positioning": "下沉市场、强私域信任、老铁经济、直播带货",
        "prime_time": "18:00-22:00、午间 12:00-14:00",
        "solo_score": 3,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.35, "interaction_rate": 0.06},
        "monetization": "快接单、直播带货、小店、私域",
        "ad_threshold": 1000,
    },
    Platform.TOUTIAO: {
        "form": "图文/短视频",
        "positioning": "算法分发、资讯流量、搜索沉淀、头条号收益",
        "prime_time": "07:00-09:00、12:00-14:00、18:00-22:00",
        "solo_score": 4,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.40, "interaction_rate": 0.04},
        "monetization": "头条创作收益、商品卡、付费专栏",
        "ad_threshold": 0,
    },
    Platform.XIGUA: {
        "form": "中短视频",
        "positioning": "中视频计划、影视/科普/生活类，西瓜+抖音双发",
        "prime_time": "18:00-22:00",
        "solo_score": 3,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.40, "interaction_rate": 0.04},
        "monetization": "中视频计划收益、带货",
        "ad_threshold": 0,
    },
    Platform.BAIJIA: {
        "form": "图文/动态",
        "positioning": "百度搜索生态、SEO 长尾、百家号收益与品牌背书",
        "prime_time": "08:00-10:00、19:00-21:00",
        "solo_score": 4,
        "coldstart": 3,
        "metrics": {"completion_rate": 0.45, "interaction_rate": 0.03},
        "monetization": "百家号收益、百度联盟、品牌背书",
        "ad_threshold": 0,
    },
    Platform.DOUBAN: {
        "form": "长文/小组",
        "positioning": "文艺/深度/书影音口碑，小组讨论与长尾口碑",
        "prime_time": "20:00-23:00",
        "solo_score": 3,
        "coldstart": 2,
        # 豆瓣无稳定完播/互动基准，不硬设 → 复盘时标注「暂无基准」
        "metrics": {},
        "monetization": "品牌口碑、周边/课程导流（弱变现）",
        "ad_threshold": 0,
    },
}


# 领域适配矩阵：覆盖更多行业，可按需增改
FIELD_MATRIX: Dict[str, Dict[str, Any]] = {
    "编程技术": {
        "primary": [Platform.BILIBILI, Platform.ZHIHU],
        "secondary": [Platform.WECHAT, Platform.XIAOHONGSHU, Platform.SHIPINHAO],
        "pause": [Platform.DOUYIN],
        "reason": "技术内容需要代码细节、搜索沉淀和信任背书，短视频只适合拆片辅助。",
    },
    "知识付费": {
        "primary": [Platform.BILIBILI, Platform.WECHAT],
        "secondary": [Platform.ZHIHU, Platform.SHIPINHAO],
        "pause": [Platform.WEIBO],
        "reason": "高转化来自长内容信任和私域承接，避免只追泛流量。",
    },
    "职场效率": {
        "primary": [Platform.XIAOHONGSHU, Platform.ZHIHU],
        "secondary": [Platform.WECHAT, Platform.SHIPINHAO],
        "pause": [],
        "reason": "方法论和工具清单适合收藏、搜索和私域沉淀。",
    },
    "美妆护肤": {
        "primary": [Platform.XIAOHONGSHU, Platform.DOUYIN],
        "secondary": [Platform.SHIPINHAO, Platform.BILIBILI],
        "pause": [Platform.ZHIHU],
        "reason": "视觉化内容需要强展示和真实体验，小红书/抖音更容易验证。",
    },
    "本地生活": {
        "primary": [Platform.DOUYIN, Platform.XIAOHONGSHU],
        "secondary": [Platform.SHIPINHAO, Platform.WEIBO],
        "pause": [Platform.BILIBILI],
        "reason": "本地生活依赖即时推荐、搜索种草和交易链路。",
    },
    "实体电商": {
        "primary": [Platform.DOUYIN, Platform.XIAOHONGSHU],
        "secondary": [Platform.SHIPINHAO, Platform.BILIBILI],
        "pause": [Platform.WEIBO],
        "reason": "商品展示和转化链路优先，短视频/直播更直接。",
    },
    "金融财经": {
        "primary": [Platform.WECHAT, Platform.ZHIHU],
        "secondary": [Platform.BILIBILI, Platform.SHIPINHAO],
        "pause": [Platform.DOUYIN],
        "reason": "专业信任与合规优先，长内容沉淀更稳，短视频需谨慎表达。",
    },
    "教育培训": {
        "primary": [Platform.DOUYIN, Platform.SHIPINHAO],
        "secondary": [Platform.WECHAT, Platform.XIAOHONGSHU],
        "pause": [Platform.WEIBO],
        "reason": "短视频引流 + 私域转化是教育类标准路径。",
    },
    "健康健身": {
        "primary": [Platform.XIAOHONGSHU, Platform.DOUYIN],
        "secondary": [Platform.SHIPINHAO, Platform.BILIBILI],
        "pause": [Platform.ZHIHU],
        "reason": "视觉对比与跟练内容在短视频/图文平台转化更好。",
    },
    "游戏娱乐": {
        "primary": [Platform.BILIBILI, Platform.DOUYIN],
        "secondary": [Platform.WEIBO, Platform.SHIPINHAO],
        "pause": [Platform.ZHIHU],
        "reason": "中长视频做深度，短视频做传播，热点在微博扩散。",
    },
    "设计创意": {
        "primary": [Platform.XIAOHONGSHU, Platform.BILIBILI],
        "secondary": [Platform.SHIPINHAO, Platform.WECHAT],
        "pause": [Platform.WEIBO],
        "reason": "作品集在图文/中视频展示最佳，公众号做长文沉淀。",
    },
    "美食探店": {
        "primary": [Platform.DOUYIN, Platform.XIAOHONGSHU],
        "secondary": [Platform.KUAISHOU, Platform.SHIPINHAO],
        "pause": [Platform.ZHIHU],
        "reason": "美食靠视觉与真实体验，短视频/图文种草最强，快手覆盖下沉与本地。",
    },
    "旅游出行": {
        "primary": [Platform.XIAOHONGSHU, Platform.DOUYIN],
        "secondary": [Platform.SHIPINHAO, Platform.TOUTIAO],
        "pause": [Platform.WEIBO],
        "reason": "攻略与风景在图文/短视频传播最好，头条补足资讯流量。",
    },
    "母婴育儿": {
        "primary": [Platform.XIAOHONGSHU, Platform.DOUYIN],
        "secondary": [Platform.WECHAT, Platform.SHIPINHAO],
        "pause": [Platform.BILIBILI],
        "reason": "经验分享与真实测评在小红书/抖音信任度高，私域承接更稳定。",
    },
    "宠物萌宠": {
        "primary": [Platform.DOUYIN, Platform.XIAOHONGSHU],
        "secondary": [Platform.KUAISHOU, Platform.BILIBILI],
        "pause": [Platform.ZHIHU],
        "reason": "萌宠内容靠情绪与治愈，短视频/图文扩散最快。",
    },
    "家居装修": {
        "primary": [Platform.XIAOHONGSHU, Platform.DOUYIN],
        "secondary": [Platform.BILIBILI, Platform.TOUTIAO],
        "pause": [Platform.WEIBO],
        "reason": "案例与避坑在图文/中视频沉淀最好，头条补搜索流量。",
    },
    "科技数码": {
        "primary": [Platform.BILIBILI, Platform.DOUYIN],
        "secondary": [Platform.ZHIHU, Platform.XIGUA],
        "pause": [Platform.WEIBO],
        "reason": "测评与开箱在中视频/短视频最直观，知乎补专业讨论。",
    },
    "情感心理": {
        "primary": [Platform.WECHAT, Platform.XIAOHONGSHU],
        "secondary": [Platform.ZHIHU, Platform.DOUBAN],
        "pause": [Platform.DOUYIN],
        "reason": "深度与共鸣在长图文/小组发酵最好，短视频需克制表达。",
    },
    "文史知识": {
        "primary": [Platform.BILIBILI, Platform.DOUBAN],
        "secondary": [Platform.ZHIHU, Platform.TOUTIAO],
        "pause": [Platform.DOUYIN],
        "reason": "深度内容在中视频/小组/问答沉淀最好，头条补资讯流量。",
    },
    "三农乡村": {
        "primary": [Platform.KUAISHOU, Platform.DOUYIN],
        "secondary": [Platform.XIGUA, Platform.SHIPINHAO],
        "pause": [Platform.ZHIHU],
        "reason": "乡村真实生活在快手/抖音最接地气，中视频计划补收益。",
    },
    "法律普法": {
        "primary": [Platform.ZHIHU, Platform.TOUTIAO],
        "secondary": [Platform.WECHAT, Platform.BAIJIA],
        "pause": [Platform.DOUYIN],
        "reason": "专业普法与咨询在问答/图文信任最高，百度生态补搜索。",
    },
}


TOPIC_DATABASE: Dict[str, List[Dict[str, Any]]] = {
    "编程技术": [
        {"title": "Python自动化办公完全指南", "heat": 5, "potential": 5, "difficulty": 2},
        {"title": "零基础如何系统学习Python", "heat": 5, "potential": 4, "difficulty": 3},
        {"title": "用Python自动生成Excel周报", "heat": 4, "potential": 5, "difficulty": 2},
        {"title": "AI时代还要不要学编程", "heat": 5, "potential": 5, "difficulty": 3},
    ],
    "知识付费": [
        {"title": "如何把经验做成第一款付费小产品", "heat": 5, "potential": 5, "difficulty": 3},
        {"title": "一人公司如何设计9.9到999元产品梯度", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "低粉账号如何验证知识付费需求", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "职场效率": [
        {"title": "如何用AI每天省下1小时重复工作", "heat": 5, "potential": 5, "difficulty": 2},
        {"title": "普通人最值得搭建的个人效率系统", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "Excel、Notion、飞书到底怎么选", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "美妆护肤": [
        {"title": "新手化妆不踩雷的5个原则", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "油皮夏日控油全流程", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "平价替代是不是智商税", "heat": 4, "potential": 5, "difficulty": 3},
    ],
    "本地生活": [
        {"title": "城市小店如何靠短视频引流到店", "heat": 5, "potential": 5, "difficulty": 3},
        {"title": "探店脚本怎么写才有人看", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "新手做本地生活号的第一条视频", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "实体电商": [
        {"title": "新品冷启动的3个短视频打法", "heat": 5, "potential": 5, "difficulty": 3},
        {"title": "直播间怎么留人", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "一条带货视频的完整脚本", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "金融财经": [
        {"title": "普通人怎么开始做家庭资产配置", "heat": 5, "potential": 5, "difficulty": 3},
        {"title": "看懂一只基金要看哪几个指标", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "记账到底有没有用", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "教育培训": [
        {"title": "0基础怎么准备XX考试", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "家长最容易踩的3个辅导误区", "heat": 4, "potential": 5, "difficulty": 2},
        {"title": "如何把知识点讲得让人听懂", "heat": 4, "potential": 4, "difficulty": 3},
    ],
    "健康健身": [
        {"title": "在家也能练的10分钟燃脂", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "新手如何不伤膝盖地跑步", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "减脂到底该怎么吃", "heat": 5, "potential": 5, "difficulty": 2},
    ],
    "游戏娱乐": [
        {"title": "新手入坑XX游戏的第一课", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "这个版本最强阵容怎么搭", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "游戏里最容易被忽略的冷知识", "heat": 4, "potential": 4, "difficulty": 3},
    ],
    "设计创意": [
        {"title": "零基础也能上手的排版法则", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "如何建立自己的配色库", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "新手做海报常犯的5个错误", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "美食探店": [
        {"title": "人均50也能吃出仪式感的店", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "探店脚本怎么写才有人看", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "新手做美食号的第一条视频", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "旅游出行": [
        {"title": "小长假避开人潮的3个玩法", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "一个人旅行怎么拍出大片", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "周末周边游攻略模板", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "母婴育儿": [
        {"title": "新手妈妈必备的待产清单", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "宝宝睡眠训练的真相", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "0-1岁早教到底要不要做", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "宠物萌宠": [
        {"title": "新手养猫必买的5样东西", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "狗狗拆家怎么管", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "宠物医院避坑指南", "heat": 4, "potential": 5, "difficulty": 3},
    ],
    "家居装修": [
        {"title": "小户型显大的10个技巧", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "装修预算怎么分配不超支", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "新手最容易踩的装修坑", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "科技数码": [
        {"title": "2026年最值得买的手机怎么选", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "新手如何选第一台相机", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "一个视频讲清XX数码玩法", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "情感心理": [
        {"title": "总内耗的人该怎么自救", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "亲密关系里的沟通误区", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "如何缓解职场焦虑", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "文史知识": [
        {"title": "一个被忽略的历史冷知识", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "一本书带你读懂XX朝代", "heat": 4, "potential": 4, "difficulty": 3},
        {"title": "古人怎么过夏天", "heat": 4, "potential": 5, "difficulty": 2},
    ],
    "三农乡村": [
        {"title": "返乡青年如何靠短视频卖农货", "heat": 5, "potential": 5, "difficulty": 3},
        {"title": "农村自建房避坑指南", "heat": 4, "potential": 4, "difficulty": 2},
        {"title": "一个视频带你看真实乡村", "heat": 4, "potential": 4, "difficulty": 2},
    ],
    "法律普法": [
        {"title": "普通人最该知道的5条法律", "heat": 5, "potential": 4, "difficulty": 2},
        {"title": "租房合同里的隐藏陷阱", "heat": 4, "potential": 5, "difficulty": 3},
        {"title": "被裁员怎么合法维权", "heat": 4, "potential": 4, "difficulty": 2},
    ],
}


CSV_TEMPLATE = """日期,平台,内容标题,播放量,点赞数,评论数,收藏数,分享数,粉丝增长,完播率
2026-05-20,B站,Python自动化办公教程,45000,2800,450,1200,350,320,0.55
2026-05-20,知乎,Python自动化办公解析,12000,650,180,420,95,85,0.72
2026-05-20,小红书,Python办公攻略,3000,380,95,180,28,28,0.45
"""


@dataclass
class FounderProfile:
    field: str
    offer: str
    target_customer: str
    weekly_hours: int
    goal: str
    existing_platforms: Dict[str, int]


@dataclass
class CoreContent:
    title: str
    format: str
    summary: str


class MatrixPlanner:
    @staticmethod
    def recommend_platforms(profile: FounderProfile) -> Dict[str, Any]:
        matrix = FIELD_MATRIX.get(profile.field)
        if matrix is None:
            matrix = MatrixPlanner._generic_matrix()
        max_platforms = 2 if profile.weekly_hours < 6 else 3 if profile.weekly_hours < 12 else 4
        primary = matrix["primary"][:2]
        secondary = matrix["secondary"][: max(0, max_platforms - len(primary))]

        return {
            "field": profile.field,
            "goal": profile.goal,
            "weekly_hours": profile.weekly_hours,
            "primary": [MatrixPlanner._platform_card(p, profile) for p in primary],
            "secondary": [MatrixPlanner._platform_card(p, profile) for p in secondary],
            "pause": [p.value for p in matrix["pause"]],
            "reason": matrix["reason"],
            "max_active_platforms": max_platforms,
            "time_budget": MatrixPlanner.calculate_energy_budget(profile.weekly_hours, len(primary), len(secondary)),
        }

    @staticmethod
    def _generic_matrix() -> Dict[str, Any]:
        # 未知领域：按内容形态通用推荐
        return {
            "primary": [Platform.XIAOHONGSHU, Platform.ZHIHU],
            "secondary": [Platform.WECHAT, Platform.SHIPINHAO],
            "pause": [Platform.DOUYIN],
            "reason": "未识别到具体领域，按「图文沉淀 + 短视频引流」的通用组合推荐，可据实调整。",
        }

    @staticmethod
    def _platform_card(platform: Platform, profile: FounderProfile) -> Dict[str, Any]:
        kb = PLATFORM_KNOWLEDGE[platform]
        followers = profile.existing_platforms.get(platform.value, 0)
        return {
            "platform": platform.value,
            "form": kb["form"],
            "positioning": kb["positioning"],
            "prime_time": kb["prime_time"],
            "followers": followers,
            "coldstart": kb["coldstart"],
            "ad_threshold": kb["ad_threshold"],
            "threshold_status": "已达参考门槛" if followers >= kb["ad_threshold"] else f"距参考门槛差 {max(0, kb['ad_threshold'] - followers)} 粉",
        }

    @staticmethod
    def calculate_energy_budget(weekly_hours: int, primary_count: int, secondary_count: int) -> Dict[str, str]:
        ratios = {
            "选题策划": 0.15,
            "核心内容生产": 0.45,
            "拆解改写": 0.20,
            "分发互动": 0.10,
            "数据复盘": 0.10,
        }
        budget: Dict[str, str] = {}
        for name, ratio in ratios.items():
            hours = weekly_hours * ratio
            # 兜底：即便总时间短，关键动作也至少给 0.5h，避免 0h 显得不合理
            budget[name] = f"{max(0.5, round(hours, 1))}h" if weekly_hours > 0 else "0h"
        budget["active_mix"] = f"{primary_count}个主平台 + {secondary_count}个辅助平台"
        return budget


class TopicScheduler:
    @staticmethod
    def score_topic(search_heat: int, interaction_potential: int, creation_difficulty: int) -> Dict[str, Any]:
        notes: List[str] = []
        # 容错：超出 1-5 范围时按 5 封顶并提示，而不是抛异常中断
        heat = max(1, min(5, int(round(search_heat))))
        potential = max(1, min(5, int(round(interaction_potential))))
        difficulty = max(1, min(5, int(round(creation_difficulty))))
        if search_heat != heat or interaction_potential != potential or creation_difficulty != difficulty:
            notes.append("部分维度超出 1-5，已按 5 封顶处理")

        difficulty_bonus = 6 - difficulty
        # 上限恰好 100：5*5*5/125*100 = 100
        score = heat * potential * difficulty_bonus / 125 * 100
        if score >= 80:
            level = "优先创作"
        elif score >= 60:
            level = "本周备选"
        elif score >= 40:
            level = "放入题库"
        else:
            level = "暂不投入"
        return {
            "score": round(score, 1),
            "level": level,
            "formula": f"{heat} × {potential} × (6 - {difficulty}) / 125 × 100",
            "breakdown": {
                "搜索热度": heat,
                "互动潜力": potential,
                "创作难度": difficulty,
                "难度加成": difficulty_bonus,
            },
            "notes": notes,
        }

    @staticmethod
    def mine_topics(field: str) -> List[Dict[str, Any]]:
        topics = TOPIC_DATABASE.get(field, TOPIC_DATABASE.get("职场效率"))
        scored = []
        for topic in topics:
            score = TopicScheduler.score_topic(topic["heat"], topic["potential"], topic["difficulty"])
            scored.append({**topic, **score})
        return sorted(scored, key=lambda item: item["score"], reverse=True)

    @staticmethod
    def generate_calendar(
        primary: Iterable[str],
        secondary: Iterable[str],
        core_title: str,
        weekly_hours: int,
    ) -> List[Dict[str, Any]]:
        primary_list = list(primary)
        secondary_list = list(secondary)
        tasks = [
            ("周一", "选题确认 + 素材整理", "全平台", f"确定《{core_title}》角度和资料包", 1.0, "选题评分>=60"),
            ("周二", "核心内容生产", primary_list[0] if primary_list else "主平台", "完成长文/长视频脚本初稿", round(weekly_hours * 0.25, 1), "脚本可发布"),
            ("周三", "主平台发布", primary_list[0] if primary_list else "主平台", "发布核心内容并置顶评论引导资料包", 1.0, "收藏率/完播率"),
            ("周四", "搜索平台改写", primary_list[1] if len(primary_list) > 1 else "知乎/公众号", "改写为问答或长图文", 1.5, "阅读完成率"),
            ("周五", "辅助平台拆片", secondary_list[0] if secondary_list else "辅助平台", "拆出2-3条短内容/图文卡片", 1.5, "互动率"),
            ("周六", "互动与私域承接", "全平台", "回复评论、收集问题、更新FAQ", 1.0, "私信/领取数"),
            ("周日", "数据复盘 + 下周实验", "全平台", "记录指标，决定加码/降频", 1.0, "下周动作清单"),
        ]
        return [
            {"day": day, "task": task, "platform": platform, "output": output, "hours": hours, "metric": metric}
            for day, task, platform, output, hours, metric in tasks
        ]


class ContentKitchen:
    PRODUCTION_TIME = {
        Platform.BILIBILI: 240,
        Platform.ZHIHU: 90,
        Platform.WECHAT: 120,
        Platform.XIAOHONGSHU: 45,
        Platform.SHIPINHAO: 45,
        Platform.DOUYIN: 60,
        Platform.WEIBO: 15,
        Platform.KUAISHOU: 60,
        Platform.TOUTIAO: 90,
        Platform.XIGUA: 120,
        Platform.BAIJIA: 90,
        Platform.DOUBAN: 120,
    }

    @staticmethod
    def dismantle_content(content: CoreContent, target_platforms: List[str]) -> List[Dict[str, Any]]:
        output = []
        for platform_name in target_platforms:
            platform = platform_from_name(platform_name)
            if platform is None:
                continue
            output.append(ContentKitchen._adapt(content, platform))
        return output

    # 每个平台的「内容简报」模板：标题、Hook、封面思路、结构大纲、交付物、CTA、目标
    _BRIEF_TEMPLATES = {
        Platform.BILIBILI: {
            "title": "{t}：从入门到实战",
            "hook": "这期用一个真实场景讲清楚：{t}。",
            "cover": "对比封面：左边「加班 3 小时」vs 右边「10 分钟搞定」，大字标结果",
            "outline": "① 痛点场景 ② 整体思路 ③ 分步实操（含代码） ④ 避坑 ⑤ 资料包领取",
            "deliverable": "8-12分钟教程视频 + 代码/资料包",
            "cta": "评论区置顶资料包关键词，引导私信/收藏",
            "publish_goal": "收藏、投币、搜索沉淀",
        },
        Platform.ZHIHU: {
            "title": "如何系统掌握{t}？",
            "hook": "先给结论，再拆步骤，最后给可复制模板。",
            "cover": "文字封面：一句话结论 + 3 个分点，突出「系统性」",
            "outline": "① 结论先行 ② 为什么难 ③ 分步方法 ④ 模板/案例 ⑤ 延伸资料",
            "deliverable": "2000字问答 + 案例 + 资料包入口",
            "cta": "文末放「可复制模板」入口，引导关注专栏",
            "publish_goal": "赞同、收藏、搜索长尾",
        },
        Platform.WECHAT: {
            "title": "{t}：一人公司实战手册",
            "hook": "把散点经验整理成可复用流程，适合私域沉淀。",
            "cover": "信息图封面：流程四步 + 一个关键数字",
            "outline": "① 背景与痛点 ② 我的做法 ③ 可复用 SOP ④ 工具清单 ⑤ 领取/转化",
            "deliverable": "长文 + 产品说明 + 领取入口",
            "cta": "文末引导加企微/进社群，承接产品",
            "publish_goal": "打开率、转发、私域转化",
        },
        Platform.XIAOHONGSHU: {
            "title": "{t}｜可直接照做",
            "hook": "封面突出结果：省时间、少踩坑、可复制。",
            "cover": "首图大字结果 + 步骤缩略，统一封面风格利于系列化",
            "outline": "① 结果展示 ② 适用人群 ③ 步骤清单 ④ 注意事项 ⑤ 资料领取",
            "deliverable": "6-9页攻略卡片 + 清单式正文",
            "cta": "评论区引导「想要模板」+ 主页置顶",
            "publish_goal": "收藏率、评论问题",
        },
        Platform.SHIPINHAO: {
            "title": "1分钟看懂：{t}",
            "hook": "用一个前后对比展示价值。",
            "cover": "前后对比动态封面，前「低效」后「搞定」",
            "outline": "① 问题 ② 一句话方法 ③ 演示 ④ 引导资料",
            "deliverable": "60秒短视频 + 评论区资料引导",
            "cta": "评论区置顶资料，借微信生态转发",
            "publish_goal": "转发、私信、社群流动",
        },
        Platform.DOUYIN: {
            "title": "别再低效了，{t}这样做",
            "hook": "前三秒展示痛点和结果差异。",
            "cover": "前三帧放痛点画面 + 结果字幕，强节奏卡点",
            "outline": "① 3 秒痛点 ② 反转方法 ③ 快速演示 ④ 结尾引导",
            "deliverable": "30-60秒强节奏短视频",
            "cta": "评论区留问题，引导主页/直播间",
            "publish_goal": "完播率、收藏",
        },
        Platform.WEIBO: {
            "title": "{t}的3个关键点",
            "hook": "用观点摘要接热点或行业讨论。",
            "cover": "九宫格要点图，配一句观点摘要",
            "outline": "① 观点 ② 3 个要点 ③ 讨论引导",
            "deliverable": "短图文 + 九宫格要点",
            "cta": "引导转发讨论，承接其他平台",
            "publish_goal": "转发、讨论",
        },
        Platform.KUAISHOU: {
            "title": "老铁都在看的{t}",
            "hook": "用真实、接地气的方式讲清楚：{t}。",
            "cover": "真人出镜笑脸 + 大字利益点，强化「老铁信任」",
            "outline": "① 真实场景 ② 直给方法 ③ 演示 ④ 引导关注/直播间",
            "deliverable": "短视频/直播切片 + 老铁互动",
            "cta": "引导关注、进直播间或小店，强调「实在」",
            "publish_goal": "互动率、私域、带货",
        },
        Platform.TOUTIAO: {
            "title": "{t}：一文说清",
            "hook": "用事实和结论切入，适合算法分发与搜索。",
            "cover": "信息图封面：结论 + 关键数据，利于点击",
            "outline": "① 结论先行 ② 背景 ③ 分步/要点 ④ 延伸阅读",
            "deliverable": "图文/短视频 + 头条号收益",
            "cta": "引导关注头条号、点击商品卡或专栏",
            "publish_goal": "阅读量、点击、收益",
        },
        Platform.XIGUA: {
            "title": "{t}：中视频详解",
            "hook": "用一个完整案例把{t}讲透。",
            "cover": "封面放案例对比图，突出「看完能懂」",
            "outline": "① 问题引入 ② 完整演示 ③ 要点总结 ④ 引导点赞",
            "deliverable": "1-5分钟中视频 + 中视频计划收益",
            "cta": "引导点赞关注，西瓜/抖音双发承接",
            "publish_goal": "播放、完播、收益",
        },
        Platform.BAIJIA: {
            "title": "{t}：百度搜索也能找到的答案",
            "hook": "从搜索意图出发，给出可检索的干货。",
            "cover": "标题体封面，强调「干货/权威」",
            "outline": "① 搜索意图 ② 方法/答案 ③ 案例 ④ 延伸",
            "deliverable": "图文/动态 + 百家号收益",
            "cta": "引导关注百家号、百度生态品牌背书",
            "publish_goal": "阅读、搜索长尾、背书",
        },
        Platform.DOUBAN: {
            "title": "关于{t}，一些不吐不快的话",
            "hook": "用真诚、有态度的长文接小组或书影音讨论。",
            "cover": "氛围图 + 一句态度，适合文艺/深度调性",
            "outline": "① 态度/观点 ② 细节与故事 ③ 讨论引导",
            "deliverable": "长文/小组帖 + 口碑沉淀",
            "cta": "引导小组讨论，弱变现、重口碑",
            "publish_goal": "讨论、收藏、口碑",
        },
    }

    @staticmethod
    def _adapt(content: CoreContent, platform: Platform) -> Dict[str, Any]:
        t = content.title
        item = ContentKitchen._BRIEF_TEMPLATES[platform]
        return {
            "platform": platform.value,
            "content_form": PLATFORM_KNOWLEDGE[platform]["form"],
            "title": item["title"].format(t=t),
            "hook": item["hook"].format(t=t),
            "cover_idea": item["cover"],
            "outline": item["outline"],
            "deliverable": item["deliverable"],
            "cta": item["cta"],
            "production_minutes": ContentKitchen.PRODUCTION_TIME[platform],
            "publish_goal": item["publish_goal"],
            "prime_time": PLATFORM_KNOWLEDGE[platform]["prime_time"],
        }


class AnalyticsBoard:
    # 互动率正确公式应包含收藏与分享；缺字段自动按 0 处理
    NUMERIC_FIELDS = ["播放量", "点赞数", "评论数", "收藏数", "分享数", "粉丝增长", "完播率"]

    @staticmethod
    def import_from_csv(csv_content: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        for raw in reader:
            # 字段名容错：去掉可能存在的 BOM 与首尾空格
            row = {(k.strip().lstrip("\ufeff")): v for k, v in raw.items() if k is not None}
            for field in AnalyticsBoard.NUMERIC_FIELDS:
                row[field] = safe_float(row.get(field, 0))
            plays = row.get("播放量", 0)
            if plays > 0:
                interactions = row["点赞数"] + row["评论数"] + row["收藏数"] + row["分享数"]
                row["互动率"] = round(interactions / plays, 4)
                row["涨粉率"] = round(row["粉丝增长"] / plays, 4)
            else:
                row["互动率"] = 0.0
                row["涨粉率"] = 0.0
            rows.append(row)
        return rows

    @staticmethod
    def cross_platform_compare(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"summary": "没有可分析的数据", "platforms": [], "insights": [], "has_baseline": {}}

        # 按平台汇总（支持多行同类数据）
        agg = defaultdict(lambda: {"plays": 0, "likes": 0, "comments": 0, "favorites": 0, "shares": 0, "followers": 0, "completion_sum": 0.0, "completion_n": 0, "titles": []})
        for row in rows:
            platform = row.get("平台", "")
            if not platform:
                continue
            a = agg[platform]
            a["plays"] += row.get("播放量", 0)
            a["likes"] += row.get("点赞数", 0)
            a["comments"] += row.get("评论数", 0)
            a["favorites"] += row.get("收藏数", 0)
            a["shares"] += row.get("分享数", 0)
            a["followers"] += row.get("粉丝增长", 0)
            comp = row.get("完播率", 0)
            if comp:
                a["completion_sum"] += comp
                a["completion_n"] += 1
            title = row.get("内容标题", "")
            if title:
                a["titles"].append(title)

        platforms = []
        has_baseline: Dict[str, bool] = {}
        for name, a in agg.items():
            kb = PLATFORM_KNOWLEDGE.get(platform_from_name(name))
            metrics = kb.get("metrics", {}) if kb else {}
            avg_interaction = metrics.get("interaction_rate")
            completion_line = metrics.get("completion_rate")
            baseline_exists = avg_interaction is not None or completion_line is not None
            has_baseline[name] = baseline_exists

            interaction = (a["likes"] + a["comments"] + a["favorites"] + a["shares"]) / a["plays"] if a["plays"] > 0 else 0.0
            completion = (a["completion_sum"] / a["completion_n"]) if a["completion_n"] > 0 else 0.0

            if not baseline_exists:
                decision = "保持观察"
            elif interaction >= avg_interaction * 1.5 or completion >= completion_line * 1.2:
                decision = "加码"
            elif interaction < avg_interaction * 0.7 or (completion_line and completion < completion_line * 0.7):
                decision = "优化/降频"
            else:
                decision = "保持测试"

            platforms.append({
                "平台": name,
                "标题": "、".join(a["titles"][:3]),
                "播放量": int(a["plays"]),
                "互动率": round(interaction, 4),
                "完播率": round(completion, 4),
                "涨粉": int(a["followers"]),
                "判断": decision,
            })

        # 「最该加码」只从有基准且达标的平台中选
        scaled = [p for p in platforms if p["判断"] == "加码"]
        if scaled:
            best = sorted(scaled, key=lambda item: (item["互动率"], item["涨粉"]), reverse=True)[0]
            summary = f"{best['平台']}表现最佳，可加码"
        else:
            best = sorted(platforms, key=lambda item: (item["互动率"], item["涨粉"]), reverse=True)[0]
            summary = f"暂无平台达到加码基准，优先观察 {best['平台']}"

        insights = [
            f"最该加码：{best['平台']}，互动率 {best['互动率']:.1%}，涨粉 {best['涨粉']}。",
            "下周只做一个变量实验：标题钩子、封面、时长或结尾转化入口，不要同时改太多。",
            "无基准平台（如微博）仅作观察，不参与加码/降频判断。",
        ]
        return {"summary": summary, "platforms": platforms, "insights": insights, "has_baseline": has_baseline}

    @staticmethod
    def csv_template() -> str:
        return CSV_TEMPLATE


class MonetizationPlanner:
    @staticmethod
    def match_monetization_model(profile: FounderProfile) -> Dict[str, Any]:
        total_followers = sum(profile.existing_platforms.values())
        if total_followers < 1000:
            stage = "验证期"
            action = "先用免费资料包换取私信/社群线索，验证痛点和表达。"
        elif total_followers < 10000:
            stage = "小产品期"
            action = "上线9.9-99元模板/小册，测试付费意愿。"
        else:
            stage = "产品矩阵期"
            action = "搭建低价小产品 + 中价训练营 + 高价咨询/陪跑。"

        return {
            "stage": stage,
            "total_followers": total_followers,
            "this_week_action": action,
            "product_ladder": [
                {"level": "免费", "product": f"{profile.field}资料包/检查清单", "purpose": "私域引流"},
                {"level": "低价 9.9-99", "product": profile.offer or "模板/小册", "purpose": "验证需求"},
                {"level": "中价 199-499", "product": f"{profile.field}训练营/系统课", "purpose": "规模化交付"},
                {"level": "高价 1000+", "product": "1对1咨询/陪跑/企业服务", "purpose": "利润和案例"},
            ],
            "risk_note": "平台门槛和合规要求变化快，正式接商单或投放前以官方后台为准。",
        }


class PlatformRadar:
    # 扩展敏感词库（金融/健康/教育等高风险领域尤其注意）
    SENSITIVE_PATTERNS = ["最", "第一", "100%", "稳赚", "包过", "加微信", "私加", "绝对", "国家级", "万能", "根治", "零风险"]

    @staticmethod
    def detect_violation_risk(text: str) -> Dict[str, Any]:
        hits = [word for word in PlatformRadar.SENSITIVE_PATTERNS if word in text]
        if len(hits) >= 3:
            level = "高"
        elif hits:
            level = "中"
        else:
            level = "低"
        suggestion = (
            "替换绝对化承诺，站外引流改为平台允许的表达。" if hits
            else "未发现明显高风险词，仍需按平台规则复核。"
        )
        return {"risk_level": level, "hits": hits, "suggestion": suggestion}


class CompetitorAnalyzer:
    """竞品对标：基于用户提供的对标信息做结构化差距分析。"""

    @staticmethod
    def analyze(rival_info: Dict[str, Any]) -> Dict[str, Any]:
        field = rival_info.get("field", "")
        strengths = rival_info.get("strengths", [])
        gaps = rival_info.get("gaps", [])
        learn = rival_info.get("learn", [])
        return {
            "field": field,
            "strengths": strengths,
            "gaps": gaps,
            "learn": learn,
            "note": "对标信息由用户提供或联网检索后人工核对，不调用任何平台 API。",
        }


class TitleGenerator:
    """按平台风格生成标题/Hook 候选（模板见 references/title-hook-library.md）。"""

    STYLE_TEMPLATES = {
        "B站": ["{t}：从入门到实战", "{t}保姆级教程", "用{t}解决一个真实问题"],
        "知乎": ["如何系统掌握{t}？", "{t}到底值不值得做？", "关于{t}，这是我见过最清晰的回答"],
        "公众号": ["{t}：一人实战手册", "{t}，普通人也能复制", "我把{t}做成了可复用流程"],
        "小红书": ["{t}｜可直接照做", "{t}保姆级攻略📌", "别再踩坑！{t}正确姿势"],
        "视频号": ["1分钟看懂：{t}", "{t}，原来还能这样", "一个视频讲清{t}"],
        "抖音": ["别再低效了，{t}这样做", "{t}的3个真相", "90%的人都不知道{t}"],
        "微博": ["{t}的3个关键点", "关于{t}的一点看法", "{t}避坑指南"],
        "快手": ["老铁都在看的{t}", "{t}实在教程", "一个视频讲清{t}"],
        "今日头条": ["{t}：一文说清", "{t}到底怎么回事", "关于{t}，事实是这样的"],
        "西瓜视频": ["{t}：中视频详解", "{t}完整演示", "用{t}解决一个真实问题"],
        "百家号": ["{t}：百度也能搜到的答案", "{t}干货合集", "关于{t}的权威说法"],
        "豆瓣": ["关于{t}，一些不吐不快的话", "{t}：一份私人清单", "{t}到底好在哪"],
    }

    @staticmethod
    def generate(title: str, platforms: List[str]) -> List[Dict[str, Any]]:
        out = []
        for p in platforms:
            templates = TitleGenerator.STYLE_TEMPLATES.get(p, ["{t}"])
            out.append({"platform": p, "titles": [tpl.format(t=title) for tpl in templates]})
        return out


class GoalTracker:
    """目标追踪：对比历史与本周数据，判断是否跑在「达成目标」的节奏上。

    输入任意两期数据（上期 vs 本期，或首期 vs 当前），给出趋势与目标达成进度。
    不依赖 API，全部来自用户提供的 CSV 或手动输入。
    """

    # 常见目标类型 → 用来衡量进度的核心指标
    GOAL_METRIC = {
        "涨粉": "粉丝增长",
        "播放": "播放量",
        "互动": "互动率",
        "转化": "涨粉率",
    }

    @staticmethod
    def pace_analysis(
        goal: str,
        target_value: float,
        days_total: int,
        days_elapsed: int,
        previous_total: float,
        current_total: float,
    ) -> Dict[str, Any]:
        if days_total <= 0 or days_elapsed < 0:
            return {"error": "天数参数不合法"}
        if days_elapsed == 0:
            per_day_needed = target_value / days_total if days_total else 0
            return {
                "goal": goal,
                "target": target_value,
                "elapsed": 0,
                "total": days_total,
                "progress_value": current_total,
                "gained": current_total - previous_total,
                "pace": "未开始",
                "per_day_needed": round(per_day_needed, 2),
                "on_track": None,
                "advice": "还没到统计节点，先按排期执行，别急着看数。",
            }

        gained = current_total - previous_total
        remaining = max(0.0, target_value - gained)
        days_left = max(0, days_total - days_elapsed)
        per_day_needed = (remaining / days_left) if days_left > 0 else float("inf")
        actual_per_day = gained / days_elapsed

        # 进度节奏：以「当前日均所需」是否小于等于「实际日均」判断
        on_track = (per_day_needed <= actual_per_day) if days_left > 0 else (gained >= target_value)
        pace = "达标中" if on_track else "偏慢"
        if days_left == 0:
            pace = "已到期"

        advice = (
            "节奏正常，保持当前打法即可。"
            if on_track
            else f"进度偏慢：剩余 {days_left} 天需日均 {per_day_needed:.1f}（当前日均 {actual_per_day:.1f}）。"
                 f"建议：把更多精力压到主平台、或把本周核心选题换成更高潜力选题。"
        )
        return {
            "goal": goal,
            "target": target_value,
            "elapsed": days_elapsed,
            "total": days_total,
            "progress_value": round(current_total, 2),
            "gained": round(gained, 2),
            "remaining": round(remaining, 2),
            "days_left": days_left,
            "per_day_needed": round(per_day_needed, 2) if days_left > 0 else None,
            "actual_per_day": round(actual_per_day, 2),
            "pace": pace,
            "on_track": on_track,
            "advice": advice,
        }


class ContentBank:
    """常青内容库：按「支柱主题 × 内容形式」给可持续复用的选题骨架，缓解选题枯竭。"""

    # 每个领域 3-4 个支柱主题，可长期围绕它们做系列化内容
    PILLARS: Dict[str, List[str]] = {
        "编程技术": ["效率工具实操", "踩坑与排错", "从0到1做项目", "行业认知/AI 趋势"],
        "知识付费": ["方法论", "案例拆解", "学员/用户故事", "认知升级"],
        "职场效率": ["工具对比", "每日习惯", "沟通/协作", "副业探索"],
        "美妆护肤": ["新手教程", "成分科普", "好物平价替代", "误区避坑"],
        "本地生活": ["探店", "同城玩法", "商家访谈", "避坑指南"],
        "实体电商": ["产品故事", "使用场景", "买家秀", "行业干货"],
        "金融财经": ["资产配置", "基金/股票科普", "记账理财", "风险认知"],
        "教育培训": ["备考方法", "知识点精讲", "家长课堂", "学习资源"],
        "健康健身": ["居家训练", "饮食搭配", "误区避坑", "打卡陪伴"],
        "游戏娱乐": ["新手攻略", "版本解读", "趣味集锦", "观点吐槽"],
        "设计创意": ["排版/配色法则", "案例赏析", "工具教程", "灵感收集"],
        "美食探店": ["探店实录", "菜谱教程", "避坑指南", "食材/好物"],
        "旅游出行": ["攻略模板", "小众玩法", "拍照技巧", "预算/避坑"],
        "母婴育儿": ["待产/好物清单", "早教误区", "睡眠/喂养", "亲子沟通"],
        "宠物萌宠": ["新手养宠", "行为训练", "健康避坑", "好物测评"],
        "家居装修": ["小户型技巧", "预算控制", "避坑指南", "软装灵感"],
        "科技数码": ["选购指南", "开箱测评", "玩法教程", "行业趋势"],
        "情感心理": ["内耗自救", "关系沟通", "情绪管理", "自我成长"],
        "文史知识": ["历史冷知识", "书影音解读", "人物故事", "文化常识"],
        "三农乡村": ["农货带货", "乡村生活", "自建房/种植", "返乡故事"],
        "法律普法": ["必备法条", "合同陷阱", "维权指南", "案例分析"],
    }

    # 可套用的内容形式骨架
    FORMAT_SKELETONS = [
        "清单体：N 个 xxx 你一定要知道",
        "对比体：A vs B，到底怎么选",
        "避坑体：做 xxx 最常见的 3 个错误",
        "案例体：我是怎么用 xxx 解决 xxx 的",
        "问答体：关于 xxx，高频问题一次说清",
        "复盘体：一个月做 xxx，我学到的 5 件事",
    ]

    @staticmethod
    def suggest(field: str, count: int = 6) -> List[Dict[str, Any]]:
        pillars = ContentBank.PILLARS.get(field, ContentBank.PILLARS.get("知识付费"))
        out = []
        i = 0
        while len(out) < count:
            pillar = pillars[i % len(pillars)]
            skeleton = ContentBank.FORMAT_SKELETONS[i % len(ContentBank.FORMAT_SKELETONS)]
            out.append({"pillar": pillar, "skeleton": skeleton})
            i += 1
        return out


class WeeklyPlanOperator:
    @staticmethod
    def generate_weekly_plan(
        profile: FounderProfile,
        core_content: CoreContent,
        metrics_csv: Optional[str] = None,
        rival_info: Optional[Dict[str, Any]] = None,
        check_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        platform_plan = MatrixPlanner.recommend_platforms(profile)
        primary_names = [p["platform"] for p in platform_plan["primary"]]
        secondary_names = [p["platform"] for p in platform_plan["secondary"]]
        targets = primary_names + secondary_names
        content_versions = ContentKitchen.dismantle_content(core_content, targets)
        calendar = TopicScheduler.generate_calendar(primary_names, secondary_names, core_content.title, profile.weekly_hours)
        topics = TopicScheduler.mine_topics(profile.field)[:5]
        monetization = MonetizationPlanner.match_monetization_model(profile)
        metrics_review = AnalyticsBoard.cross_platform_compare(AnalyticsBoard.import_from_csv(metrics_csv)) if metrics_csv else None
        competitor = CompetitorAnalyzer.analyze(rival_info) if rival_info else None
        compliance = PlatformRadar.detect_violation_risk(check_text) if check_text else None
        titles = TitleGenerator.generate(core_content.title, targets)
        content_bank = ContentBank.suggest(profile.field, count=6)

        return {
            "version": VERSION,
            "profile": asdict(profile),
            "core_content": asdict(core_content),
            "operating_judgement": {
                "weekly_goal": profile.goal,
                "primary_platforms": primary_names,
                "secondary_platforms": secondary_names,
                "paused_platforms": platform_plan["pause"],
                "reason": platform_plan["reason"],
                "time_budget": platform_plan["time_budget"],
            },
            "topic_candidates": topics,
            "content_versions": content_versions,
            "titles": titles,
            "calendar": calendar,
            "metrics_review": metrics_review,
            "competitor": competitor,
            "compliance": compliance,
            "monetization": monetization,
            "content_bank": content_bank,
            "today_actions": [
                f"确认本周唯一核心选题：《{core_content.title}》。",
                f"用 {primary_names[0] if primary_names else '主平台'} 的长内容作为母内容，不为每个平台单独重写。",
                "准备一个免费资料包或清单，在评论/私信/公众号中承接需求。",
            ],
            "do_not_do": [
                "本周不新增超过计划外的平台。",
                "不做全平台日更。",
                "不同时测试标题、封面、时长、转化入口四个变量。",
            ],
        }

    @staticmethod
    def to_markdown(plan: Dict[str, Any]) -> str:
        judgement = plan["operating_judgement"]
        lines = [
            f"# 全平台内容矩阵 V{plan['version']} 周作战计划",
            "",
            "## 经营判断",
            f"- 本周目标: {judgement['weekly_goal']}",
            f"- 主平台: {', '.join(judgement['primary_platforms'])}",
            f"- 辅助平台: {', '.join(judgement['secondary_platforms']) or '无'}",
            f"- 暂缓平台: {', '.join(judgement['paused_platforms']) or '无'}",
            f"- 核心选题: {plan['core_content']['title']}",
            f"- 时间预算: {plan['profile']['weekly_hours']}小时/周",
            f"- 判断依据: {judgement['reason']}",
            "",
            "## 一源多发拆解",
            "| 平台 | 内容形态 | 标题/Hook | 交付物 | 耗时 | 目标 |",
            "|---|---|---|---|---:|---|",
        ]
        for item in plan["content_versions"]:
            lines.append(
                f"| {item['platform']} | {item['content_form']} | {item['title']} / {item['hook']} | "
                f"{item['deliverable']} | {item['production_minutes']}分钟 | {item['publish_goal']} |"
            )
        # 每个平台的「内容简报」：封面 + 大纲 + CTA，省去另查
        for item in plan["content_versions"]:
            lines.extend([
                "",
                f"### {item['platform']} 内容简报",
                f"- 封面思路：{item.get('cover_idea', '—')}",
                f"- 结构大纲：{item.get('outline', '—')}",
                f"- 行动号召(CTA)：{item.get('cta', '—')}",
                f"- 黄金时段：{item.get('prime_time', '—')}",
            ])

        lines.extend([
            "",
            "## 标题候选（按平台风格）",
        ])
        for item in plan.get("titles", []):
            for t in item["titles"]:
                lines.append(f"- {item['platform']}：{t}")

        lines.extend([
            "",
            "## 常青内容库（可持续做的选题骨架）",
            "> 围绕支柱主题做系列化，缓解选题枯竭。每周从这里挑 1-2 个填充排期。",
        ])
        for item in plan.get("content_bank", []):
            lines.append(f"- 支柱【{item['pillar']}】→ {item['skeleton']}")

        lines.extend([
            "",
            "## 7天排期",
            "| 日期 | 任务 | 平台 | 产出 | 耗时 | 指标 |",
            "|---|---|---|---|---:|---|",
        ])
        for item in plan["calendar"]:
            lines.append(f"| {item['day']} | {item['task']} | {item['platform']} | {item['output']} | {item['hours']}h | {item['metric']} |")

        lines.extend([
            "",
            "## 选题候选",
            "| 选题 | 分数 | 判断 |",
            "|---|---:|---|",
        ])
        for item in plan["topic_candidates"]:
            lines.append(f"| {item['title']} | {item['score']} | {item['level']} |")

        if plan.get("metrics_review"):
            mr = plan["metrics_review"]
            lines.extend([
                "",
                "## 数据复盘",
                f"- 结论: {mr['summary']}",
                "| 平台 | 播放/阅读 | 互动率 | 完播率 | 涨粉 | 判断 |",
                "|---|---:|---:|---:|---:|---|",
            ])
            for item in mr["platforms"]:
                lines.append(
                    f"| {item['平台']} | {item['播放量']} | {item['互动率']:.1%} | "
                    f"{item['完播率']:.1%} | {item['涨粉']} | {item['判断']} |"
                )
            for insight in mr["insights"]:
                lines.append(f"- {insight}")

        if plan.get("competitor"):
            c = plan["competitor"]
            lines.extend([
                "",
                "## 竞品对标",
                f"- 对标/赛道: {c.get('field', '—')}",
                f"- 对方强在哪: {', '.join(c.get('strengths', [])) or '—'}",
                f"- 你差在哪: {', '.join(c.get('gaps', [])) or '—'}",
                f"- 可抄作业: {', '.join(c.get('learn', [])) or '—'}",
            ])

        if plan.get("compliance"):
            comp = plan["compliance"]
            lines.extend([
                "",
                "## 合规检查",
                f"- 风险等级: {comp['risk_level']}",
                f"- 命中词: {', '.join(comp['hits']) or '无'}",
                f"- 建议: {comp['suggestion']}",
            ])

        monetization = plan["monetization"]
        lines.extend([
            "",
            "## 变现动作",
            f"- 阶段: {monetization['stage']}",
            f"- 本周验证: {monetization['this_week_action']}",
            "| 层级 | 产品 | 目的 |",
            "|---|---|---|",
        ])
        for item in monetization["product_ladder"]:
            lines.append(f"| {item['level']} | {item['product']} | {item['purpose']} |")

        lines.extend(["", "## 今日动作"])
        for index, action in enumerate(plan["today_actions"], 1):
            lines.append(f"{index}. {action}")

        lines.extend(["", "## 不做清单"])
        for action in plan["do_not_do"]:
            lines.append(f"- {action}")

        return "\n".join(lines)


def platform_from_name(name: str) -> Optional[Platform]:
    for platform in Platform:
        if platform.value == name:
            return platform
    return None


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def demo_profile() -> FounderProfile:
    return FounderProfile(
        field="编程技术",
        offer="Python自动化办公小册和模板包",
        target_customer="想用AI和Python提升办公效率的职场人",
        weekly_hours=10,
        goal="30天内涨粉并验证知识付费",
        existing_platforms={"B站": 3000, "知乎": 1200, "小红书": 500},
    )


def demo_content() -> CoreContent:
    return CoreContent(
        title="Python自动化办公完全指南",
        format="长文",
        summary="用Python处理Excel报表、自动生成PPT、批量处理邮件，让职场人减少重复劳动。",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Omni Content Matrix demo")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--with-metrics", action="store_true", help="include sample CSV metrics review")
    args = parser.parse_args()

    metrics = CSV_TEMPLATE if args.with_metrics else None
    plan = WeeklyPlanOperator.generate_weekly_plan(demo_profile(), demo_content(), metrics)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(WeeklyPlanOperator.to_markdown(plan))


if __name__ == "__main__":
    main()
