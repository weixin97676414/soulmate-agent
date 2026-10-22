

















from __future__ import annotations

import logging
import re

from ..config.schemas import ModelSpec

logger = logging.getLogger(__name__)


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
    
    
    
    score += min(hits, 3) * 2

    if _CODE_FENCE.search(text or ""):
        score += 1
    
    if need_tools:
        score += 2
    
    if has_images:
        score += 1

    if any(hint in lowered for hint in _LIGHT_HINTS):
        score -= 2

    return max(0, min(score, 10))


def pick_tier(score: int) -> str:

    if score <= 2:
        return "cheap"
    if score >= 6:
        return "strong"
    return "standard"


class ModelRouter:


    def __init__(
        self,
        *,
        default_id: str,
        candidates: list[ModelSpec],
        enabled: bool = True,
    ) -> None:
        self._default_id = default_id
        self._enabled = enabled
        
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
