"""多模型故障降级。

对应《智能体框架开发文档》4.6/4.7（失败重试与降级）。主模型不可用时按配置顺序
自动切到备用模型，让用户"还能继续用"，而不是弹出一个技术性报错。

## 哪些错误会降级，哪些不会

**会降级**（基础设施类故障）：超时、网络异常、厂商 5xx、429 限流、模型名写错。
这些换一个模型大概率就能成，用户此刻要的也是"别中断手上的活"。

**不会降级**：鉴权失败（401/403）。
这是一个刻意的取舍——Key 失效通常意味着**过期 / 欠费 / 凭据被改**，
用户必须知道。静默切到另一个厂商，后果是悄悄替用户花另一家的钱，
而他自己的账户到底怎么了再也看不出来。鉴权错误直接抛出去反而更诚实。

## 为什么降级链只做一层

备用模型本身如果也配了降级链，这里**不会**再展开它。

原因不是偷懒：一旦 A 的备用是 B、B 的备用又是 A，逐级展开就会形成无限循环
（A 失败 → 切 B → B 失败 → 切 A → A 又失败 → ...），直到请求超时。
固定一层之后，"这次请求到底会试哪些模型"始终是一张确定的、看得见的短表，
排查时也只需要看一个模型的配置。
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Iterator

from ..errors import LLMAuthError, LLMError
from ..observability.request_context import current_session_id
from .base import BaseLLM, LLMResponse, Message, StreamChunk, ToolSpec

logger = logging.getLogger(__name__)

# (失败的模型 id, 接手的模型 id, 失败原因)；接手为空表示已经没有备用可用
FallbackListener = Callable[[str, str, str], None]


class FallbackLLM(BaseLLM):
    """把一个主模型和若干备用模型串成一条链。

    对外表现得和普通 ``BaseLLM`` 完全一样，Agent 层不需要知道自己拿到的是条链。
    """

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
            token_limit=primary.token_limit,
        )
        self._primary = primary
        self._fallbacks = list(fallbacks)
        self._primary_id = primary_id
        self._fallback_ids = list(fallback_ids)
        # 用于把降级事件透出去给上层（目前只写日志；留这个口子是为了
        # 将来界面能提示"主模型不可用，已切换到 X"，而不是让用户以为一切正常）
        self._listener = listener

    # ------------------------------------------------------------------ #
    # 链的结构
    # ------------------------------------------------------------------ #
    def _chain(self) -> Iterator[tuple[str, BaseLLM]]:
        """按尝试顺序产出 ``(模型 id, 实例)``。"""
        yield self._primary_id, self._primary
        yield from zip(self._fallback_ids, self._fallbacks, strict=True)

    def describe_chain(self) -> list[str]:
        """给设置/诊断界面看的备用链（不含当前模型自身）。"""
        return list(self._fallback_ids)

    # ------------------------------------------------------------------ #
    # 降级记账
    # ------------------------------------------------------------------ #
    def _notify(self, failed_index: int, failed_id: str, error: BaseException) -> None:
        taken_over = (
            self._fallback_ids[failed_index]
            if failed_index < len(self._fallback_ids)
            else ""
        )
        reason = str(error)
        # ⚠️ 降级日志必须带**会话**（第 88 批，L-14）：这句以前只有模型名，
        # 于是"某个会话的回答突然变了风格 / 计费换了一家"时，日志里根本对不上是谁。
        # 会话 id 走 ContextVar（适配器内部拿不到请求信息，见 request_context 的说明）；
        # 不在请求上下文里（后台任务、CLI）就是 `-`。
        logger.warning(
            "模型 %s 调用失败，%s：%s（session=%s）",
            failed_id,
            f"已降级到 {taken_over}" if taken_over else "且已无备用模型可用",
            reason,
            current_session_id.get() or "-",
        )
        if self._listener is not None:
            # 监听器是可选的旁路，它自己炸了绝不能影响正在进行的请求
            with contextlib.suppress(Exception):
                self._listener(failed_id, taken_over, reason)

    # ------------------------------------------------------------------ #
    # BaseLLM 接口
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
                # 凭据有问题 —— 换模型只会掩盖用户自己的账户问题（见模块说明）
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
                    # 这几个必须一起转发。漏掉不会报错，只会让"配了降级链的用户"
                    # 发现自己调的参数**时灵时不灵** —— 主模型在时生效、
                    # 切到备用就消失，而这类问题几乎不可能靠观察定位。
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
                    # 已经有内容流给用户了：换模型等于把半截话接上另一个模型的续写，
                    # 出来的文本会比直接报错更让人困惑。这种情况下只能就此报错。
                    raise
                last_error = exc
                self._notify(index, model_id, exc)

        raise last_error or LLMError("模型调用失败：全部候选均不可用")

    async def list_models(self) -> list[str]:
        """连通性测试只问主模型：备用模型有自己的条目，会在设置里各自测试。"""
        return await self._primary.list_models()

    async def aclose(self) -> None:
        for _, llm in self._chain():
            close = getattr(llm, "aclose", None)
            if close is None:
                continue
            # 其中一个关不掉也要把剩下的关完，避免连接泄漏
            with contextlib.suppress(Exception):
                await close()
