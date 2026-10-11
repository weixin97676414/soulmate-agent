"""OpenAI 兼容适配器。

按《智能体框架开发文档》ADR-003：所有适配器优先走 OpenAI 兼容协议。
DeepSeek、通义、豆包、Kimi、智谱、SiliconFlow、Ollama 均可复用本适配器，
仅需配置不同的 ``base_url`` / ``api_key`` / ``model_name``。
"""

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

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def is_loopback_url(url: str) -> bool:
    """判断端点是否指向本机。

    用途：决定要不要读系统代理设置（见 ``__init__`` 里的说明）。
    """
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


class OpenAICompatAdapter(BaseLLM):
    """对接任意 OpenAI Chat Completions 兼容端点。"""

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
        # 平台策略：`profile` 描述这个端点已知的协议差异，`fallbacks` 记住运行期
        # 实际撞到的不兼容参数（例如某网关不支持 stream_options）。
        # 两者分工详见 ``llm/platform.py`` 的模块说明。
        self.profile = detect_profile(self.base_url)
        self.fallbacks = AdaptiveFallbacks()
        # 本机端点必须绕过系统代理。
        #
        # windows 上 httpx 会通过 urllib.request.getproxies() 读取**注册表**里的
        # 系统代理（不只是环境变量），而它对 127.0.0.1 不做豁免。企业网络里
        # 配了代理是很常见的情况，结果就是"本地 Ollama 怎么都连不上"，
        # 报错还是代理返回的 502，排查方向完全错。
        #
        # 云端**默认也不走代理**（use_system_proxy=False，用户按模型显式打开）：
        # 实测有系统代理的机器上，国内厂商（硅基流动/百炼）的请求全被代理拖成
        # 超时，直连都在 300ms 内 —— 而"要不要代理"只有用户自己知道（访问
        # OpenAI/Anthropic 通常需要，访问国内厂商通常不需要），交给配置最稳。
        loopback = is_loopback_url(self.base_url)
        # ⚠️ 走 utils.http 的统一入口（自动复用共享 SSL 上下文）。
        # 直接写 httpx.AsyncClient 的话，**每条客户端**都要新建一个 SSL 上下文
        # （Windows 上约 500ms），而"保存模型"每次都要重建全部适配器 ——
        # 三个模型就要 1.5 秒，而且是同步的、会把整个事件循环一起堵住。
        # 详见 utils/http.py 的实测数据。
        self._client = async_client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=15.0),
            trust_env=(not loopback) and use_system_proxy,
            # 仅供测试注入 MockTransport，生产环境为 None
            transport=transport,
        )

    # ------------------------------------------------------------------ #
    # 格式转换：框架内部 -> OpenAI
    # ------------------------------------------------------------------ #
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
                # 带图消息的 content 必须从**字符串**变成**分片数组**，这是
                # OpenAI 兼容协议的硬要求（纯文本才允许用字符串）。
                #
                # 文字分片放最前面：部分网关对"图片在前"的处理不一致，
                # 而"先给指令再给图"也是更自然的表达顺序。
                parts: list[dict[str, Any]] = []
                if m.content:
                    parts.append({"type": "text", "text": m.content})
                parts.extend(
                    {"type": "image_url", "image_url": {"url": part.data_url}}
                    for part in m.images
                    if part.data_url
                )
                # 只有图片、没有文字时 parts 仍然非空；但万一图片都被过滤掉了，
                # 退回纯字符串，避免发一个空数组给网关
                content = parts or m.content

            # 注意：**前缀缓存不受影响**。图片只落在最后一条 user 消息上，
            # 它前面的历史一字未动，缓存前缀照旧命中。
            item: dict[str, Any] = {"role": m.role, "content": content}
            if m.tool_calls:
                item["tool_calls"] = [tc.to_openai() for tc in m.tool_calls]  # type: ignore[attr-defined]
                # 带 tool_calls 的 assistant 消息 content 允许为空串
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

        # 采样参数：``clamp`` 返回 None 表示这个厂商**完全不接受**它
        # （推理模型的典型行为）。此时必须整个字段都不发送 ——
        # 传一个默认值进去照样会被拒，因为问题在于字段而不是取值。
        clamped = clamp(temperature, self.profile.temperature_range)
        if clamped is not None and self.fallbacks.enabled("temperature"):
            payload["temperature"] = clamped

        # ``top_p`` 与 ``temperature`` 是**两种不同的随机性控制**，同时调会互相
        # 干扰（OpenAI 官方也建议只用其中之一）。但这里不替用户做取舍：
        # 他两个都填说明他知道自己在干什么，两个都不填就两个都不发。
        #
        # 额外要求 ``temperature_range is not None``：厂商连 temperature 都不接受时
        # （推理模型的典型行为），top_p 同样不该发 —— 它们属于同一类"采样控制"，
        # 一个不支持另一个基本也不支持，而发出去就是整条请求 400。
        if (
            top_p is not None
            and self.profile.temperature_range is not None
            and self.fallbacks.enabled("top_p")
        ):
            clamped_top_p = clamp(top_p, self.profile.top_p_range)
            if clamped_top_p is not None:
                payload["top_p"] = clamped_top_p

        # 惩罚类参数：部分厂商完全不支持（通义、智谱都在这里），
        # 发出去会让整条请求 400，所以先看 profile 再决定发不发
        if self.profile.supports_penalties:
            if frequency_penalty is not None and self.fallbacks.enabled("frequency_penalty"):
                payload["frequency_penalty"] = frequency_penalty
            if presence_penalty is not None and self.fallbacks.enabled("presence_penalty"):
                payload["presence_penalty"] = presence_penalty

        # 思考强度：只有用户**主动选过**才会走到这里（None = 不发送）。
        #
        # 这是刻意的：多数网关不认识这个字段，默认发送等于让所有用户替少数推理模型
        # 承担"请求被拒"的风险。而一旦用户主动选了档位，就说明他知道自己在调什么 ——
        # 万一这家不认，`_ADAPTIVE_PARAMS` 里的自适应回退会禁用该字段并重试一次。
        #
        # ⚠️ **不能再硬编码 `reasoning_effort`。** 那正是"思考程度设了没生效"的根因：
        # 除 OpenAI 外的厂商各有各的写法（通义是 enable_thinking + thinking_budget，
        # 智谱是 thinking 对象），而它们对不认识的字段是**静默忽略**的 ——
        # 请求成功、回答正常，只有那个开关什么都没干，用户完全看不出来。
        # 现在按厂商策略生成，见 platform.ThinkingStrategy。
        if reasoning_effort and self.supports_reasoning:
            for field_name, value in self.profile.thinking.payload_for(
                reasoning_effort
            ).items():
                if self.fallbacks.enabled(field_name):
                    payload[field_name] = value

        if tools and self.supports_tools and self.fallbacks.enabled("tools"):
            payload["tools"] = self._to_openai_tools(tools)

        if max_tokens and self.fallbacks.enabled("max_tokens"):
            # 新模型改叫 max_completion_tokens，老模型又不认这个名字，
            # 所以按厂商区分而不是全局改掉
            payload[self.profile.max_tokens_field] = max_tokens

        if stream and self.profile.stream_usage and self.fallbacks.enabled("stream_options"):
            # 让厂商在最后一个 chunk 返回 usage —— 没有它就统计不了费用与缓存命中率
            payload["stream_options"] = {"include_usage": True}

        return payload

    def _adapt_to_error(self, body: str) -> bool:
        """厂商抱怨某个参数不支持时记住它，返回 True 表示"值得重试一次"。

        只在能**精确定位**到字段名时才自愈。定位不到就让它照常抛错 ——
        否则会把真正的错误（Key 失效、模型不存在）误判成参数问题，
        重试三次然后给出一个完全无关的报错。
        """
        param = extract_unsupported_param(body)
        return bool(param) and self.fallbacks.disable(param)

    # ------------------------------------------------------------------ #
    # 响应解析
    # ------------------------------------------------------------------ #
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
            # 别名同流式那条：部分网关只给 `reasoning`（见下面 _stream 里的说明）
            reasoning_content=msg.get("reasoning_content") or msg.get("reasoning") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason") or "",
            usage=data.get("usage") or {},
            raw=data,
        )

    # ------------------------------------------------------------------ #
    # 错误归类
    # ------------------------------------------------------------------ #
    @staticmethod
    def _raise_for_status(status: int, body: str) -> None:
        # 厂商返回的响应体是**不可信文本**：某些网关会把请求原样回显（含
        # Authorization 头），有些错误页还会带上请求参数。这段内容会随错误信息
        # 一路走到界面上，所以必须先脱敏再拼进去。
        snippet = redact(body[:500])
        if status in (401, 403):
            raise LLMAuthError(f"模型鉴权失败（HTTP {status}），请检查 API Key。{snippet}")
        if status == 429:
            raise LLMError(f"触发厂商限流（HTTP 429），请稍后重试。{snippet}")
        raise LLMError(f"模型调用失败（HTTP {status}）。{snippet}")

    # ------------------------------------------------------------------ #
    # 非流式
    # ------------------------------------------------------------------ #
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
            # payload 必须每轮重建：上一轮可能刚被自适应回退禁用了某个参数
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
                # 不是所有 400 都值得重试：只有明确指向"某个入参不支持"才自愈。
                # 定位不到就让 _raise_for_status 正常抛出，避免把鉴权失败
                # 误判成参数问题后连试三次再报一个无关的错误。
                if self._adapt_to_error(resp.text) and attempt < self.max_retries:
                    continue
                self._raise_for_status(resp.status_code, resp.text)

            data = resp.json()
            # HTTP 200 但内容其实是错误。不拦的话，下面解析 choices 会炸出一个
            # 和真实原因毫无关系的异常，界面上就是"莫名其妙地失败了"。
            wrapped = looks_like_error_payload(data)
            if wrapped:
                raise LLMError(f"模型服务返回错误：{redact(str(wrapped))}")

            return self._parse_response(data)

        raise last_error or LLMError("模型调用失败：已达最大重试次数")

    # ------------------------------------------------------------------ #
    # 流式
    # ------------------------------------------------------------------ #
    async def stream(  # type: ignore[override]
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
        # 外层是「自适应重试」循环。
        #
        # 它只能重放**还没有 yield 过任何分片**的失败 —— 一旦内容已经流给用户，
        # 生成器就撤不回去了，那种情况只能报错。实际需要重试的都是请求阶段的
        # 400/429/5xx，正好全都落在这个范围内。
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

            # 工具调用在流中以「按 index 分片的 JSON 字符串」到达，需要累积拼接
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

                        # HTTP 200 但内容其实是错误：部分网关会把错误夹在流中间。
                        # 正常的流式分片都带 choices（哪怕内容为空数组），
                        # 所以这里不会误伤；不拦的话界面上就是流到一半莫名中断。
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
                        # ⚠️ 两个字段名都要认：正式名是 ``reasoning_content``（DeepSeek 起的头，
                        # 后来成了事实标准），但**一部分 OpenAI 兼容网关（含硅基流动）只用
                        # ``reasoning``**。只认前者的后果不是报错，而是"思考强度设了却看不到
                        # 思考内容"—— 那类静默失效最难查。
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

            # 完整读完后才到这里：把累积的工具调用一次性交出，然后**立即 return**。
            # 少了 return 会掉进下一轮重试，把同一段话再生成一遍。
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

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    async def list_models(self) -> list[str]:
        """调用 ``GET /models`` 拉取可用模型，用于设置中心的连通性测试。"""
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
