


















from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..llm.usage import PriceSpec, Usage, estimate_cost
from ..observability.metrics import METRICS
from ..storage.usage import UsageRecord

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  
    
    from ..server.runtime import AppRuntime


class UsageService:






    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime

    @property
    def available(self) -> bool:

        return bool(self._runtime.db_ready)

    def prices_configured(self) -> bool:





        return any(
            model.price_input_per_1m is not None and model.price_output_per_1m is not None
            for model in self._runtime.config.models.models
        )

    async def summary(self, days: int) -> dict[str, Any]:

        usage_settings = self._runtime.config.settings.usage
        base: dict[str, Any] = {
            "currency": usage_settings.currency,
            "daily_budget": usage_settings.daily_budget,
            "prices_configured": self.prices_configured(),
            "window_days": days,
        }

        if not self.available:
            
            return {
                **base,
                "available": False,
                "message": "数据库不可用，用量统计暂时无法读取。",
                "today": None,
                "total": None,
                "window": None,
                "by_model": [],
                "by_day": [],
            }

        cutoff = time.time() - days * 86400
        repo = self._runtime.usage_repo
        return {
            **base,
            "available": True,
            "today": await repo.today(),
            "total": await repo.totals(),
            "window": await repo.totals(since=cutoff),
            "by_model": await repo.by_model(since=cutoff),
            "by_day": await repo.by_day(days=days),
        }

    async def session(self, session_id: str) -> dict[str, Any]:

        if not self.available:
            return {"available": False}
        return {"available": True, **await self._runtime.usage_repo.by_session(session_id)}

    async def clear(self) -> int:

        if not self.available:
            return 0
        return await self._runtime.usage_repo.clear()

    
    
    
    def price_of(self, model_id: str) -> PriceSpec:





        spec = self._runtime.config.models.get(model_id)
        if spec is None:
            return PriceSpec()

        in_peak = any(window.contains(datetime.now()) for window in spec.peak_windows)
        if in_peak:
            return PriceSpec(
                input=(
                    spec.price_input_per_1m_peak
                    if spec.price_input_per_1m_peak is not None
                    else spec.price_input_per_1m
                ),
                cached_input=(
                    spec.price_cached_input_per_1m_peak
                    if spec.price_cached_input_per_1m_peak is not None
                    else spec.price_cached_input_per_1m
                ),
                output=(
                    spec.price_output_per_1m_peak
                    if spec.price_output_per_1m_peak is not None
                    else spec.price_output_per_1m
                ),
            )
        return PriceSpec(
            input=spec.price_input_per_1m,
            cached_input=spec.price_cached_input_per_1m,
            output=spec.price_output_per_1m,
        )

    async def record(
        self,
        *,
        session_id: str | None,
        model_id: str,
        usage: Usage,
        trace_id: str | None = None,
        duration_ms: float | None = None,
        iterations: int = 0,
    ) -> None:





        spec = self._runtime.config.models.get(model_id)
        cost = estimate_cost(usage, self.price_of(model_id))

        
        
        
        
        METRICS.inc("llm_calls_total", model=model_id)
        METRICS.inc("llm_prompt_tokens_total", float(usage.prompt_tokens), model=model_id)
        METRICS.inc("llm_completion_tokens_total", float(usage.completion_tokens), model=model_id)
        
        METRICS.inc("llm_cached_tokens_total", float(usage.cached_tokens), model=model_id)
        if cost is not None and cost > 0:
            METRICS.inc("llm_cost_total", float(cost), model=model_id)
        if duration_ms:
            METRICS.observe("turn_duration_ms", duration_ms, model=model_id)

        if not self.available:
            return
        try:
            await self._runtime.usage_repo.record(
                UsageRecord(
                    session_id=session_id,
                    trace_id=trace_id,
                    model_id=model_id,
                    provider=spec.provider if spec else "",
                    usage=usage,
                    cost=cost,
                    currency=self._runtime.config.settings.usage.currency,
                    duration_ms=duration_ms,
                    iterations=iterations,
                )
            )
        except Exception:  
            logger.exception("用量落库失败 session=%s model=%s", session_id, model_id)
