"""ModelRouter：按任务复杂度挑选模型。

对应《智能体框架开发文档》4.7 节。目标只有一个：**把便宜模型用在便宜的事上**。

日常使用中大量请求是"改个错别字""把这句话翻一下""这个报错什么意思"——
用最强模型处理它们，成本可能是用便宜模型的 20 倍，而效果没有区别。
反过来，长链条的工具编排、多步推理交给便宜模型，失败重试的代价更大。

## 设计取舍

**复杂度用启发式判断，不额外调用模型。** 让模型来判断"这个任务难不难"，
本身就要花一次调用 —— 为了省钱先花钱，逻辑上说不通。
这里用长度、代码块、多步连接词、是否需要工具等**零成本信号**打分。

**没有可用档位时返回 None，由调用方回落到默认模型。** 路由是优化手段，
不是必需品：用户只配了一个模型时，它必须能正常工作。
"""

from __future__ import annotations

import logging
import re

from ..config.schemas import ModelSpec

logger = logging.getLogger(__name__)

# 多步 / 编排类表述。命中越多，任务越可能是"需要规划"而不是"一句话能答"。
_MULTI_STEP_HINTS = (
    "然后",
    "接着",
    "分别",
    "批量",
    "逐个",
    "对比",
    "总结成",
    "整理成",
    "帮我做",
    "生成一份",
    "写一份",
    "导出",
    "分析一下",
    "step by step",
    "分步骤",
)

# 明显的"低成本"诉求：短问答、翻译、改写、解释名词
_LIGHT_HINTS = (
    "翻译",
    "改写",
    "润色",
    "什么意思",
    "怎么读",
    "拼写",
    "多少",
    "换算",
    "translate",
    "rewrite",
)

_CODE_FENCE = re.compile(r"```")
_LONG_INPUT_CHARS = 1200
_SHORT_INPUT_CHARS = 120


def score_complexity(text: str, *, need_tools: bool, has_images: bool = False) -> int:
    """给任务复杂度打分（0~10）。

    这个分数只用于**档位选择**，不追求精确 —— 分错一档只是多花一点或少省一点钱，
    不会导致功能异常。所以宁可规则简单、可解释，也不要搞成黑盒。
    """
    score = 0
    length = len(text or "")

    if length > _LONG_INPUT_CHARS:
        score += 3
    elif length > _SHORT_INPUT_CHARS * 3:
        score += 2
    elif length > _SHORT_INPUT_CHARS:
        score += 1

    lowered = (text or "").lower()
    hits = sum(1 for hint in _MULTI_STEP_HINTS if hint in lowered)
    # 多步表述按**每条 2 分**计（上限 3 条）。原来按 1 分计的话，一句典型的多步
    # 请求（"整理成表格，再分别导出对比"）需要工具也只有 5 分，刚好卡在 standard ——
    # 而这类任务恰恰是最需要强模型的：链条长、每一步都可能跑偏
    score += min(hits, 3) * 2

    if _CODE_FENCE.search(text or ""):
        score += 1
    # 需要工具往往意味着"要操作真实文件/数据"，出错代价高于纯问答
    if need_tools:
        score += 2
    # 带图的任务通常不是一句话能打发的
    if has_images:
        score += 1

    if any(hint in lowered for hint in _LIGHT_HINTS):
        score -= 2

    return max(0, min(score, 10))


def pick_tier(score: int) -> str:
    """把分数映射到目标档位。"""
    if score <= 2:
        return "cheap"
    if score >= 6:
        return "strong"
    return "standard"


class ModelRouter:
    """在已配置的模型之间做选择。"""

    def __init__(
        self,
        *,
        default_id: str,
        candidates: list[ModelSpec],
        enabled: bool = True,
    ) -> None:
        self._default_id = default_id
        self._enabled = enabled
        # 只保留可用（enabled）的候选，并按档位分桶
        self._by_tier: dict[str, list[str]] = {}
        for spec in candidates:
            if not spec.enabled:
                continue
            self._by_tier.setdefault(spec.tier, []).append(spec.id)

    @property
    def enabled(self) -> bool:
        return self._enabled and len(self._by_tier) > 0

    def available_tiers(self) -> list[str]:
        return sorted(self._by_tier)

    def pick(
        self,
        *,
        text: str,
        need_tools: bool = False,
        has_images: bool = False,
        within: set[str] | None = None,
    ) -> str | None:
        """返回应当使用的模型 id；没有更合适的就返回 ``None``（调用方用默认模型）。

        ``within`` 是"这个会话允许用的模型集合"（助手可能限定过）。
        路由只能在允许的范围内挑，否则会把用户的助手限定悄悄绕过去。
        """
        if not self.enabled:
            return None

        allowed = {
            tier: [mid for mid in ids if within is None or mid in within]
            for tier, ids in self._by_tier.items()
        }
        allowed = {tier: ids for tier, ids in allowed.items() if ids}
        if not allowed:
            return None

        score = score_complexity(text, need_tools=need_tools, has_images=has_images)
        target = pick_tier(score)

        # 先找目标档位，找不到就退一档（strong 缺则用 standard，cheap 缺则用 standard）
        for tier in self._fallback_order(target):
            ids = allowed.get(tier)
            if ids:
                chosen = ids[0]
                if chosen != self._default_id:
                    logger.info(
                        "任务路由：复杂度 %s -> 档位 %s，选用 %s（默认 %s）",
                        score,
                        tier,
                        chosen,
                        self._default_id,
                    )
                return chosen
        return None

    @staticmethod
    def _fallback_order(target: str) -> tuple[str, ...]:
        if target == "cheap":
            return ("cheap", "standard", "strong")
        if target == "strong":
            return ("strong", "standard", "cheap")
        return ("standard", "cheap", "strong")
