
























from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Iterator

from ..errors import LLMAuthError, LLMError
from ..observability.request_context import current_session_id
from .base import BaseLLM, LLMResponse, Message, StreamChunk, ToolSpec

logger = logging.getLogger(__name__)


FallbackListener = Callable[[str, str, str], None]


class FallbackLLM(BaseLLM):





    def __init__(
        self,
        primary: BaseLLM,
        fallbacks: list[BaseLLM],
        *,
        primary_id: str,
        fallback_ids: list[str],
        listener: FallbackListener | None = None,
    ) -> None:
        if len(fallbacks) != len(fallback_ids):
            raise ValueError("fallbacks 与 fallback_ids 长度必须一致")
        super().__init__(
            model_name=primary.model_name,
            supports_tools=primary.supports_tools,
            supports_stream=primary.supports_stream,
            supports_vision=primary.supports_vision,
            token_limit=primary.token_limit,
        )
        self._primary = primary
        self._fallbacks = list(fallbacks)
        self._primary_id = primary_id
        self._fallback_ids = list(fallback_ids)
        
        
        self._listener = listener

    
    
    
    def _chain(self) -> Iterator[tuple[str, BaseLLM]]:

        yield self._primary_id, self._primary
        yield from zip(self._fallback_ids, self._fallbacks, strict=True)

    def describe_chain(self) -> list[str]:

        return list(self._fallback_ids)

    
    
    
    def _notify(self, failed_index: int, failed_id: str, error: BaseException) -> None:
        taken_over = (
            self._fallback_ids[failed_index]
            if failed_index < len(self._fallback_ids)
            else ""
        )
        reason = str(error)
        
        
        
        
        logger.warning(
            "模型 %s 调用失败，%s：%s（session=%s）",
            failed_id,
            f"已降级到 {taken_over}" if taken_over else "且已无备用模型可用",
            reason,
            current_session_id.get() or "-",
        )
        if self._listener is not None:
            
            with contextlib.suppress(Exception):
                self._listener(failed_id, taken_over, reason)

    
    
    
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        last_error: LLMError | None = None
        for index, (model_id, llm) in enumerate(self._chain()):
            try:
                return await llm.chat(
                    messages,
                    tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    reasoning_effort=reasoning_effort,
                )
            except LLMAuthError:
                
                raise
            except LLMError as exc:
                last_error = exc
                self._notify(index, model_id, exc)

        raise last_error or LLMError("模型调用失败：全部候选均不可用")

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        last_error: LLMError | None = None
        for index, (model_id, llm) in enumerate(self._chain()):
            produced = False
            try:
                async for chunk in llm.stream(
                    messages,
                    tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    
                    
                    
                    top_p=top_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    reasoning_effort=reasoning_effort,
                ):
                    produced = True
                    yield chunk
                return
            except LLMAuthError:
                raise
            except LLMError as exc:
                if produced:
                    
                    
                    raise
                last_error = exc
                self._notify(index, model_id, exc)

        raise last_error or LLMError("模型调用失败：全部候选均不可用")

    async def list_models(self) -> list[str]:

        return await self._primary.list_models()

    async def aclose(self) -> None:
        for _, llm in self._chain():
            close = getattr(llm, "aclose", None)
            if close is None:
                continue
            
            with contextlib.suppress(Exception):
                await close()
