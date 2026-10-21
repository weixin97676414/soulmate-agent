












from __future__ import annotations

import pytest

from my_agent.config.schemas import ModelsConfig, ModelSpec
from my_agent.errors import LLMAuthError, LLMError, LLMTimeoutError
from my_agent.llm.adapters.openai_compat import OpenAICompatAdapter
from my_agent.llm.base import BaseLLM, LLMResponse, Message, StreamChunk, ToolSpec
from my_agent.llm.factory import build_registry
from my_agent.llm.fallback import FallbackLLM


class FakeLLM(BaseLLM):


    def __init__(
        self,
        model_name: str = "fake",
        *,
        reply: str = "ok",
        error: BaseException | None = None,
        deltas: list[str] | None = None,
        stream_error_after: int = 0,
    ) -> None:
        super().__init__(model_name=model_name)
        self.reply = reply
        self.error = error
        self.deltas = deltas or []
        self.stream_error_after = stream_error_after
        self.chat_calls = 0
        self.stream_calls = 0
        self.closed = False

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
        self.chat_calls += 1
        if self.error is not None:
            raise self.error
        return LLMResponse(content=self.reply, finish_reason="stop")

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
    ):
        self.stream_calls += 1
        if self.error is not None:
            
            for delta in self.deltas[: self.stream_error_after]:
                yield StreamChunk(delta=delta)
            raise self.error
        for delta in self.deltas:
            yield StreamChunk(delta=delta)
        yield StreamChunk(finish_reason="stop")

    async def aclose(self) -> None:
        self.closed = True


def chain_of(primary: BaseLLM, *fallbacks: BaseLLM) -> FallbackLLM:
    return FallbackLLM(
        primary,
        list(fallbacks),
        primary_id="primary",
        fallback_ids=[f"backup-{i}" for i in range(len(fallbacks))],
    )


def user_msg() -> list[Message]:
    return [Message(role="user", content="hi")]





class TestChatFallback:
    @pytest.mark.asyncio
    async def test_healthy_primary_is_used_alone(self):
        primary = FakeLLM(reply="主模型")
        backup = FakeLLM(reply="备用")

        resp = await chain_of(primary, backup).chat(user_msg())

        assert resp.content == "主模型"
        assert backup.chat_calls == 0

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self):
        primary = FakeLLM(error=LLMTimeoutError("超时"))
        backup = FakeLLM(reply="备用回答")

        resp = await chain_of(primary, backup).chat(user_msg())

        assert resp.content == "备用回答"
        assert backup.chat_calls == 1

    @pytest.mark.asyncio
    async def test_auth_error_is_never_fallen_back(self):





        primary = FakeLLM(error=LLMAuthError("Invalid API key"))
        backup = FakeLLM(reply="备用回答")

        with pytest.raises(LLMAuthError):
            await chain_of(primary, backup).chat(user_msg())

        assert backup.chat_calls == 0

    @pytest.mark.asyncio
    async def test_all_fail_raises_the_last_error(self):
        primary = FakeLLM(error=LLMTimeoutError("超时"))
        backup = FakeLLM(error=LLMError("备用也挂了"))

        with pytest.raises(LLMError) as exc:
            await chain_of(primary, backup).chat(user_msg())

        assert "备用也挂了" in str(exc.value)

    @pytest.mark.asyncio
    async def test_tries_in_configured_order(self):
        first = FakeLLM(error=LLMError("first down"))
        second = FakeLLM(reply="second up")
        third = FakeLLM(reply="third up")

        resp = await chain_of(FakeLLM(error=LLMError("down")), first, second, third).chat(
            user_msg()
        )

        assert resp.content == "second up"
        assert third.chat_calls == 0  


