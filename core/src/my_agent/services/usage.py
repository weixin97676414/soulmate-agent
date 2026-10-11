"""用量与计费（审计 L-01 抽出的第一个窄服务）。

## 搬的是什么

原先这些逻辑住在 `server/routes/usage.py` 里：取数（`usage_repo` 的五个方法）、
"数据库没连上就明说没数据"的分支、以及"用户到底填没填单价"的判定。
它们既不是 HTTP 的事、也不是仓库的事 —— 只有路由文件可待，
于是 H-06 那类"领域逻辑长在路由里"的问题又出现一次。

## 三个刻意的口径（原样保留，别在重构里弄丢）

1. ``prices_configured`` 明确告诉界面"用户填没填单价"：没填时费用是 NULL，
   界面显示「未配置价格」而不是 ``¥0.00`` —— 把"不知道"显示成"免费"最容易误导人。
2. ``available=False`` 只在数据库不可用时返回，且**不返回一堆 0**，
   否则用户会以为"这个月没花过钱"。
3. 缓存命中率一并返回。它不只是个好看的指标：
   **它是验证前缀缓存优化是否生效的唯一手段**（见 ``agent/prompts.py``）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..llm.usage import PriceSpec, Usage, estimate_cost
from ..observability.metrics import METRICS
from ..storage.usage import UsageRecord

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    # ⚠️ 只为类型注解：运行时导入会成环（runtime → services → runtime）
    from ..server.runtime import AppRuntime


class UsageService:
    """用量与费用的**读写**接口。

    写入（`record` / `price_of`）第 101 批从 runtime 搬进来，调用点第 102 批全部切过来，
    **runtime 上那两个转发方法已删除** ⇒ chat / scheduler / groups 都直接调这里。
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime

    @property
    def available(self) -> bool:
        """数据库连接好了没有。没连上时接口要**明说没数据**，不能给一堆 0。"""
        return bool(self._runtime.db_ready)

    def prices_configured(self) -> bool:
        """是否至少有一个模型同时填了输入价与输出价。

        只填一半也算没配：算不出完整费用时后端会返回 ``None``，
        界面据此显示「未配置价格」，保持一致。
        """
        return any(
            model.price_input_per_1m is not None and model.price_output_per_1m is not None
            for model in self._runtime.config.models.models
        )

    async def summary(self, days: int) -> dict[str, Any]:
        """总览：今天 / 累计 / 窗口内 / 按模型 / 按天。（逐字搬自原路由体）"""
        usage_settings = self._runtime.config.settings.usage
        base: dict[str, Any] = {
            "currency": usage_settings.currency,
            "daily_budget": usage_settings.daily_budget,
            "prices_configured": self.prices_configured(),
            "window_days": days,
        }

        if not self.available:
            # 明确说"没有数据"，而不是给一堆 0 让用户以为真的没花过钱
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
        """单个会话的累计用量（Trace 抽屉 / 会话详情用）。"""
        if not self.available:
            return {"available": False}
        return {"available": True, **await self._runtime.usage_repo.by_session(session_id)}

    async def clear(self) -> int:
        """清空用量流水，返回删除条数（只删统计，不动会话与消息）。"""
        if not self.available:
            return 0
        return await self._runtime.usage_repo.clear()

    # ------------------------------------------------------------------ #
    # 写入侧（原先长在 AppRuntime 上，第 101 批搬进来）
    # ------------------------------------------------------------------ #
    def price_of(self, model_id: str) -> PriceSpec:
        """取某个模型配置里的单价。没配就是全 None（费用会留空而不是算成 0）。

        配了高峰时段（``peak_windows``）且当前时间命中 → 用峰值价；
        峰值某一项没填就退回普通价（宁可少算不虚报）。
        """
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
        """记录一次对话的 token 用量与费用。

        落库失败**不影响对话**（用户已经拿到回复了），所以这里吞掉异常只记日志——
        统计不该成为主流程的故障点。
        """
        spec = self._runtime.config.models.get(model_id)
        cost = estimate_cost(usage, self.price_of(model_id))

        # 指标**先记**，且不受数据库可用性影响。
        # 内存模式（数据库初始化失败降级）下用户同样值得知道
        # "这一轮花了多少 token、耗时多久"，而指标本来就是进程内的、
        # 不需要持久化。
        METRICS.inc("llm_calls_total", model=model_id)
        METRICS.inc("llm_prompt_tokens_total", float(usage.prompt_tokens), model=model_id)
        METRICS.inc("llm_completion_tokens_total", float(usage.completion_tokens), model=model_id)
        # 缓存命中单独记：它就是前缀缓存优化是否生效的唯一直接证据
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
        except Exception:  # noqa: BLE001 - 统计失败不该打断对话
            logger.exception("用量落库失败 session=%s model=%s", session_id, model_id)
