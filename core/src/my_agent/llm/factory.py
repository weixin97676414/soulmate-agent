"""配置驱动的适配器工厂。

把 ``models.json`` 里的声明转换成可用的 ``BaseLLM`` 实例集合。
新增厂商只要有 OpenAI 兼容端点，就无需写任何代码，只加一条配置。
"""

from __future__ import annotations

import logging

from ..config.schemas import ModelsConfig, ModelSpec
from ..errors import ConfigError
from .adapters.anthropic import AnthropicAdapter
from .adapters.openai_compat import OpenAICompatAdapter
from .base import BaseLLM
from .fallback import FallbackListener, FallbackLLM
from .registry import LlmRegistry

logger = logging.getLogger(__name__)


def build_llm(spec: ModelSpec) -> BaseLLM:
    """按 spec 构建单个适配器。"""
    if spec.adapter in ("openai_compat", "ollama"):
        if not spec.base_url:
            raise ConfigError(f"模型 {spec.id} 缺少 base_url，无法建立连接。")
        if spec.adapter == "openai_compat" and not spec.api_key:
            # 本地端点（如 LM Studio）可能不需要 Key，但云端缺失一定报错更友好
            logger.warning("模型 %s 未配置 API Key，请求可能被厂商拒绝。", spec.id)
        return OpenAICompatAdapter(
            base_url=spec.base_url,
            api_key=spec.api_key,
            model_name=spec.model_name,
            timeout=spec.timeout,
            supports_tools=spec.supports_tools,
            supports_stream=spec.supports_stream,
            supports_reasoning=spec.supports_reasoning,
            token_limit=spec.token_limit,
            use_system_proxy=spec.use_system_proxy,
        )

    if spec.adapter == "anthropic":
        # 走原生协议而不是 OpenAI 兼容网关。差别不只是格式：
        # 兼容网关通常**不转发 cache_control**，于是 Anthropic 的显式
        # prompt caching 完全用不上，输入价格差一个数量级。
        if not spec.api_key:
            logger.warning("模型 %s 未配置 API Key，请求会被 Anthropic 拒绝。", spec.id)
        return AnthropicAdapter(
            base_url=spec.base_url or "https://api.anthropic.com",
            api_key=spec.api_key,
            model_name=spec.model_name,
            timeout=spec.timeout,
            supports_tools=spec.supports_tools,
            supports_stream=spec.supports_stream,
            supports_reasoning=spec.supports_reasoning,
            token_limit=spec.token_limit,
            use_system_proxy=spec.use_system_proxy,
        )

    raise ConfigError(f"暂不支持的适配器类型: {spec.adapter}（模型 {spec.id}）")


def resolve_utility_llm(registry: LlmRegistry, model_id: str, fallback: BaseLLM) -> BaseLLM:
    """挑出"压缩 / 规划 / 自检"这些辅助调用要用的模型。

    用户在这些地方并不需要一个更强的模型 —— 它们产出的都是**中间结果**
    （摘要、计划、自检意见）。所以给一个可选的模型 id，默认留空跟随会话模型。

    三种情况都退回 ``fallback``，**不抛错**：
      - 没配（空串）—— 这就是默认行为；
      - 配了一个已被删除 / 停用的模型 —— 用户改了模型清单却没改这里，
        属于最常见的失配；此时多花一次主模型的钱，远好过整轮报错；
      - 注册表里恰好没有它（比如全部模型都被停用）。

    唯一需要说明的是"悄悄退回"这件事：所以每次退回都记一条 warning，
    排查"怎么账单比预期高"时能一眼看到。
    """
    if model_id and registry.has(model_id):
        return registry.get(model_id)
    if model_id:
        logger.warning(
            "设置的「压缩 / 规划 / 自检模型」%s 不存在或已停用，本次改回跟随当前会话模型。",
            model_id,
        )
    return fallback


def build_registry(
    config: ModelsConfig,
    *,
    on_fallback: FallbackListener | None = None,
) -> LlmRegistry:
    """构建完整注册表，跳过 ``enabled=False`` 的模型。

    ``on_fallback`` 用来把"主模型挂了、已切到备用"这件事透出去。没有它的话，
    用户在完全不知情的情况下用着另一个模型 —— 输出风格、能力甚至计费方
    都变了，而界面上看不出任何区别。
    """
    registry = LlmRegistry()
    enabled = [m for m in config.models if m.enabled]
    if not enabled:
        # **空清单不再是致命错误**：新装用户的清单本来就是空的，启动必须成功，
        # 引导页自己就要调模型接口。发消息时 LlmRegistry.get 会给出
        # "未知模型(默认)，请在设置中检查模型配置" 的引导性错误 ——
        # 那才是这个提示该出现的位置。
        logger.warning("没有任何已启用的模型；应用将以「未配置模型」状态启动。")
        return registry

    default_id = config.default_model or enabled[0].id

    # 第一遍：先把每个可用模型都建成实例。
    # 必须**全建完**再配降级链 —— A 的备用完全可能是配置里排在它**后面**的 B，
    # 边建边配会因为 B 还没实例化而把这条链悄悄丢掉。
    instances: dict[str, BaseLLM] = {}
    for spec in enabled:
        try:
            instances[spec.id] = build_llm(spec)
        except ConfigError as exc:
            # 单个模型配置错误不应导致整个应用起不来
            logger.error("跳过模型 %s: %s", spec.id, exc)

    if not instances:
        raise ConfigError("所有模型配置均无效，请检查设置。")

    # 第二遍：按 fallback_models 给模型套一层降级链
    for spec in enabled:
        llm = instances.get(spec.id)
        if llm is None:
            continue

        chain: list[str] = []
        for candidate in spec.fallback_models:
            # 去掉自身引用（否则失败时会原样重试一遍）、不存在的 id、以及重复项。
            # 顺序必须保留 —— 它就是优先级。
            if candidate == spec.id or candidate not in instances or candidate in chain:
                continue
            chain.append(candidate)
        if len(chain) != len(spec.fallback_models):
            logger.warning(
                "模型 %s 的备用链有无效项，实际生效: %s", spec.id, chain or "（无）"
            )

        if chain:
            # 刻意传**未被包装**的实例进去：见 FallbackLLM 模块说明，
            # 这是防止 A→B→A 无限循环的关键
            llm = FallbackLLM(
                llm,
                [instances[c] for c in chain],
                primary_id=spec.id,
                fallback_ids=chain,
                listener=on_fallback,
            )
            logger.info("模型 %s 已启用故障降级：%s", spec.id, " -> ".join(chain))

        registry.register(spec.id, llm, is_default=spec.id == default_id)

    # 若配置的默认模型恰好构建失败，LlmRegistry 已自动回退到首个成功注册的模型
    if not registry.has(default_id):
        logger.warning("默认模型 %s 不可用，已回退到 %s", default_id, registry.default_id)
    logger.info("已加载 %s 个模型，默认: %s", len(registry), registry.default_id)
    return registry
