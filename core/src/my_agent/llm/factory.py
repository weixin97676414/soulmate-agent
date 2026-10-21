





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

    if spec.adapter in ("openai_compat", "ollama"):
        if not spec.base_url:
            raise ConfigError(f"模型 {spec.id} 缺少 base_url，无法建立连接。")
        if spec.adapter == "openai_compat" and not spec.api_key:
            
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






    registry = LlmRegistry()
    enabled = [m for m in config.models if m.enabled]
    if not enabled:
        
        
        
        
        logger.warning("没有任何已启用的模型；应用将以「未配置模型」状态启动。")
        return registry

    default_id = config.default_model or enabled[0].id

    
    
    
    instances: dict[str, BaseLLM] = {}
    for spec in enabled:
        try:
            instances[spec.id] = build_llm(spec)
        except ConfigError as exc:
            
            logger.error("跳过模型 %s: %s", spec.id, exc)

    if not instances:
        raise ConfigError("所有模型配置均无效，请检查设置。")

    
    for spec in enabled:
        llm = instances.get(spec.id)
        if llm is None:
            continue

        chain: list[str] = []
        for candidate in spec.fallback_models:
            
            
            if candidate == spec.id or candidate not in instances or candidate in chain:
                continue
            chain.append(candidate)
        if len(chain) != len(spec.fallback_models):
            logger.warning(
                "模型 %s 的备用链有无效项，实际生效: %s", spec.id, chain or "（无）"
            )

        if chain:
            
            
            llm = FallbackLLM(
                llm,
                [instances[c] for c in chain],
                primary_id=spec.id,
                fallback_ids=chain,
                listener=on_fallback,
            )
            logger.info("模型 %s 已启用故障降级：%s", spec.id, " -> ".join(chain))

        registry.register(spec.id, llm, is_default=spec.id == default_id)

    
    if not registry.has(default_id):
        logger.warning("默认模型 %s 不可用，已回退到 %s", default_id, registry.default_id)
    logger.info("已加载 %s 个模型，默认: %s", len(registry), registry.default_id)
    return registry
