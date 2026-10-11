"""LLM 用量（usage）归一化与费用估算。

各家厂商返回的字段名不一样，但语义就那么几个。这里把原始 usage 统一成
一个内部结构，上层（Tracer / 落库 / 费用估算 / 界面展示）只认这一份。

## 为什么必须把「缓存命中」单独拎出来

- **DeepSeek**：命中价约为未命中的 **1/10**，字段是 ``prompt_cache_hit_tokens``
- **OpenAI**：缓存输入约 **5 折**，字段在 ``prompt_tokens_details.cached_tokens``
- **Anthropic**：读约 **1 折**、写约 **1.25 倍**，字段是
  ``cache_read_input_tokens`` / ``cache_creation_input_tokens``
- 其余 OpenAI 兼容厂商（Kimi / 智谱 / 豆包 / 通义）多为自动前缀缓存，
  字段名各异（``cached_tokens`` / ``prompt_cache_hit_tokens`` 都有见过）

不区分命中与否，算出来的费用会**高出好几倍**，用户会直接认为统计是错的。
更要紧的是：没有这个指标，就无法验证「前缀缓存优化是否真的生效」——
而那是本项目里最大的一块成本优化（见 ``agent/prompts.py`` 的说明）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 单位：每百万 token 的价格。厂商报价基本都是这个量纲。
PRICE_UNIT = 1_000_000


def _first_int(*values: Any) -> int:
    """取第一个能转成整数的值。

    厂商偶尔会把 token 数写成字符串或浮点，直接 int() 会炸掉整条统计链路，
    所以这里一律走"尽力转换"，失败就当 0。
    """
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
    """一次（或累计若干次）模型调用的用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    # 走缓存命中的输入 token（价更低）
    cached_tokens: int = 0
    # 写入缓存的开销（目前只有 Anthropic 显式缓存会产生）
    cache_write_tokens: int = 0
    # 推理模型的思考 token（通常已包含在 completion_tokens 里，仅用于展示）
    reasoning_tokens: int = 0
    # 保留原始 dict，排错时能直接看到厂商到底回了什么
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def billable_input_tokens(self) -> int:
        """按**未命中**价计费的输入 token 数。"""
        return max(self.prompt_tokens - self.cached_tokens, 0)

    @property
    def hit_rate(self) -> float | None:
        """缓存命中率。没有输入 token 时返回 None（而不是 0，避免误导）。"""
        if self.prompt_tokens <= 0:
            return None
        return self.cached_tokens / self.prompt_tokens

    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0 and self.cached_tokens == 0

    def add(self, other: Usage) -> None:
        """把另一次调用的用量累加进来（一次对话会有多轮）。"""
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
    """把厂商返回的原始 usage 归一化成 :class:`Usage`。

    字段探测顺序按「谁的语义最明确」排，不按厂商流行度：
    ``prompt_cache_hit_tokens`` 是 DeepSeek 的专用字段，语义无歧义；
    ``cached_tokens`` 太通用，可能有厂商拿它表示别的东西，所以排在后面。
    """
    if not isinstance(usage, dict) or not usage:
        return Usage()

    prompt_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    completion_details = usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = {}

    # 输入总量：OpenAI 系叫 prompt_tokens，Anthropic 系叫 input_tokens
    prompt = _first_int(usage.get("prompt_tokens"), usage.get("input_tokens"))
    completion = _first_int(usage.get("completion_tokens"), usage.get("output_tokens"))

    cached = _first_int(
        usage.get("prompt_cache_hit_tokens"),  # DeepSeek
        usage.get("cache_read_input_tokens"),  # Anthropic
        prompt_details.get("cached_tokens"),  # OpenAI
        prompt_details.get("cache_hit_tokens"),  # 部分网关
        usage.get("cached_tokens"),  # 其他兼容实现
    )
    # 防御：命中量不可能超过输入总量。某些网关在流式末帧会把两者都报一遍，
    # 不加这道限制会算出"命中率 180%"这种一眼假的数据。
    if prompt > 0:
        cached = min(cached, prompt)

    cache_write = _first_int(
        usage.get("cache_creation_input_tokens"),  # Anthropic
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


# --------------------------------------------------------------------------- #
# 费用估算
# --------------------------------------------------------------------------- #
@dataclass
class PriceSpec:
    """每百万 token 的单价。任何一项没配就用保守策略（见 estimate_cost）。"""

    input: float | None = None
    cached_input: float | None = None
    cache_write: float | None = None
    output: float | None = None


def estimate_cost(usage: Usage, price: PriceSpec) -> float | None:
    """估算费用；价格没配全时返回 ``None``。

    **刻意不内置任何默认价**：厂商调价频繁，写死会让界面显示一个错误金额，
    而用户看到"费用"两个字就会当真。宁可显示"未配置价格"，
    也不要给出一个看起来很精确的错数字。

    另外两条保守策略：

    - ``cached_input`` 没填时**不打折**（按未命中价算）。缓存折扣各家不同，
      猜一个反而会低估；不打折只会高估，用户不会被"少算"误导。
    - 价格全部按每 **百万** token 计，与厂商报价单一致，避免换算错位。
    """
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
    # 保留 6 位小数：单次对话常常只有几分钱，四舍五入到 2 位会全变成 0.00
    return round(total, 6)
