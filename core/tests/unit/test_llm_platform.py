












from __future__ import annotations

import json

import httpx
import pytest

from my_agent.errors import LLMError
from my_agent.llm.adapters.openai_compat import OpenAICompatAdapter
from my_agent.llm.base import Message
from my_agent.llm.platform import (
    DEFAULT_PROFILE,
    AdaptiveFallbacks,
    PlatformProfile,
    clamp,
    detect_profile,
    extract_unsupported_param,
    looks_like_error_payload,
)


def make_adapter(
    handler, base_url: str = "https://api.example.com/v1", **kwargs
) -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        base_url=base_url,
        api_key="sk-test",
        model_name="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def ok_text_reply(text: str = "ok") -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    )





class TestDetectProfile:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://api.openai.com/v1", "openai"),
            ("https://api.deepseek.com/v1", "deepseek"),
            ("https://dashscope.aliyuncs.com/compatible-mode/v1", "dashscope"),
            ("https://open.bigmodel.cn/api/paas/v4", "zhipu"),
            ("https://api.moonshot.cn/v1", "moonshot"),
            ("https://api.moonshot.ai/v1", "moonshot"),
            ("https://ark.cn-beijing.volces.com/api/v3", "volcengine"),
            ("https://api.siliconflow.cn/v1", "siliconflow"),
            ("http://127.0.0.1:11434/v1", "local"),
            ("http://localhost:8000/v1", "local"),
        ],
    )
    def test_known_vendors(self, url: str, expected: str):
        assert detect_profile(url).name == expected

    def test_unknown_vendor_falls_back_to_generic(self):
        
        assert detect_profile("https://llm.mycompany.internal/v1") is DEFAULT_PROFILE

    def test_subdomain_still_matches(self):

        assert detect_profile("https://gateway.dashscope.aliyuncs.com/v1").name == "dashscope"

    def test_malformed_url_is_safe(self):
        assert detect_profile("这不是一个 URL") is DEFAULT_PROFILE
        assert detect_profile("") is DEFAULT_PROFILE

    def test_generic_profile_accepts_default_temperature(self):

        assert clamp(0.7, DEFAULT_PROFILE.temperature_range) == 0.7


class TestClamp:
    def test_value_within_range_is_unchanged(self):
        assert clamp(0.7, (0.0, 2.0)) == 0.7

    def test_above_range_is_clipped(self):

        assert clamp(1.5, (0.01, 1.0)) == 1.0

    def test_below_range_is_clipped(self):
        assert clamp(0.0, (0.01, 1.0)) == 0.01

    def test_none_range_means_unsupported(self):




        assert clamp(0.7, None) is None





class TestExtractUnsupportedParam:
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("{'error': {'message': \"Unknown parameter: 'stream_options'\"}}", "stream_options"),
            ('{"error": {"message": "Unknown parameter: \\"temperature\\""}}', "temperature"),
            ("unrecognized request argument supplied: top_p", "top_p"),
            ("extra inputs are not permitted for max_tokens", "max_tokens"),
        ],
    )
    def test_identifies_the_offending_field(self, body: str, expected: str):
        assert extract_unsupported_param(body) == expected

    def test_ignores_unrelated_errors(self):

        for body in (
            "Invalid API key provided",
            "The model does not exist",
            "Rate limit reached for requests",
        ):
            assert extract_unsupported_param(body) is None

    def test_unidentifiable_field_returns_empty_string(self):

        assert extract_unsupported_param("Unknown parameter supplied") == ""

    def test_never_returns_unknown_field_name(self):





        assert extract_unsupported_param("Unknown parameter: 'ssrf_token'") == ""


class TestAdaptiveFallbacks:
    def test_first_disable_signals_retry(self):
        fb = AdaptiveFallbacks()
        assert fb.disable("stream_options") is True

    def test_second_disable_returns_false(self):

        fb = AdaptiveFallbacks()
        fb.disable("stream_options")
        assert fb.disable("stream_options") is False

    def test_enabled_reflects_state(self):
        fb = AdaptiveFallbacks()
        assert fb.enabled("temperature") is True
        fb.disable("temperature")
        assert fb.enabled("temperature") is False





class TestLooksLikeErrorPayload:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            ({"error": {"message": "余额不足"}}, "余额不足"),
            ({"error": {"msg": "boom"}}, "boom"),
            ({"error": "plain failure"}, "plain failure"),
            ({"code": 400, "message": "bad request"}, "bad request"),
        ],
    )
    def test_detects_wrapped_error(self, data, expected):
        assert looks_like_error_payload(data) == expected

    @pytest.mark.parametrize(
        "data",
        [
            {"choices": [{"message": {"content": "hi"}}]},
            {"choices": []},  
            {"usage": {"prompt_tokens": 1}},  
            {"code": 200, "message": "ok"},
            "not even a dict",
            None,
        ],
    )
    def test_leaves_normal_responses_alone(self, data):
        assert looks_like_error_payload(data) is None