class TestStreamFallback:
    @pytest.mark.asyncio
    async def test_falls_back_when_nothing_was_emitted(self):
        primary = FakeLLM(error=LLMError("down"))
        backup = FakeLLM(deltas=["备", "用"])

        chunks = [c async for c in chain_of(primary, backup).stream(user_msg())]

        assert [c.delta for c in chunks if c.delta] == ["备", "用"]
        assert backup.stream_calls == 1

    @pytest.mark.asyncio
    async def test_does_not_fall_back_after_partial_output(self):

        primary = FakeLLM(
            error=LLMError("中途断流"), deltas=["我", "来"], stream_error_after=2
        )
        backup = FakeLLM(deltas=["不一样的话"])

        received: list[StreamChunk] = []
        with pytest.raises(LLMError):
            async for chunk in chain_of(primary, backup).stream(user_msg()):
                received.append(chunk)

        assert [c.delta for c in received] == ["我", "来"]
        assert backup.stream_calls == 0

    @pytest.mark.asyncio
    async def test_healthy_stream_returns_primary_output(self):
        primary = FakeLLM(deltas=["主", "模型"])
        backup = FakeLLM(deltas=["备用"])

        chunks = [c async for c in chain_of(primary, backup).stream(user_msg())]

        assert [c.delta for c in chunks if c.delta] == ["主", "模型"]
        assert backup.stream_calls == 0


class TestChainShape:
    def test_describe_chain(self):
        llm = chain_of(FakeLLM(), FakeLLM(), FakeLLM())
        assert llm.describe_chain() == ["backup-0", "backup-1"]

    def test_empty_fallbacks_is_allowed(self):

        llm = chain_of(FakeLLM())
        assert llm.describe_chain() == []

    def test_mismatched_ids_are_rejected(self):
        with pytest.raises(ValueError):
            FallbackLLM(FakeLLM(), [FakeLLM()], primary_id="p", fallback_ids=[])

    @pytest.mark.asyncio
    async def test_aclose_closes_every_member(self):
        primary = FakeLLM()
        backup = FakeLLM()
        llm = chain_of(primary, backup)

        await llm.aclose()

        assert primary.closed and backup.closed





def _two_model_config() -> ModelsConfig:
    return ModelsConfig(
        default_model="a",
        models=[
            ModelSpec(
                id="a", model_name="mA", adapter="openai_compat",
                base_url="https://a.example.com/v1", api_key="k",
                fallback_models=["b"],
            ),
            ModelSpec(
                id="b", model_name="mB", adapter="openai_compat",
                base_url="https://b.example.com/v1", api_key="k",
                fallback_models=["a"],  
            ),
        ],
    )


class TestFactoryBuilding:
    def test_chain_is_built_from_config(self):
        registry = build_registry(_two_model_config())
        llm = registry.get("a")

        assert isinstance(llm, FallbackLLM)
        assert llm.describe_chain() == ["b"]

    def test_chain_is_flat_to_prevent_cycles(self):

        registry = build_registry(_two_model_config())

        chain = registry.get("a")
        assert isinstance(chain, FallbackLLM)
        backup = chain._fallbacks[0]

        assert isinstance(backup, OpenAICompatAdapter)
        assert not isinstance(backup, FallbackLLM)

    def test_self_reference_is_dropped(self):
        config = ModelsConfig(
            models=[
                ModelSpec(
                    id="solo", model_name="m", adapter="openai_compat",
                    base_url="https://s.example.com/v1", api_key="k",
                    fallback_models=["solo", "ghost"],  
                )
            ]
        )

        llm = build_registry(config).get("solo")

        
        assert isinstance(llm, OpenAICompatAdapter)
        assert not isinstance(llm, FallbackLLM)

    def test_default_is_no_fallback(self):

        spec = ModelSpec(id="x", model_name="mX", base_url="https://x.example.com/v1")
        assert spec.fallback_models == []

    def test_duplicate_and_forward_references(self):

        registry = build_registry(_two_model_config())

        assert isinstance(registry.get("b"), FallbackLLM)
        assert registry.get("b").describe_chain() == ["a"]
