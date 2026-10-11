"""采样参数（top_p / 频率惩罚 / 存在惩罚）。

这组用例钉住的不是"参数能不能传下去"，而是**什么时候绝对不能传**。

``None`` 在这里表示"这个字段根本不发"，而不是"发默认值" —— 这两者的区别是
整件事的关键：不接受的厂商收到默认值同样会 400，问题出在字段本身。所以
每条"该发"的用例都配了一条"不该发"的，否则测不出这个语义。
"""

from __future__ import annotations

import json

import httpx
import pytest

from my_agent.errors import LLMError
from my_agent.llm.adapters.openai_compat import OpenAICompatAdapter
from my_agent.llm.base import BaseLLM, LLMResponse, Message, StreamChunk, ToolSpec
from my_agent.llm.fallback import FallbackLLM
from my_agent.llm.platform import PlatformProfile


def make_adapter(profile: PlatformProfile | None = None, **kwargs) -> OpenAICompatAdapter:
    """构造一个不会真的发请求的适配器，用于直接检查 payload。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    adapter = OpenAICompatAdapter(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model_name="m",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )
    if profile is not None:
        adapter.profile = profile
    return adapter


def payload_of(adapter: OpenAICompatAdapter, **sampling) -> dict:
    return adapter._build_payload(
        [Message(role="user", content="hi")], None, sampling.pop("temperature", 0.7),
        sampling.pop("max_tokens", None), stream=False, **sampling,
    )


class TestDefaults:
    def test_nothing_is_sent_when_unset(self):
        """一个都不填就一个都不发 —— 这是默认状态，也是最该保持的行为。

        默认发出去的话，等于替所有用户打开了三个他们没要求的旋钮；
        而其中任意一个都可能让某家网关直接拒掉请求。
        """
        payload = payload_of(make_adapter())

        assert "top_p" not in payload
        assert "frequency_penalty" not in payload
        assert "presence_penalty" not in payload

    def test_all_three_are_sent_when_set(self):
        payload = payload_of(make_adapter(), top_p=0.5, frequency_penalty=0.3, presence_penalty=0.1)

        assert payload["top_p"] == 0.5
        assert payload["frequency_penalty"] == 0.3
        assert payload["presence_penalty"] == 0.1


class TestVendorDifferences:
    def test_penalties_are_not_sent_to_unsupporting_vendor(self):
        """``supports_penalties=False`` 的厂商（通义、智谱）一个字都不该收到。

        单独看"通了"，但它其实是最容易造成"整条请求 400"的一项 ——
        而且报错信息通常只说某个参数非法，不会告诉你"这家根本不支持惩罚"。
        """
        profile = PlatformProfile(name="dashscope", supports_penalties=False)

        payload = payload_of(
            make_adapter(profile), top_p=0.5, frequency_penalty=0.3, presence_penalty=0.1
        )

        assert payload["top_p"] == 0.5  # top_p 仍然发
        assert "frequency_penalty" not in payload
        assert "presence_penalty" not in payload

    def test_top_p_is_clamped_to_vendor_range(self):
        """超出厂商区间要压回来，而不是原样发出去吃 400。"""
        profile = PlatformProfile(name="narrow", top_p_range=(0.0, 0.6))

        assert payload_of(make_adapter(profile), top_p=0.95)["top_p"] == 0.6

    def test_top_p_is_dropped_for_model_that_rejects_sampling(self):
        """连 temperature 都不接受的推理模型，top_p 也不能发。

        它们属于同一类采样控制，一个不支持另一个基本也不支持；
        而 ``top_p_range`` 有默认值，不小心就会漏过这道判断。
        """
        profile = PlatformProfile(name="reasoner", temperature_range=None)

        payload = payload_of(make_adapter(profile), top_p=0.5)

        assert "top_p" not in payload
        assert "temperature" not in payload


class TestAdaptiveFallback:
    @pytest.mark.asyncio
    async def test_unsupported_top_p_is_retried_without_it(self):
        """网关抱怨 top_p 不认识时，去掉它重试一次应当成功。"""
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            calls.append(payload)
            if "top_p" in payload:
                return httpx.Response(
                    400, json={"error": {"message": "Unknown parameter: 'top_p'"}}
                )
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "好"}, "finish_reason": "stop"}]}
            )

        adapter = make_adapter(max_retries=1)
        adapter._client = httpx.AsyncClient(
            base_url=adapter.base_url, transport=httpx.MockTransport(handler)
        )

        reply = await adapter.chat([Message(role="user", content="hi")], top_p=0.5)
        await adapter.aclose()

        assert reply.content == "好"
        assert len(calls) == 2
        assert "top_p" in calls[0]
        assert "top_p" not in calls[1]


# --------------------------------------------------------------------------- #
# 降级链的转发
# --------------------------------------------------------------------------- #
class RecordingLLM(BaseLLM):
    def __init__(self, *, error: BaseException | None = None) -> None:
        super().__init__(model_name="rec")
        self.error = error
        self.seen: list[dict] = []

    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        self.seen.append(kwargs)
        if self.error is not None:
            raise self.error
        return LLMResponse(content="ok", finish_reason="stop")

    async def stream(self, messages, tools=None, **kwargs):
        self.seen.append(kwargs)
        yield StreamChunk(delta="ok", finish_reason="stop")


class TestFallbackForwarding:
    """降级链必须把采样参数一并转发。

    漏掉不会报错，只会让**配了降级链的用户**发现自己调的参数时灵时不灵：
    主模型在时生效、一切到备用就消失。这类问题几乎不可能靠观察定位，
    所以只能用测试钉住。
    """

    @pytest.mark.asyncio
    async def test_chat_forwards_sampling(self):
        primary = RecordingLLM()
        chain = FallbackLLM(primary, [], primary_id="a", fallback_ids=[])

        await chain.chat(
            [Message(role="user", content="hi")],
            top_p=0.5,
            frequency_penalty=0.3,
            presence_penalty=0.1,
            reasoning_effort="high",
        )

        assert primary.seen[-1]["top_p"] == 0.5
        assert primary.seen[-1]["frequency_penalty"] == 0.3
        assert primary.seen[-1]["presence_penalty"] == 0.1
        assert primary.seen[-1]["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_stream_forwards_sampling(self):
        primary = RecordingLLM()
        chain = FallbackLLM(primary, [], primary_id="a", fallback_ids=[])

        async for _ in chain.stream([Message(role="user", content="hi")], top_p=0.25):
            pass

        assert primary.seen[-1]["top_p"] == 0.25

    @pytest.mark.asyncio
    async def test_fallback_also_receives_them(self):
        """切到备用模型之后，参数必须还在 —— 这是这条用例存在的全部理由。"""
        primary = RecordingLLM(error=LLMError("主模型挂了"))
        backup = RecordingLLM()
        chain = FallbackLLM(primary, [backup], primary_id="a", fallback_ids=["b"])

        await chain.chat([Message(role="user", content="hi")], top_p=0.42)

        assert backup.seen[-1]["top_p"] == 0.42


# --------------------------------------------------------------------------- #
# 思考强度
# --------------------------------------------------------------------------- #
class TestReasoningEffort:
    """``reasoning_effort`` 的发送条件。

    它与采样参数的关键差别是：**只在用户主动选过档位时才发送**（None = 完全不发）。
    所以这里同时钉住两件事 —— 选了必须发出去，没选一个字段都不许多。

    这个"默认不发"的性质不是洁癖：多数网关不认识这个字段，默认发送等于让所有用户
    替少数推理模型承担"请求被拒"的风险。
    """

    def test_not_sent_when_unset(self):
        assert "reasoning_effort" not in payload_of(make_adapter())

    def test_sent_when_chosen(self):
        payload = payload_of(make_adapter(), reasoning_effort="high")

        assert payload["reasoning_effort"] == "high"

    def test_not_sent_when_model_declares_no_support(self):
        """模型声明不支持时不发 —— 用户即使选了档位，也不该因此把整条请求弄失败。"""
        payload = payload_of(make_adapter(supports_reasoning=False), reasoning_effort="high")

        assert "reasoning_effort" not in payload

    def test_adaptive_fallback_can_disable_it(self):
        """厂商拒绝过这个字段之后，后续请求不该再发它（否则每次都要先失败一次）。"""
        adapter = make_adapter()
        adapter.fallbacks.disable("reasoning_effort")

        assert "reasoning_effort" not in payload_of(adapter, reasoning_effort="low")

    @pytest.mark.asyncio
    async def test_fallback_chain_forwards_it(self):
        """降级链必须一起转发，否则"主模型能用、切到备用就失效"。"""
        primary = RecordingLLM()
        chain = FallbackLLM(primary, [], primary_id="a", fallback_ids=[])

        await chain.chat([Message(role="user", content="hi")], reasoning_effort="medium")

        assert primary.seen[-1]["reasoning_effort"] == "medium"


class TestReasoningEffortReachesTheWire:
    """走**真实调用路径**把参数钉住。

    上面那一组只测了 `_build_payload`，而"参数从 `chat()` 传进 payload"是
    **另一个**独立的失败点 —— 实际就漏过一次：`_build_payload` 支持了、
    `FallbackLLM` 也转发了，但 `OpenAICompatAdapter.chat/stream` 既没接这个参数、
    也没往 payload 里传。只测 `_build_payload` 完全抓不到，而线上表现是
    `FallbackLLM` 转发时直接 TypeError。

    教训：**给抽象接口加参数时，要有一个走到底的用例**，否则中间层漏掉一处
    不会有任何信号。
    """

    @pytest.mark.asyncio
    async def test_chat_transmits_it(self):
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
            )

        adapter = make_adapter()
        adapter._client = httpx.AsyncClient(
            base_url=adapter.base_url, transport=httpx.MockTransport(handler)
        )

        await adapter.chat([Message(role="user", content="hi")], reasoning_effort="high")
        await adapter.aclose()

        assert seen[-1]["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_stream_transmits_it(self):
        """流式才是客户端实际走的那条路（SSE）。"""
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text='data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
            )

        adapter = make_adapter()
        adapter._client = httpx.AsyncClient(
            base_url=adapter.base_url, transport=httpx.MockTransport(handler)
        )

        async for _ in adapter.stream(
            [Message(role="user", content="hi")], reasoning_effort="low"
        ):
            break
        await adapter.aclose()

        assert seen and seen[0]["reasoning_effort"] == "low"

    @pytest.mark.asyncio
    async def test_fallback_chain_to_real_adapter(self):
        """降级链 → 真实适配器 → 真的发出去。这才是生产里那条完整的路。"""
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
            )

        adapter = make_adapter()
        adapter._client = httpx.AsyncClient(
            base_url=adapter.base_url, transport=httpx.MockTransport(handler)
        )
        chain = FallbackLLM(adapter, [], primary_id="a", fallback_ids=[])

        await chain.chat([Message(role="user", content="hi")], reasoning_effort="medium")
        await adapter.aclose()

        assert seen[-1]["reasoning_effort"] == "medium"


def test_tool_specs_still_work():
    """确认这几处改动没有意外影响工具字段的发送（回归护栏）。"""
    adapter = make_adapter()

    payload = adapter._build_payload(
        [Message(role="user", content="hi")],
        [ToolSpec(name="t", description="d", parameters={"type": "object"})],
        0.7,
        None,
        stream=False,
    )

    assert payload["tools"][0]["function"]["name"] == "t"
