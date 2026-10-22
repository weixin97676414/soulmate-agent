


















from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRICE_UNIT = 1_000_000


def _first_int(*values: Any) -> int:





    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


@dataclass
class Usage:


    prompt_tokens: int = 0
    completion_tokens: int = 0
    
    cached_tokens: int = 0
    
    cache_write_tokens: int = 0
    
    reasoning_tokens: int = 0
    
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def billable_input_tokens(self) -> int:

        return max(self.prompt_tokens - self.cached_tokens, 0)

    @property
    def hit_rate(self) -> float | None:

        if self.prompt_tokens <= 0:
            return None
        return self.cached_tokens / self.prompt_tokens

    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0 and self.cached_tokens == 0

    def add(self, other: Usage) -> None:

        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.reasoning_tokens += other.reasoning_tokens

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
        }
        if self.cache_write_tokens:
            data["cache_write_tokens"] = self.cache_write_tokens
        if self.reasoning_tokens:
            data["reasoning_tokens"] = self.reasoning_tokens
        rate = self.hit_rate
        if rate is not None:
            data["cache_hit_rate"] = round(rate, 4)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Usage:
        if not data:
            return cls()
        return cls(
            prompt_tokens=_first_int(data.get("prompt_tokens")),
            completion_tokens=_first_int(data.get("completion_tokens")),
            cached_tokens=_first_int(data.get("cached_tokens")),
            cache_write_tokens=_first_int(data.get("cache_write_tokens")),
            reasoning_tokens=_first_int(data.get("reasoning_tokens")),
        )


def normalize_usage(usage: dict[str, Any] | None) -> Usage:






    if not isinstance(usage, dict) or not usage:
        return Usage()

    prompt_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    completion_details = usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = {}

    
    prompt = _first_int(usage.get("prompt_tokens"), usage.get("input_tokens"))
    completion = _first_int(usage.get("completion_tokens"), usage.get("output_tokens"))

    cached = _first_int(
        usage.get("prompt_cache_hit_tokens"),  
        usage.get("cache_read_input_tokens"),  
        prompt_details.get("cached_tokens"),  
        prompt_details.get("cache_hit_tokens"),  
        usage.get("cached_tokens"),  
    )
    
    
    if prompt > 0:
        cached = min(cached, prompt)

    cache_write = _first_int(
        usage.get("cache_creation_input_tokens"),  
        prompt_details.get("cache_creation_tokens"),
    )

    reasoning = _first_int(
        completion_details.get("reasoning_tokens"),
        usage.get("reasoning_tokens"),
    )

    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_tokens=cached,
        cache_write_tokens=cache_write,
        reasoning_tokens=reasoning,
        raw=dict(usage),
    )





@dataclass
class PriceSpec:


    input: float | None = None
    cached_input: float | None = None
    cache_write: float | None = None
    output: float | None = None


def estimate_cost(usage: Usage, price: PriceSpec) -> float | None:












    if price.input is None or price.output is None:
        return None

    cached_price = price.input if price.cached_input is None else price.cached_input
    write_price = price.input if price.cache_write is None else price.cache_write

    total = (
        usage.billable_input_tokens / PRICE_UNIT * price.input
        + usage.cached_tokens / PRICE_UNIT * cached_price
        + usage.cache_write_tokens / PRICE_UNIT * write_price
        + usage.completion_tokens / PRICE_UNIT * price.output
    )
    
    return round(total, 6)
