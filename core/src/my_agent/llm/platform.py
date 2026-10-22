






























from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformProfile:






    name: str
    
    
    thinking: ThinkingStrategy = field(default_factory=lambda: reasoning_effort_style())
    
    temperature_range: tuple[float, float] | None = (0.0, 2.0)
    top_p_range: tuple[float, float] | None = (0.0, 1.0)
    
    stream_usage: bool = True
    
    max_tokens_field: str = "max_tokens"
    
    supports_penalties: bool = True
    
    supports_parallel_tools: bool = True



THINKING_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class ThinkingStrategy:




















    kind: str
    fields: dict[str, dict[str, Any]]

    def payload_for(self, level: str | None) -> dict[str, Any]:

        if not level:
            return {}
        return dict(self.fields.get(level) or {})

    def supports(self, level: str | None) -> bool:
        return bool(level) and level in self.fields


def reasoning_effort_style(kind: str = "reasoning_effort") -> ThinkingStrategy:

    return ThinkingStrategy(
        kind=kind,
        fields={level: {"reasoning_effort": level} for level in THINKING_LEVELS},
    )


def dashscope_style() -> ThinkingStrategy:





    return ThinkingStrategy(
        kind="enable_thinking+thinking_budget",
        fields={
            "low": {"enable_thinking": True, "thinking_budget": 1024},
            "medium": {"enable_thinking": True, "thinking_budget": 8192},
            "high": {"enable_thinking": True, "thinking_budget": 32768},
        },
    )


def zhipu_style() -> ThinkingStrategy:





    return ThinkingStrategy(
        kind="thinking.type",
        fields={
            "low": {"thinking": {"type": "disabled"}},
            "medium": {"thinking": {"type": "enabled"}},
            "high": {"thinking": {"type": "enabled"}},
        },
    )


def openrouter_style() -> ThinkingStrategy:







    return ThinkingStrategy(
        kind="reasoning.effort",
        fields={level: {"reasoning": {"effort": level}} for level in THINKING_LEVELS},
    )










THINKING_FIELD_NAMES = frozenset(
    {"reasoning_effort", "enable_thinking", "thinking_budget", "thinking", "reasoning"}
)


def clamp(value: float, bounds: tuple[float, float] | None) -> float | None:






    if bounds is None:
        return None
    low, high = bounds
    return max(low, min(high, value))







_PROFILES: tuple[tuple[tuple[str, ...], PlatformProfile], ...] = (
    (
        ("api.openai.com",),
        PlatformProfile(
            name="openai",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            
            
            
            max_tokens_field="max_tokens",
        ),
    ),
    (
        ("api.deepseek.com",),
        PlatformProfile(
            name="deepseek",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            
            
        ),
    ),
    (
        ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"),
        PlatformProfile(
            name="dashscope",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            supports_penalties=False,
            
            thinking=dashscope_style(),
        ),
    ),
    (
        
        
        
        
        
        
        
        ("open.bigmodel.cn",),
        PlatformProfile(
            name="zhipu",
            
            temperature_range=(0.01, 1.0),
            stream_usage=True,
            supports_penalties=False,
            
            thinking=zhipu_style(),
        ),
    ),
    (
        ("api.moonshot.cn", "api.moonshot.ai"),
        PlatformProfile(
            name="moonshot",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        ("ark.cn-beijing.volces.com", "ark.ap-southeast.volces.com"),
        PlatformProfile(
            name="volcengine",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
            
            
            
            thinking=zhipu_style(),
        ),
    ),
    (
        ("api.siliconflow.cn", "api.siliconflow.com"),
        PlatformProfile(
            name="siliconflow",
            temperature_range=(0.0, 2.0),
            
            
            
            
            
            
            
            
            thinking=reasoning_effort_style(),
        ),
    ),
    
    
    
    
    
    
    (
        ("api.minimaxi.com", "api.minimax.chat"),
        PlatformProfile(
            name="minimax",
            
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        ("api.hunyuan.cloud.tencent.com",),
        PlatformProfile(
            name="hunyuan",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        ("qianfan.baidubce.com",),
        PlatformProfile(
            name="qianfan",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        ("api.stepfun.com", "api.stepfun.ai"),
        PlatformProfile(
            name="stepfun",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        
        ("generativelanguage.googleapis.com",),
        PlatformProfile(
            name="gemini",
            
            temperature_range=(0.0, 2.0),
            stream_usage=True,
        ),
    ),
    (
        ("api.x.ai",),
        PlatformProfile(
            name="xai",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
        ),
    ),
    (
        ("openrouter.ai",),
        PlatformProfile(
            name="openrouter",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
            
            thinking=openrouter_style(),
        ),
    ),
    (
        ("api.groq.com",),
        PlatformProfile(
            name="groq",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        ("api.mistral.ai",),
        PlatformProfile(
            name="mistral",
            temperature_range=(0.0, 1.0),
            stream_usage=True,
        ),
    ),
    (
        
        ("localhost", "127.0.0.1", "0.0.0.0", "::1"),
        PlatformProfile(
            name="local",
            temperature_range=(0.0, 2.0),
            
            
        ),
    ),
)












DEFAULT_PROFILE = PlatformProfile(
    name="generic",
    temperature_range=(0.0, 1.0),  
    stream_usage=True,
    
    
    
    
    
    
    
    
    
    
    
    
    supports_penalties=True,
)


def detect_profile(base_url: str) -> PlatformProfile:

    try:
        host = (urlparse(base_url).hostname or "").strip().lower()
    except ValueError:
        return DEFAULT_PROFILE

    if not host:
        return DEFAULT_PROFILE

    for hosts, profile in _PROFILES:
        for candidate in hosts:
            
            if host == candidate or host.endswith(f".{candidate}"):
                return profile

    return DEFAULT_PROFILE











_UNSUPPORTED_PARAM_HINTS = (
    "unknown parameter",
    "unsupported parameter",
    "invalid parameter",
    "not supported",
    "unrecognized request argument",
    "extra inputs are not permitted",  
)


def extract_unsupported_param(body: str) -> str | None:





    lowered = body.lower()
    if not any(hint in lowered for hint in _UNSUPPORTED_PARAM_HINTS):
        return None

    
    
    probe_text = lowered.replace("\\", "")

    
    for param in _ADAPTIVE_PARAMS:
        for probe in (f"'{param}'", f'"{param}"', f"{param}:", f"{param} "):
            if probe in probe_text:
                return param

    
    
    
    for param in _ADAPTIVE_PARAMS:
        if re.search(rf"\b{re.escape(param)}\b", probe_text):
            return param

    
    return ""



_ADAPTIVE_PARAMS = (
    "stream_options",
    "include_usage",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "max_tokens",
    "tools",
    
    
    "reasoning_effort",
    "enable_thinking",
    "thinking_budget",
    "thinking",
    "reasoning",
)


@dataclass
class AdaptiveFallbacks:






    disabled: set[str] = field(default_factory=set)

    def disable(self, param: str) -> bool:

        if param in self.disabled:
            return False
        self.disabled.add(param)
        logger.info("自适应禁用不被 %s 支持的参数，已重试", param)
        return True

    def enabled(self, param: str) -> bool:
        return param not in self.disabled


def looks_like_error_payload(data: Any) -> str | None:









    if not isinstance(data, dict):
        return None

    
    if data.get("choices") is not None:
        return None

    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("msg") or error.get("type")
        if message:
            return str(message)
    elif isinstance(error, str) and error:
        return error

    
    code = data.get("code")
    message = data.get("message")
    if isinstance(message, str) and message and code not in (None, 0, "0", 200, "200"):
        return message

    return None
