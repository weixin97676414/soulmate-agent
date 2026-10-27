


























from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from ...errors import LLMAuthError, LLMError, LLMTimeoutError
from ...security.redact import redact
from ...utils.http import async_client
from ..base import (
    BaseLLM,
    LLMResponse,
    Message,
    StreamChunk,
    ToolCall,
    ToolSpec,
    load_arguments,
)

logger = logging.getLogger(__name__)

API_VERSION = "2023-06-01"


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}


DEFAULT_MAX_TOKENS = 4096

CACHE_CONTROL = {"type": "ephemeral"}






_THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}


_MIN_THINKING_BUDGET = 1024

_THINKING_HEADROOM = 1024


_STOP_REASON = {
    "tool_use": "tool_calls",
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
}


def is_loopback_url(url: str) -> bool:





    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


class AnthropicAdapter(BaseLLM):


    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout: float = 120.0,
        max_retries: int = 2,
        supports_tools: bool = True,
        supports_stream: bool = True,
        supports_reasoning: bool = True,
        supports_vision: bool = False,
        token_limit: int = 200_000,
        cache_enabled: bool = True,
        use_system_proxy: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            supports_tools=supports_tools,
            supports_stream=supports_stream,
            supports_reasoning=supports_reasoning,
            supports_vision=supports_vision,
            token_limit=token_limit,
        )
        
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        
        self.cache_enabled = cache_enabled

        loopback = is_loopback_url(self.base_url)
        
        self._client = async_client(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=15.0),
            
            
            trust_env=(not loopback) and use_system_proxy,
            transport=transport,
        )

    
    
    
    @staticmethod
    def _to_anthropic_messages(
        messages: list[Message],
    ) -> tuple[str | None, list[dict[str, Any]]]:

        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        
        
        pending_results: list[dict[str, Any]] = []

        def flush_results() -> None:
            if pending_results:
                out.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        def append(role: str, blocks: list[dict[str, Any]]) -> None:






            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)
                return
            out.append({"role": role, "content": blocks})

        for message in messages:
            if message.role == "system":
                if message.content.strip():
                    system_parts.append(message.content)
                continue

            if message.role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id or "",
                        "content": message.content or "",
                    }
                )
                continue

            flush_results()

            if message.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                for call in message.tool_calls or []:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments or {},
                        }
                    )
                if blocks:
                    append("assistant", blocks)
                continue

            append("user", [{"type": "text", "text": message.content}])

        flush_results()
        system = "\n\n".join(system_parts) if system_parts else None
        return system, out

    def _build_system(self, system: str | None) -> Any:

        if not system:
            return None
        if not self.cache_enabled:
            return system
        return [{"type": "text", "text": system, "cache_control": CACHE_CONTROL}]

    def _to_anthropic_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        converted = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]
        if self.cache_enabled and converted:
            
            
            converted[-1] = {**converted[-1], "cache_control": CACHE_CONTROL}
        return converted

    @staticmethod
    def _mark_history_breakpoint(messages: list[dict[str, Any]]) -> None:





        if not messages:
            return
        last = messages[-1]
        blocks = last.get("content")
        if not isinstance(blocks, list) or not blocks:
            return
        blocks[-1] = {**blocks[-1], "cache_control": CACHE_CONTROL}

    def _warn_unsupported_penalties(
        self, frequency_penalty: float | None, presence_penalty: float | None
    ) -> None:








        if frequency_penalty is not None or presence_penalty is not None:
            logger.debug(
                "Anthropic 原生协议不支持 frequency_penalty / presence_penalty，"
                "本次已忽略（top_p 仍然生效）"
            )

    def _thinking_param(self, effort: str | None, max_tokens: int) -> dict[str, Any] | None:










        if not effort or not self.supports_reasoning:
            return None
        desired = _THINKING_BUDGETS.get(effort)
        if desired is None:
            return None

        budget = min(desired, max_tokens - _THINKING_HEADROOM)
        if budget < _MIN_THINKING_BUDGET:
            logger.debug(
                "思考强度 %s 最少需要 %s token 预算，但 max_tokens 只有 %s，本次不启用扩展思考",
                effort,
                _MIN_THINKING_BUDGET,
                max_tokens,
            )
            return None
        return {"type": "enabled", "budget_tokens": budget}

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        temperature: float,
        max_tokens: int | None,
        *,
        stream: bool,
        top_p: float | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        system, converted = self._to_anthropic_messages(messages)
        if self.cache_enabled:
            self._mark_history_breakpoint(converted)

        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "messages": converted,
            "temperature": temperature,
        }
        
        if top_p is not None:
            payload["top_p"] = top_p

        thinking = self._thinking_param(reasoning_effort, int(payload["max_tokens"]))
        if thinking is not None:
            payload["thinking"] = thinking
            
            
            
            
            payload.pop("temperature", None)
        if stream:
            payload["stream"] = True
        system_param = self._build_system(system)
        if system_param is not None:
            payload["system"] = system_param
        if tools and self.supports_tools:
            payload["tools"] = self._to_anthropic_tools(tools)
        return payload

    
    
    
    @staticmethod
    def _parse_blocks(blocks: list[dict[str, Any]]) -> tuple[str, list[ToolCall], str]:

        texts: list[str] = []
        thinking: list[str] = []
        calls: list[ToolCall] = []
        for block in blocks or []:
            kind = block.get("type")
            if kind == "text":
                texts.append(str(block.get("text") or ""))
            elif kind == "thinking":
                thinking.append(str(block.get("thinking") or ""))
            elif kind == "tool_use":
                arguments = block.get("input")
                if not isinstance(arguments, dict):
                    arguments = {}
                calls.append(
                    ToolCall(
                        id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=arguments,
                        raw_arguments=json.dumps(arguments, ensure_ascii=False),
                    )
                )
        return "".join(texts), calls, "".join(thinking)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> LLMResponse:
        text, calls, thinking = AnthropicAdapter._parse_blocks(data.get("content") or [])
        stop_reason = str(data.get("stop_reason") or "")
        return LLMResponse(
            content=text,
            reasoning_content=thinking,
            tool_calls=calls,
            finish_reason=_STOP_REASON.get(stop_reason, stop_reason or "stop"),
            usage=data.get("usage") or {},
            raw=data,
        )

    
    
    
    @staticmethod
    def _raise_for_status(status: int, body: str) -> None:
        
        snippet = redact(body[:500])
        if status in (401, 403):
            raise LLMAuthError(f"Anthropic 鉴权失败（HTTP {status}），请检查 API Key。{snippet}")
        if status == 429:
            raise LLMError(f"触发 Anthropic 限流（HTTP 429），请稍后重试。{snippet}")
        if status == 529:
            raise LLMError(f"Anthropic 服务过载（HTTP 529），请稍后重试。{snippet}")
        raise LLMError(f"Anthropic 调用失败（HTTP {status}）。{snippet}")

    
    
    
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
        self._warn_unsupported_penalties(frequency_penalty, presence_penalty)
        payload = self._build_payload(
            messages,
            tools,
            temperature,
            max_tokens,
            stream=False,
            top_p=top_p,
            reasoning_effort=reasoning_effort,
        )
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.post("/v1/messages", json=payload)
            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError(f"Anthropic 调用超时（{self.timeout}s）")
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = LLMError(f"网络异常: {exc}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise last_error from exc

            if resp.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                logger.warning("Anthropic 返回 %s，第 %s 次重试", resp.status_code, attempt + 1)
                await asyncio.sleep(2**attempt)
                continue

            if resp.status_code >= 400:
                self._raise_for_status(resp.status_code, resp.text)

            return self._parse_response(resp.json())

        raise last_error or LLMError("Anthropic 调用失败：已达最大重试次数")

    
    
    
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
        self._warn_unsupported_penalties(frequency_penalty, presence_penalty)
        payload = self._build_payload(
            messages,
            tools,
            temperature,
            max_tokens,
            stream=True,
            top_p=top_p,
            reasoning_effort=reasoning_effort,
        )

        
        
        tool_buffers: dict[int, dict[str, Any]] = {}
        
        usage: dict[str, Any] = {}
        finish_reason = ""

        try:
            async with self._client.stream("POST", "/v1/messages", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    self._raise_for_status(resp.status_code, body)

                async for line in resp.aiter_lines():
                    
                    
                    
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug("跳过无法解析的流式分片: %s", raw[:200])
                        continue

                    kind = event.get("type")

                    if kind == "message_start":
                        
                        message = event.get("message") or {}
                        merged = message.get("usage")
                        if isinstance(merged, dict):
                            usage = {**usage, **merged}
                        continue

                    if kind == "message_delta":
                        delta = event.get("delta") or {}
                        if delta.get("stop_reason"):
                            finish_reason = str(delta["stop_reason"])
                        merged = event.get("usage")
                        if isinstance(merged, dict):
                            
                            
                            usage = {**usage, **merged}
                        continue

                    if kind == "content_block_start":
                        index = int(event.get("index") or 0)
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            tool_buffers[index] = {
                                "id": str(block.get("id") or ""),
                                "name": str(block.get("name") or ""),
                                "arguments": "",
                            }
                        continue

                    if kind == "content_block_delta":
                        index = int(event.get("index") or 0)
                        delta = event.get("delta") or {}
                        delta_type = delta.get("type")
                        if delta_type == "text_delta" and delta.get("text"):
                            yield StreamChunk(delta=str(delta["text"]))
                        elif delta_type == "thinking_delta" and delta.get("thinking"):
                            yield StreamChunk(reasoning_delta=str(delta["thinking"]))
                        elif delta_type == "input_json_delta":
                            buf = tool_buffers.setdefault(
                                index, {"id": "", "name": "", "arguments": ""}
                            )
                            buf["arguments"] += str(delta.get("partial_json") or "")
                        continue

        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Anthropic 流式调用超时（{self.timeout}s）") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Anthropic 流式调用网络异常: {exc}") from exc

        
        tool_calls: list[ToolCall] | None = None
        if tool_buffers:
            tool_calls = []
            for index in sorted(tool_buffers):
                buf = tool_buffers[index]
                if not buf["name"]:
                    continue
                tool_calls.append(
                    ToolCall(
                        id=buf["id"] or f"toolu_{index}",
                        name=buf["name"],
                        arguments=load_arguments(buf["arguments"]),
                        raw_arguments=buf["arguments"],
                    )
                )

        yield StreamChunk(
            tool_calls=tool_calls,
            usage=usage or None,
            finish_reason=_STOP_REASON.get(finish_reason, finish_reason or "stop"),
        )

    
    
    
    async def list_models(self) -> list[str]:

        try:
            resp = await self._client.get("/v1/models", timeout=httpx.Timeout(20.0, connect=10.0))
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接 Anthropic 端点 {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            self._raise_for_status(resp.status_code, resp.text)
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [str(i.get("id")) for i in items if isinstance(i, dict) and i.get("id")]

    async def aclose(self) -> None:
        await self._client.aclose()
