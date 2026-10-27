





from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any






@dataclass
class ToolSpec:


    name: str
    description: str
    parameters: dict[str, Any]  
    type: str = "function"


@dataclass
class ToolCall:


    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_openai(self) -> dict[str, Any]:





        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.raw_arguments or dump_arguments(self.arguments),
            },
        }


@dataclass
class ImagePart:











    mime: str = "image/png"
    data_url: str = field(default="", repr=False)
    
    name: str = ""


@dataclass
class Message:


    role: str  
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    
    reasoning_content: str = ""
    
    
    
    
    
    
    images: list[ImagePart] = field(default_factory=list)
    
    
    
    
    
    injection_hits: list[str] = field(default_factory=list)
    
    
    
    
    
    
    
    
    
    
    
    
    created_at: float | None = None
    
    
    
    
    
    
    
    
    plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.name:
            data["name"] = self.name
        
        if self.images:
            data["images"] = len(self.images)
        if self.injection_hits:
            data["injection_hits"] = list(self.injection_hits)
        return data

    def has_images(self) -> bool:
        return bool(self.images)


@dataclass
class LLMResponse:


    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    reasoning_content: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


@dataclass
class StreamChunk:






    delta: str = ""
    reasoning_delta: str = ""
    tool_calls: list[ToolCall] | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None

    @property
    def is_final(self) -> bool:
        return self.finish_reason is not None







def dump_arguments(args: dict[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False)


def load_arguments(raw: str | None) -> dict[str, Any]:





    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}





class _NullLease:


    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


_NULL_LEASE = _NullLease()


async def _leased(lease: Any, source: AsyncIterator[StreamChunk]) -> AsyncIterator[StreamChunk]:





    async with lease:
        async for chunk in source:
            yield chunk


class BaseLLM(ABC):


    def __init__(
        self,
        *,
        model_name: str,
        supports_tools: bool = True,
        supports_stream: bool = True,
        supports_reasoning: bool = True,
        
        
        supports_vision: bool = False,
        token_limit: int = 32768,
    ) -> None:
        self.model_name = model_name
        self.supports_vision = supports_vision
        
        
        
        
        
        
        self._lease_factory: Any = None
        self.supports_tools = supports_tools
        self.supports_stream = supports_stream
        
        
        
        
        
        
        
        
        
        self.supports_reasoning = supports_reasoning
        self._token_limit = token_limit

    @property
    def token_limit(self) -> int:

        return self._token_limit

    @abstractmethod
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
        pass

    @abstractmethod
    def stream(
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
        pass














    def set_lease_factory(self, factory: Any) -> None:

        self._lease_factory = factory

    def lease(self) -> Any:

        if self._lease_factory is None:
            return _NULL_LEASE
        return self._lease_factory()

    def leased_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:











        return _leased(self.lease(), self.stream(*args, **kwargs))

    async def list_models(self) -> list[str]:

        raise NotImplementedError

    async def aclose(self) -> None:

        return None