class TestPayloadRespectsProfile:
    def test_temperature_is_clamped_for_strict_vendors(self):
        adapter = make_adapter(lambda _: ok_text_reply(), base_url="https://open.bigmodel.cn/v4")

        payload = adapter._build_payload([], None, 1.5, None, stream=False)

        assert payload["temperature"] == 1.0  

    def test_temperature_is_omitted_for_reasoning_models(self):

        adapter = make_adapter(lambda _: ok_text_reply())
        adapter.profile = PlatformProfile(name="reasoner", temperature_range=None)

        payload = adapter._build_payload([], None, 0.7, None, stream=False)

        assert "temperature" not in payload

    def test_max_tokens_field_name_follows_profile(self):
        adapter = make_adapter(lambda _: ok_text_reply())
        adapter.profile = PlatformProfile(name="newmodel", max_tokens_field="max_completion_tokens")

        payload = adapter._build_payload([], None, 0.7, 512, stream=False)

        assert payload["max_completion_tokens"] == 512
        assert "max_tokens" not in payload

    def test_stream_options_absent_when_disabled(self):
        adapter = make_adapter(lambda _: ok_text_reply())
        adapter.profile = PlatformProfile(name="nostream", stream_usage=False)

        payload = adapter._build_payload([], None, 0.7, None, stream=True)

        assert "stream_options" not in payload


class TestAdaptiveRetry:
    @pytest.mark.asyncio
    async def test_unsupported_field_is_dropped_and_retried(self):





        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            calls.append(payload)
            if "temperature" in payload:
                return httpx.Response(
                    400, json={"error": {"message": "Unknown parameter: 'temperature'"}}
                )
            return ok_text_reply("恢复成功")

        adapter = make_adapter(handler, max_retries=1)

        response = await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert response.content == "恢复成功"
        assert len(calls) == 2
        assert "temperature" in calls[0]
        assert "temperature" not in calls[1]  

    @pytest.mark.asyncio
    async def test_auth_failure_is_not_retried_as_parameter_error(self):

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

        adapter = make_adapter(handler, max_retries=2)

        with pytest.raises(LLMError) as exc:
            await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert len(calls) == 1, "鉴权失败不应重试"
        assert "API Key" in str(exc.value)

    @pytest.mark.asyncio
    async def test_stream_adapts_too(self):
        sse = (
            'data: {"choices":[{"delta":{"content":"终于通了"},"index":0}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop","index":0}]}\n\n'
            "data: [DONE]\n\n"
        )
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            calls.append(payload)
            if payload.get("stream_options"):
                return httpx.Response(
                    400, json={"error": {"message": "Unknown parameter: 'stream_options'"}}
                )
            return httpx.Response(200, content=sse.encode())

        adapter = make_adapter(handler, max_retries=1)
        chunks = [c async for c in adapter.stream([Message(role="user", content="hi")])]
        await adapter.aclose()

        assert any(c.delta == "终于通了" for c in chunks)
        assert "stream_options" not in calls[1]


class TestWrappedErrorSurfaces:
    @pytest.mark.asyncio
    async def test_chat_raises_readable_error(self):


        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"message": "账户余额不足"}})

        adapter = make_adapter(handler)

        with pytest.raises(LLMError) as exc:
            await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert "账户余额不足" in str(exc.value)

    @pytest.mark.asyncio
    async def test_stream_raises_readable_error(self):

        sse = 'data: {"error": {"message": "上游服务不可用"}}\n\ndata: [DONE]\n\n'

        adapter = make_adapter(lambda _: httpx.Response(200, content=sse.encode()))

        with pytest.raises(LLMError) as exc:
            [c async for c in adapter.stream([Message(role="user", content="hi")])]
        await adapter.aclose()

        assert "上游服务不可用" in str(exc.value)

    @pytest.mark.asyncio
    async def test_error_body_is_redacted(self):

        body = '{"error": {"message": "bad key sk-SUPERSECRET1234567890"}}'

        adapter = make_adapter(lambda _: httpx.Response(200, content=body.encode()))

        with pytest.raises(LLMError) as exc:
            await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert "sk-SUPERSECRET1234567890" not in str(exc.value)
