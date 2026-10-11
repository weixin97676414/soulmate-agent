"""Anthropic Messages API 适配器。

对应《智能体框架开发文档》4.3.1 的专用适配器。之所以不能复用
``openai_compat``，是因为 Anthropic 的协议在四个关键点上不同：

1. **system 是顶层参数，不是一条消息**。塞进 messages 会直接 400。
2. **工具结果要包成 ``user`` 消息里的 ``tool_result`` 块**，而且**连续的多个
   工具结果必须合并进同一条 user 消息**；拆成多条会被判为角色不交替。
3. **prompt caching 是显式的**：要在内容块上打 ``cache_control`` 断点
   （最多 4 个）。这是它和 DeepSeek / OpenAI「自动前缀缓存」最大的差别——
   不打断点就**完全没有缓存**，输入价格差一个数量级。
4. ``max_tokens`` 是**必填**的，不给会 400。

## 缓存断点怎么放

Anthropic 的缓存层级是 ``tools → system → messages``：某个断点会把它**之前**
的全部内容都纳入缓存。所以：

- 在**最后一个 tool 定义**上打断点 → 缓存住整个工具列表；
- 在 **system 块**上打断点 → 缓存住 tools + system；
- 在**最后一条消息**的末尾打断点 → 缓存住整段对话历史，
  下一轮对话就能命中（这是长会话里最值钱的一个断点）。

三个断点，在 4 个的上限内。注意最小可缓存长度是 1024 token（Haiku 为 2048），
低于它断点会被忽略——**不会报错**，只是不生效。
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

logger = logging.getLogger(__name__)

API_VERSION = "2023-06-01"

# Anthropic 的限流与过载码。529（overloaded）是它独有的，值得重试。
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}

# 没有显式指定时给的输出上限。Anthropic 必填 max_tokens，不给会 400。
DEFAULT_MAX_TOKENS = 4096

CACHE_CONTROL = {"type": "ephemeral"}

# "思考强度"档位 -> 扩展思考的 token 预算。
#
# Anthropic 没有 ``reasoning_effort`` 这个名字，对应的是"扩展思考"的
# ``budget_tokens``，而且它有两条硬约束：**>= 1024** 且 **< max_tokens**。
# 违反任一条都是整条请求 400，所以下面会先判一下再决定发不发。
_THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}

# 预算至少要这么多才有意义（Anthropic 的硬下限也是 1024）
_MIN_THINKING_BUDGET = 1024
# 给正文留的余量：budget 必须 < max_tokens
_THINKING_HEADROOM = 1024

# 停止原因 -> 框架内部口径
_STOP_REASON = {
    "tool_use": "tool_calls",
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
}


def is_loopback_url(url: str) -> bool:
    """判断端点是否指向本机（决定要不要读系统代理设置）。

    绝大多数 Anthropic 用法是云端，但有人会用本地代理/网关转发，
    那时把 127.0.0.1 的请求交给系统代理会得到 502，排查方向完全跑偏。
    """
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


class AnthropicAdapter(BaseLLM):
    """对接 Anthropic Messages API（``/v1/messages``）。"""

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
            token_limit=token_limit,
        )
        # base_url 通常填 https://api.anthropic.com；它自己的路由前缀是 /v1
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        # 关掉后不打断点：调试缓存行为时有用，也便于排查"是不是断点导致的 400"
        self.cache_enabled = cache_enabled

        loopback = is_loopback_url(self.base_url)
        # 走统一入口共享 SSL 上下文（否则每条客户端要多付约 500ms，见 utils/http.py）
        self._client = async_client(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=15.0),
            # 与 OpenAI 适配器同样的取舍：本机端点必须绕过系统代理；
            # 云端默认也不走（use_system_proxy 按模型显式打开，见 ModelSpec）
            trust_env=(not loopback) and use_system_proxy,
            transport=transport,
        )

    # ------------------------------------------------------------------ #
    # 格式转换：框架内部 -> Anthropic
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_anthropic_messages(
        messages: list[Message],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """拆出 system，并把工具结果合并成合法的 user 消息。"""
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        # 连续的 tool 消息必须合成一条 user 消息里的多个 tool_result 块；
        # 分成多条会被 Anthropic 判为"角色不交替"而 400。
        pending_results: list[dict[str, Any]] = []

        def flush_results() -> None:
            if pending_results:
                out.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        def append(role: str, blocks: list[dict[str, Any]]) -> None:
            """同角色的相邻消息合并。

            内部记忆里可能出现连续两条 user（例如"空回复催促"紧跟用户原话，
            中间那条空 assistant 被跳过了）。Anthropic 要求角色交替，
            不合并就会偶发 400，而且只在特定时序下出现，极难复现。
            """
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
        """system 参数。打成缓存断点后，tools + system 会一起被缓存。"""
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
            # 断点打在**最后一个**工具上：缓存层级是 tools → system → messages，
            # 一个断点就把整个工具列表纳入缓存
            converted[-1] = {**converted[-1], "cache_control": CACHE_CONTROL}
        return converted

    @staticmethod
    def _mark_history_breakpoint(messages: list[dict[str, Any]]) -> None:
        """在最后一条消息末尾打断点，让下一轮能命中整段历史。

        这是长会话里最值钱的一个断点：没有它，每轮都要按全价重算
        system + 全部历史；有了它，只有新增部分按全价算。
        """
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
        """Anthropic 原生协议**没有**这两个惩罚参数，只能忽略。

        为什么是"忽略 + 记一行日志"而不是报错：它们的取值来自**全局设置**，
        用户可能是在用别家模型时调的，切到 Claude 不该让整个请求失败。
        但也不能一声不响 —— 用户会发现"我明明调了却没效果"，
        所以留下一条可查的记录。用 debug 级别是因为每轮对话都会走到这里，
        warning 会把日志刷满。
        """
        if frequency_penalty is not None or presence_penalty is not None:
            logger.debug(
                "Anthropic 原生协议不支持 frequency_penalty / presence_penalty，"
                "本次已忽略（top_p 仍然生效）"
            )

    def _thinking_param(self, effort: str | None, max_tokens: int) -> dict[str, Any] | None:
        """把"思考强度"翻译成 Anthropic 的扩展思考参数；装不下就返回 None。

        硬约束是 ``1024 <= budget_tokens < max_tokens``。

        **额度不够时按上限缩减，而不是干脆不生效**：档位是倾向而不是精确值，
        用户要的是"多想一点"。直接放弃会让他觉得"我明明调了高却没变化"，
        而且他归因不到"输出上限太小"这一层 —— 那是典型的"配置了但不起作用"。
        只有连最低预算都装不下（max_tokens <= 1024）时才不发，因为那种情况
        Anthropic 本来也不接受。
        """
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
        # Anthropic 支持 top_p（官方同样建议它与 temperature 二选一）
        if top_p is not None:
            payload["top_p"] = top_p

        thinking = self._thinking_param(reasoning_effort, int(payload["max_tokens"]))
        if thinking is not None:
            payload["thinking"] = thinking
            # 开着扩展思考时 temperature **只能是 1**，否则整条请求被拒。
            # 与其把用户填的 0.7 悄悄改成 1（他之后会发现"温度没生效"），
            # 不如干脆不发这个字段，让 Anthropic 用自己的默认值 —— 少一个字段，
            # 好过让一个用户明确填过的值被静默改掉。
            payload.pop("temperature", None)
        if stream:
            payload["stream"] = True
        system_param = self._build_system(system)
        if system_param is not None:
            payload["system"] = system_param
        if tools and self.supports_tools:
            payload["tools"] = self._to_anthropic_tools(tools)
        return payload

    # ------------------------------------------------------------------ #
    # 响应解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_blocks(blocks: list[dict[str, Any]]) -> tuple[str, list[ToolCall], str]:
        """把 content 块拆成（文本、工具调用、思维链）。"""
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

    # ------------------------------------------------------------------ #
    # 错误归类
    # ------------------------------------------------------------------ #
    @staticmethod
    def _raise_for_status(status: int, body: str) -> None:
        # 厂商返回体是不可信文本，可能回显请求内容（含 x-api-key），先脱敏再拼
        snippet = redact(body[:500])
        if status in (401, 403):
            raise LLMAuthError(f"Anthropic 鉴权失败（HTTP {status}），请检查 API Key。{snippet}")
        if status == 429:
            raise LLMError(f"触发 Anthropic 限流（HTTP 429），请稍后重试。{snippet}")
        if status == 529:
            raise LLMError(f"Anthropic 服务过载（HTTP 529），请稍后重试。{snippet}")
        raise LLMError(f"Anthropic 调用失败（HTTP {status}）。{snippet}")

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

        # 工具调用的参数是**分片**的 JSON 字符串（input_json_delta），
        # 要按 content block 的 index 分别累积
        tool_buffers: dict[int, dict[str, Any]] = {}
        # usage 分散在两个事件里：message_start 给输入，message_delta 给输出
        usage: dict[str, Any] = {}
        finish_reason = ""

        try:
            async with self._client.stream("POST", "/v1/messages", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    self._raise_for_status(resp.status_code, body)

                async for line in resp.aiter_lines():
                    # Anthropic 会同时发 `event:` 和 `data:` 两行。
                    # data 的 JSON 里自带 type，所以只认 data 行就够，
                    # 不必维护 event 行的状态机。
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
                        # 输入 token 与缓存命中量都在这里
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
                            # 这里只带 output_tokens，必须**合并**而不是覆盖，
                            # 否则前面拿到的输入 token 与缓存命中量会全丢
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

        # 流结束：把累积的工具调用一次性交出
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

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    async def list_models(self) -> list[str]:
        """拉取可用模型，用于设置中心的连通性测试。"""
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
