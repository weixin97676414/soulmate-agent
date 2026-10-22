








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





        profile = PlatformProfile(name="dashscope", supports_penalties=False)

        payload = payload_of(
            make_adapter(profile), top_p=0.5, frequency_penalty=0.3, presence_penalty=0.1
        )

        assert payload["top_p"] == 0.5  
        assert "frequency_penalty" not in payload
        assert "presence_penalty" not in payload

    def test_top_p_is_clamped_to_vendor_range(self):

        profile = PlatformProfile(name="narrow", top_p_range=(0.0, 0.6))

        assert payload_of(make_adapter(profile), top_p=0.95)["top_p"] == 0.6

    def test_top_p_is_dropped_for_model_that_rejects_sampling(self):





        profile = PlatformProfile(name="reasoner", temperature_range=None)

        payload = payload_of(make_adapter(profile), top_p=0.5)

        assert "top_p" not in payload
        assert "temperature" not in payload


class TestAdaptiveFallback:
    @pytest.mark.asyncio
    async def test_unsupported_top_p_is_retried_without_it(self):

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

        primary = RecordingLLM(error=LLMError("主模型挂了"))
        backup = RecordingLLM()
        chain = FallbackLLM(primary, [backup], primary_id="a", fallback_ids=["b"])

        await chain.chat([Message(role="user", content="hi")], top_p=0.42)

        assert backup.seen[-1]["top_p"] == 0.42





class TestReasoningEffort:









    def test_not_sent_when_unset(self):
        assert "reasoning_effort" not in payload_of(make_adapter())

    def test_sent_when_chosen(self):
        payload = payload_of(make_adapter(), reasoning_effort="high")

        assert payload["reasoning_effort"] == "high"

    def test_not_sent_when_model_declares_no_support(self):

        payload = payload_of(make_adapter(supports_reasoning=False), reasoning_effort="high")

        assert "reasoning_effort" not in payload

    def test_adaptive_fallback_can_disable_it(self):

        adapter = make_adapter()
        adapter.fallbacks.disable("reasoning_effort")

        assert "reasoning_effort" not in payload_of(adapter, reasoning_effort="low")

    @pytest.mark.asyncio
    async def test_fallback_chain_forwards_it(self):

        primary = RecordingLLM()
        chain = FallbackLLM(primary, [], primary_id="a", fallback_ids=[])

        await chain.chat([Message(role="user", content="hi")], reasoning_effort="medium")

        assert primary.seen[-1]["reasoning_effort"] == "medium"


class TestReasoningEffortReachesTheWire:












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

    adapter = make_adapter()

    payload = adapter._build_payload(
        [Message(role="user", content="hi")],
        [ToolSpec(name="t", description="d", parameters={"type": "object"})],
        0.7,
        None,
        stream=False,
    )

    assert payload["tools"][0]["function"]["name"] == "t"
