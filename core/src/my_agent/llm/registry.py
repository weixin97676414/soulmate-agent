





















from __future__ import annotations

import logging

from ..errors import LLMError
from .base import BaseLLM

logger = logging.getLogger(__name__)


class LlmLease:











    __slots__ = ("_registry", "_released")

    def __init__(self, registry: LlmRegistry) -> None:
        self._registry = registry
        self._released = False

    async def __aenter__(self) -> LlmLease:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._registry.release_lease()


class LlmRegistry:
    def __init__(self) -> None:
        self._models: dict[str, BaseLLM] = {}
        self._default: str = ""
        
        self._leases = 0
        
        self._retire_pending = False
        
        self._closed = False

    
    
    
    def register(self, model_id: str, llm: BaseLLM, *, is_default: bool = False) -> None:
        self._models[model_id] = llm
        
        
        
        llm.set_lease_factory(self.lease)
        if is_default or not self._default:
            self._default = model_id

    def get(self, model_id: str | None) -> BaseLLM:

        key = model_id or self._default
        if not key or key not in self._models:
            raise LLMError(f"未知模型: {model_id or '(默认)'}，请在设置中检查模型配置。")
        return self._models[key]

    def has(self, model_id: str) -> bool:
        return model_id in self._models

    def ids(self) -> list[str]:
        return list(self._models)

    def default(self) -> BaseLLM:
        return self.get(None)

    @property
    def default_id(self) -> str:
        return self._default

    def __len__(self) -> int:
        return len(self._models)

    
    
    
    def lease(self) -> LlmLease:

        self._leases += 1
        return LlmLease(self)

    async def release_lease(self) -> None:
        self._leases = max(0, self._leases - 1)
        if self._leases == 0 and self._retire_pending:
            logger.debug("最后一个在途请求已结束，回收旧模型注册表")
            await self._close_now()

    @property
    def active_leases(self) -> int:

        return self._leases

    
    
    
    async def retire(self) -> None:





        if self._leases == 0:
            await self._close_now()
            return
        self._retire_pending = True
        logger.info(
            "旧模型注册表仍有 %s 个在途请求，等它们结束后再回收（避免打断正在进行的回答）",
            self._leases,
        )

    async def _close_now(self) -> None:
        self._retire_pending = False
        if self._closed:
            return
        self._closed = True
        await self.aclose()

    async def aclose(self) -> None:
        for llm in self._models.values():
            try:
                await llm.aclose()
            except Exception as exc:  
                logger.warning("关闭模型适配器失败: %s", exc)
        self._models.clear()
        self._default = ""
