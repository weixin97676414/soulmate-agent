"""平台策略：抹平厂商之间的协议差异。

《智能体框架开发文档》要求多模型接入要处理厂商差异。这组用例覆盖三件事：

1. **静态 Profile** —— 已知厂商的参数边界（例如智谱的 temperature 是 0~1）；
2. **自适应回退** —— 未知网关第一次报 ``Unknown parameter`` 时能自己好过来；
3. **HTTP 200 包裹错误** —— 网关返回 200 但内容其实是失败。

后两项只在真实网络里才会遇到，而且**失败形态都极具误导性**
（第 3 项尤其：不处理的话会抛出一个和真实原因毫无关系的解析异常），
所以用 MockTransport 把行为钉住。
"""

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


# --------------------------------------------------------------------------- #
# 静态 Profile
# --------------------------------------------------------------------------- #
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
        # 用户的自建网关 / 代理聚合 / OpenRouter，我们枚举不完
        assert detect_profile("https://llm.mycompany.internal/v1") is DEFAULT_PROFILE

    def test_subdomain_still_matches(self):
        """按后缀匹配：厂商的备用域名与区域域名都该命中。"""
        assert detect_profile("https://gateway.dashscope.aliyuncs.com/v1").name == "dashscope"

    def test_malformed_url_is_safe(self):
        assert detect_profile("这不是一个 URL") is DEFAULT_PROFILE
        assert detect_profile("") is DEFAULT_PROFILE

    def test_generic_profile_accepts_default_temperature(self):
        """兜底 Profile 必须允许常规温度值，否则默认配置下谁都用不了。"""
        assert clamp(0.7, DEFAULT_PROFILE.temperature_range) == 0.7


class TestClamp:
    def test_value_within_range_is_unchanged(self):
        assert clamp(0.7, (0.0, 2.0)) == 0.7

    def test_above_range_is_clipped(self):
        """智谱上限是 1：直接透传会被拒，截到边界至少能用。"""
        assert clamp(1.5, (0.01, 1.0)) == 1.0

    def test_below_range_is_clipped(self):
        assert clamp(0.0, (0.01, 1.0)) == 0.01

    def test_none_range_means_unsupported(self):
        """推理模型完全不接受采样参数 —— 返回 None 让调用方整个字段都不发。

        这里必须返回 None 而不是 0.7：这类模型哪怕收到默认值也会 400。
        """
        assert clamp(0.7, None) is None


# --------------------------------------------------------------------------- #
# 自适应回退
# --------------------------------------------------------------------------- #
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
        """别把鉴权失败、模型不存在当成参数问题，否则会重试三次再报无关错误。"""
        for body in (
            "Invalid API key provided",
            "The model does not exist",
            "Rate limit reached for requests",
        ):
            assert extract_unsupported_param(body) is None

    def test_unidentifiable_field_returns_empty_string(self):
        """确实是不支持参数、但定位不到具体字段：返回空串，调用方据此**不**自愈。"""
        assert extract_unsupported_param("Unknown parameter supplied") == ""

    def test_never_returns_unknown_field_name(self):
        """只会返回我们确实会发送的参数名。

        没有这道约束的话，厂商错误信息里的任意字符串都会被当成参数名去"禁用"，
        结果什么都没修好，还白白重试一轮。
        """
        assert extract_unsupported_param("Unknown parameter: 'ssrf_token'") == ""


class TestAdaptiveFallbacks:
    def test_first_disable_signals_retry(self):
        fb = AdaptiveFallbacks()
        assert fb.disable("stream_options") is True

    def test_second_disable_returns_false(self):
        """同一个参数第二次不该再触发重试 —— 否则会陷入重试直到耗尽配额。"""
        fb = AdaptiveFallbacks()
        fb.disable("stream_options")
        assert fb.disable("stream_options") is False

    def test_enabled_reflects_state(self):
        fb = AdaptiveFallbacks()
        assert fb.enabled("temperature") is True
        fb.disable("temperature")
        assert fb.enabled("temperature") is False


# --------------------------------------------------------------------------- #
# HTTP 200 包裹错误
# --------------------------------------------------------------------------- #
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
            {"choices": []},  # 空 choices 也是"响应成功"
            {"usage": {"prompt_tokens": 1}},  # 流式最后的 usage 分片
            {"code": 200, "message": "ok"},
            "not even a dict",
            None,
        ],
    )
    def test_leaves_normal_responses_alone(self, data):
        assert looks_like_error_payload(data) is None


# --------------------------------------------------------------------------- #
# 适配器集成
# --------------------------------------------------------------------------- #
class TestPayloadRespectsProfile:
    def test_temperature_is_clamped_for_strict_vendors(self):
        adapter = make_adapter(lambda _: ok_text_reply(), base_url="https://open.bigmodel.cn/v4")

        payload = adapter._build_payload([], None, 1.5, None, stream=False)

        assert payload["temperature"] == 1.0  # 智谱上限

    def test_temperature_is_omitted_for_reasoning_models(self):
        """完全不接受采样参数时必须整字段消失，而不是传默认值。"""
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
        """网关报 ``Unknown parameter`` 后应当自动去掉该字段再试一次并成功。

        这里用 ``temperature`` 而不是 ``stream_options``：非流式请求本**就不带**
        stream_options，用它测等于什么都没测。
        """
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
        assert "temperature" not in calls[1]  # 第二次不再携带

    @pytest.mark.asyncio
    async def test_auth_failure_is_not_retried_as_parameter_error(self):
        """鉴权失败不能走参数自愈 —— 否则会重试一轮再报一个无关的错。"""
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
        """HTTP 200 但内容是错误 —— 不处理会在解析时抛出毫不相关的异常。"""

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"message": "账户余额不足"}})

        adapter = make_adapter(handler)

        with pytest.raises(LLMError) as exc:
            await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert "账户余额不足" in str(exc.value)

    @pytest.mark.asyncio
    async def test_stream_raises_readable_error(self):
        """错误夹在流中间的情况。"""
        sse = 'data: {"error": {"message": "上游服务不可用"}}\n\ndata: [DONE]\n\n'

        adapter = make_adapter(lambda _: httpx.Response(200, content=sse.encode()))

        with pytest.raises(LLMError) as exc:
            [c async for c in adapter.stream([Message(role="user", content="hi")])]
        await adapter.aclose()

        assert "上游服务不可用" in str(exc.value)

    @pytest.mark.asyncio
    async def test_error_body_is_redacted(self):
        """厂商可能把请求回显出来（含 Authorization），错误信息不能直接拼原始响应体。"""
        body = '{"error": {"message": "bad key sk-SUPERSECRET1234567890"}}'

        adapter = make_adapter(lambda _: httpx.Response(200, content=body.encode()))

        with pytest.raises(LLMError) as exc:
            await adapter.chat([Message(role="user", content="hi")])
        await adapter.aclose()

        assert "sk-SUPERSECRET1234567890" not in str(exc.value)
