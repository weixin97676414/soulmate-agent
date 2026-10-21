






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
from ..platform import (
    AdaptiveFallbacks,
    clamp,
    detect_profile,
    extract_unsupported_param,
    looks_like_error_payload,
)

logger = logging.getLogger(__name__)


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def is_loopback_url(url: str) -> bool:




    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


class OpenAICompatAdapter(BaseLLM):


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
        token_limit: int = 32768,
        use_system_proxy: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            supports_tools=supports_tools,
            supports_stream=supports_stream,
            supports_reasoning=supports_reasoning,
            token_limit=token_limit,
        )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        
        
        
        self.profile = detect_profile(self.base_url)
        self.fallbacks = AdaptiveFallbacks()
        
        
        
        
        
        
        
        
        
        
        
        loopback = is_loopback_url(self.base_url)
        
        
        
        
        
        self._client = async_client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=15.0),
            trust_env=(not loopback) and use_system_proxy,
            
            transport=transport,
        )

    
    
    
    @staticmethod
    def _to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "content": m.content,
                        "tool_call_id": m.tool_call_id or "",
                    }
                )
                continue
            content: Any = m.content
            if m.images:
                
                
                
                
                
                parts: list[dict[str, Any]] = []
                if m.content:
                    parts.append({"type": "text", "text": m.content})
                parts.extend(
                    {"type": "image_url", "image_url": {"url": part.data_url}}
                    for part in m.images
                    if part.data_url
                )
                
                
                content = parts or m.content

            
            
            item: dict[str, Any] = {"role": m.role, "content": content}
            if m.tool_calls:
                item["tool_calls"] = [tc.to_openai() for tc in m.tool_calls]  
                
                item["content"] = m.content or None
            out.append(item)
        return out

    @staticmethod
    def _to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        temperature: float,
        max_tokens: int | None,
        *,
        stream: bool,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._to_openai_messages(messages),
            "stream": stream,
        }

        
        
        
        clamped = clamp(temperature, self.profile.temperature_range)
        if clamped is not None and self.fallbacks.enabled("temperature"):
            payload["temperature"] = clamped

        
        
        
        
        
        
        
        if (
            top_p is not None
            and self.profile.temperature_range is not None
            and self.fallbacks.enabled("top_p")
        ):
            clamped_top_p = clamp(top_p, self.profile.top_p_range)
            if clamped_top_p is not None:
                payload["top_p"] = clamped_top_p

        
        
        if self.profile.supports_penalties:
            if frequency_penalty is not None and self.fallbacks.enabled("frequency_penalty"):
                payload["frequency_penalty"] = frequency_penalty
            if presence_penalty is not None and self.fallbacks.enabled("presence_penalty"):
                payload["presence_penalty"] = presence_penalty

        
        
        
        
        
        
        
        
        
        
        
        if reasoning_effort and self.supports_reasoning:
            for field_name, value in self.profile.thinking.payload_for(
                reasoning_effort
            ).items():
                if self.fallbacks.enabled(field_name):
                    payload[field_name] = value

        if tools and self.supports_tools and self.fallbacks.enabled("tools"):
            payload["tools"] = self._to_openai_tools(tools)

        if max_tokens and self.fallbacks.enabled("max_tokens"):
            
            
            payload[self.profile.max_tokens_field] = max_tokens

        if stream and self.profile.stream_usage and self.fallbacks.enabled("stream_options"):
            
            payload["stream_options"] = {"include_usage": True}

        return payload

    def _adapt_to_error(self, body: str) -> bool:






        param = extract_unsupported_param(body)
        return bool(param) and self.fallbacks.disable(param)

    
    
    
    @staticmethod
    def _parse_response(data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            return LLMResponse(raw=data, finish_reason="empty")
        choice = choices[0]
        msg = choice.get("message") or {}

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or ""
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or "",
                    name=fn.get("name") or "",
                    arguments=load_arguments(raw_args),
                    raw_arguments=raw_args,
                )
            )

        return LLMResponse(
            content=msg.get("content") or "",
            
            reasoning_content=msg.get("reasoning_content") or msg.get("reasoning") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason") or "",
            usage=data.get("usage") or {},
            raw=data,
        )

    
    
    
    @staticmethod
    def _raise_for_status(status: int, body: str) -> None:
        
        
        
        snippet = redact(body[:500])
        if status in (401, 403):
            raise LLMAuthError(f"模型鉴权失败（HTTP {status}），请检查 API Key。{snippet}")
        if status == 429:
            raise LLMError(f"触发厂商限流（HTTP 429），请稍后重试。{snippet}")
        raise LLMError(f"模型调用失败（HTTP {status}）。{snippet}")

    
    
    
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
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            
            payload = self._build_payload(
                messages,
                tools,
                temperature,
                max_tokens,
                stream=False,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                reasoning_effort=reasoning_effort,
            )
            try:
                resp = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError(f"模型调用超时（{self.timeout}s）")
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
                logger.warning(
                    "模型调用返回 %s，第 %s 次重试", resp.status_code, attempt + 1
                )
                await asyncio.sleep(2**attempt)
                continue

            if resp.status_code >= 400:
                
                
                
                if self._adapt_to_error(resp.text) and attempt < self.max_retries:
                    continue
                self._raise_for_status(resp.status_code, resp.text)

            data = resp.json()
            
            
            wrapped = looks_like_error_payload(data)
            if wrapped:
                raise LLMError(f"模型服务返回错误：{redact(str(wrapped))}")

            return self._parse_response(data)

        raise last_error or LLMError("模型调用失败：已达最大重试次数")

    
    
    
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
        
        
        
        
        
        for attempt in range(self.max_retries + 1):
            payload = self._build_payload(
                messages,
                tools,
                temperature,
                max_tokens,
                stream=True,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                reasoning_effort=reasoning_effort,
            )

            
            tool_buffers: dict[int, dict[str, Any]] = {}
            usage: dict[str, Any] = {}
            finish_reason = ""

            try:
                async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                    if resp.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                        logger.warning(
                            "模型流式调用返回 %s，第 %s 次重试", resp.status_code, attempt + 1
                        )
                        await asyncio.sleep(2**attempt)
                        continue

                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")
                        if self._adapt_to_error(body) and attempt < self.max_retries:
                            continue
                        self._raise_for_status(resp.status_code, body)

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            logger.debug("跳过无法解析的流式分片: %s", data[:200])
                            continue

                        
                        
                        
                        wrapped = looks_like_error_payload(event)
                        if wrapped:
                            raise LLMError(f"模型服务返回错误：{redact(str(wrapped))}")

                        if event.get("usage"):
                            usage = event["usage"]

                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]

                        delta = choice.get("delta") or {}
                        
                        
                        
                        
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        text = delta.get("content") or ""

                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            buf = tool_buffers.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                buf["name"] = fn["name"]
                            if fn.get("arguments"):
                                buf["arguments"] += fn["arguments"]

                        if text or reasoning:
                            yield StreamChunk(delta=text, reasoning_delta=reasoning)

            except httpx.TimeoutException as exc:
                raise LLMTimeoutError(f"模型流式调用超时（{self.timeout}s）") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"模型流式调用网络异常: {exc}") from exc

            
            
            tool_calls: list[ToolCall] | None = None
            if tool_buffers:
                tool_calls = []
                for idx in sorted(tool_buffers):
                    buf = tool_buffers[idx]
                    if not buf["name"]:
                        continue
                    tool_calls.append(
                        ToolCall(
                            id=buf["id"] or f"call_{idx}",
                            name=buf["name"],
                            arguments=load_arguments(buf["arguments"]),
                            raw_arguments=buf["arguments"],
                        )
                    )

            yield StreamChunk(
                tool_calls=tool_calls,
                usage=usage or None,
                finish_reason=finish_reason or ("tool_calls" if tool_calls else "stop"),
            )
            return

        raise LLMError("模型流式调用失败：已达最大重试次数")

    
    
    
    async def list_models(self) -> list[str]:

        try:
            resp = await self._client.get("/models", timeout=httpx.Timeout(20.0, connect=10.0))
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接模型端点 {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            self._raise_for_status(resp.status_code, resp.text)
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [str(i.get("id")) for i in items if isinstance(i, dict) and i.get("id")]

    async def aclose(self) -> None:
        await self._client.aclose()
