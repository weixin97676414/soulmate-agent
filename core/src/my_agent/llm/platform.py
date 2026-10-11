"""平台策略：抹平厂商之间的协议差异。

对应《智能体框架开发文档》4.x「多模型接入」里提到的厂商适配要求。

## 为什么需要这一层

"OpenAI 兼容"是一个**目标**，不是保证。各厂商/网关几乎一定在下面几处有差异，
而每一处差异的失败形态都不是"降级"，而是**直接报错**：

| 差异点 | 不支持时的表现 |
|---|---|
| ``stream_options.include_usage`` | 返回 400 ``Unknown parameter``，整个流式请求失败 |
| ``temperature`` 取值范围 | 超范围被拒（智谱/月之暗面是 0~1，OpenAI 是 0~2） |
| 推理模型不接受采样参数 | 带 ``temperature`` 直接 400 |
| ``max_tokens`` / ``max_completion_tokens`` | 新模型换了字段名 |
| HTTP 200 包裹错误 | 网关把错误放进 ``{"error": {...}}`` 却返回 200，按状态码判成功，最后在解析时抛出一个与真实原因毫无关系的异常 |

## 策略：静态 Profile + 自适应回退

**只做静态表不够** —— 用户会填自己的网关、代理聚合（OpenRouter / one-api 之类），
我们枚举不完。**只做自适应也不好** —— 每次都让厂商先报错再退，
等于每个会话首轮都白扔一次请求（还要多花几百毫秒到几秒）。

两者结合：

- **已知厂商**按表走，第一次请求参数就是对的；
- **未知网关**第一次报 ``Unknown parameter`` 时记下来并永久禁用该参数，自动重试一次。

默认 Profile 是**保守**的：宁可少用某个可选能力，也不要因为多发一个字段而整体失败。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformProfile:
    """一个厂商/网关的协议特性。

    这里的每个字段都是"从适配角度必须区分"的差异，而不是厂商的功能宣传。
    留空/取默认值意味着"按 OpenAI 官方行为处理"。
    """

    name: str
    # "思考强度"（低/中/高）在这家要写成什么字段。见 ThinkingStrategy 的说明 ——
    # 这是"设了档位却没生效"那个问题的根因所在。
    thinking: ThinkingStrategy = field(default_factory=lambda: reasoning_effort_style())
    # 采样参数：``None`` 表示**完全不接受**该参数（推理模型的典型行为）
    temperature_range: tuple[float, float] | None = (0.0, 2.0)
    top_p_range: tuple[float, float] | None = (0.0, 1.0)
    # 是否支持 stream_options.include_usage（拿不到 usage 就无法统计费用与缓存命中率）
    stream_usage: bool = True
    # max_tokens 的字段名：新版 OpenAI 用 max_completion_tokens
    max_tokens_field: str = "max_tokens"
    # 是否支持 frequency_penalty / presence_penalty
    supports_penalties: bool = True
    # 是否支持并行工具调用（一次返回多个 tool_call）
    supports_parallel_tools: bool = True


#: 统一的档位取值（与前端控件、会话字段一致）
THINKING_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class ThinkingStrategy:
    """把统一的 low/medium/high 翻译成**这家真正认的**请求字段。

    ## 为什么必须有这一层

    "思考强度"在我们这边是一个档位，但在厂商那边**没有统一的名字**：
    OpenAI 是 ``reasoning_effort``；通义/DashScope 是 ``enable_thinking`` +
    ``thinking_budget``；智谱是 ``thinking``；Anthropic 是 ``thinking.budget_tokens``。

    我们以前一律按 OpenAI 的写法发 ``reasoning_effort``，于是**除 OpenAI 之外的
    厂商会静默忽略它**。用户看到的现象就是"思考程度设了但没生效"——
    而静默是这个 bug 里最难受的部分：请求成功、回答正常，只是那个开关什么都没干，
    用户完全无从判断是"没生效"还是"这个模型就是这样"。

    ``fields`` 的键是**请求体的字段名**，值是那一档要写入的内容；一个档位可以
    同时写多个字段（DashScope 就是布尔 + 预算两个一起）。

    默认为 OpenAI 风格：多数 OpenAI 兼容网关都实现了 ``reasoning_effort``，
    而万一某家不认，``AdaptiveFallbacks`` 会在收到 400 后禁用它并重试一次。
    """

    kind: str
    fields: dict[str, dict[str, Any]]

    def payload_for(self, level: str | None) -> dict[str, Any]:
        """取某一档要写入请求体的字段；没有这一档就返回空（发送方应视为"不发"）。"""
        if not level:
            return {}
        return dict(self.fields.get(level) or {})

    def supports(self, level: str | None) -> bool:
        return bool(level) and level in self.fields


def reasoning_effort_style(kind: str = "reasoning_effort") -> ThinkingStrategy:
    """OpenAI 风格：一个字符串字段取 low/medium/high。"""
    return ThinkingStrategy(
        kind=kind,
        fields={level: {"reasoning_effort": level} for level in THINKING_LEVELS},
    )


def dashscope_style() -> ThinkingStrategy:
    """通义千问 / DashScope：``enable_thinking`` + ``thinking_budget``。

    它的"强度"是靠**预算 token 数**表达的，没有 low/medium/high 这种字面值 ——
    这也正是"发 reasoning_effort 过去被忽略"的原因。
    """
    return ThinkingStrategy(
        kind="enable_thinking+thinking_budget",
        fields={
            "low": {"enable_thinking": True, "thinking_budget": 1024},
            "medium": {"enable_thinking": True, "thinking_budget": 8192},
            "high": {"enable_thinking": True, "thinking_budget": 32768},
        },
    )


def zhipu_style() -> ThinkingStrategy:
    """智谱 GLM：``thinking`` 对象，**只有开关、没有档位**。

    ``low`` 映射成关闭是刻意的：既然它表达不了"想一点"，那"低"最接近的
    语义就是"不要多花这份预算"，而不是"假装开了但没区别"。
    """
    return ThinkingStrategy(
        kind="thinking.type",
        fields={
            "low": {"thinking": {"type": "disabled"}},
            "medium": {"thinking": {"type": "enabled"}},
            "high": {"thinking": {"type": "enabled"}},
        },
    )


def openrouter_style() -> ThinkingStrategy:
    """OpenRouter：归一化的 ``reasoning.effort`` 对象。

    OpenRouter 是个**聚合网关**（背后可能是任何一家），它自己给了一个统一写法
    ``reasoning: {"effort": "low"|"medium"|"high"}``。用它而不是 ``reasoning_effort``：
    后者只是它对部分后端做透传时的巧合，依赖透传等于把"档位生效"押在
    "它恰好代理了一家认这个字段的厂商"上 —— 而在聚合网关上是**猜不到**的。
    """
    return ThinkingStrategy(
        kind="reasoning.effort",
        fields={level: {"reasoning": {"effort": level}} for level in THINKING_LEVELS},
    )


#: 各家"思考强度"实际会写进请求体的**顶层字段名**（见上面那几个 ``*_style``）。
#:
#: ⚠️ 这份名单的用途是**让自适应回退救得回来**：厂商回一句
#: ``Unknown parameter: 'thinking'`` 时，``extract_unsupported_param`` 只会在
#: ``_ADAPTIVE_PARAMS`` 里找名字 —— 名单里没有它，就定位不到、禁不掉，
#: 于是重试又带着同一个字段再失败一次。用户看到的是**整条对话报错**，
#: 而不是我们承诺的"档位静默失效、对话照常"。
#: 有一条单测与一条打包闸同时钉着"这份名单必须 ⊆ ``_ADAPTIVE_PARAMS``"。
THINKING_FIELD_NAMES = frozenset(
    {"reasoning_effort", "enable_thinking", "thinking_budget", "thinking", "reasoning"}
)


def clamp(value: float, bounds: tuple[float, float] | None) -> float | None:
    """把参数压到目标区间内。

    返回 ``None`` 表示这个厂商**不接受**该参数，调用方应当整个字段都不发送 ——
    注意这和"传默认值"完全不同：接受 ``temperature`` 的模型拿到 0.7 会正常工作，
    而不接受它的推理模型哪怕收到 0.7 也会直接 400。
    """
    if bounds is None:
        return None
    low, high = bounds
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# 已知厂商
# --------------------------------------------------------------------------- #
# 按 base_url 的**主机名后缀**匹配。用后缀而不是精确相等，是为了兼容
# 各家的备用域名、区域域名与用户自建的反向代理。
_PROFILES: tuple[tuple[tuple[str, ...], PlatformProfile], ...] = (
    (
        ("api.openai.com",),
        PlatformProfile(
            name="openai",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            # gpt-5 / o 系新模型用 max_completion_tokens；旧的仍接受 max_tokens。
            # 这里保守沿用 max_tokens —— 它对绝大多数模型仍然有效，
            # 而 max_completion_tokens 对老模型会直接 400。
            max_tokens_field="max_tokens",
        ),
    ),
    (
        ("api.deepseek.com",),
        PlatformProfile(
            name="deepseek",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            # DeepSeek 的磁盘缓存是**自动前缀命中**，不需要任何 Cache-Control 标记，
            # 只要别破坏前缀就行（见 agent/prompts.py 里的说明）
        ),
    ),
    (
        ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"),
        PlatformProfile(
            name="dashscope",
            temperature_range=(0.0, 2.0),
            stream_usage=True,
            supports_penalties=False,
            # 通义不认 reasoning_effort，它的思考强度是"预算 token 数"
            thinking=dashscope_style(),
        ),
    ),
    (
        # ⚠️ 只留域名（第 91 批，L-05）：这里原本还有第二个候选
        # `"open.bigmodel.cn/api/paas"`，而 `detect_profile` 比的是
        # `urlparse(base_url).hostname`（见下面的 :400-416）—— 带路径的候选
        # **永远不可能匹配**（hostname 里不会有路径）。它是死条目，
        # 而且会让人误以为"路径也参与判定"、照着再写几条。
        # 用户把 base_url 填成 `https://open.bigmodel.cn/api/paas/v4` 时，
        # hostname 仍是 `open.bigmodel.cn`，这一条本来就命中。
        ("open.bigmodel.cn",),
        PlatformProfile(
            name="zhipu",
            # 智谱的合法区间是 (0, 1] —— 传 0 或 >1 都会被拒
            temperature_range=(0.01, 1.0),
            stream_usage=True,
            supports_penalties=False,
            # 智谱的思考开关是 thinking 对象，没有 low/medium/high
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
            # 豆包（火山方舟）的思考是 ``thinking`` 对象（enabled/disabled），
            # 与智谱**同形状**，所以直接复用那套：低=关闭、中/高=开启。
            # 它表达不了"想一点"，把"低"映射成关闭比"假装开了但没区别"诚实。
            thinking=zhipu_style(),
        ),
    ),
    (
        ("api.siliconflow.cn", "api.siliconflow.com"),
        PlatformProfile(
            name="siliconflow",
            temperature_range=(0.0, 2.0),
            # 硅基流动是标准的 OpenAI 兼容网关，思考强度就走 ``reasoning_effort``。
            #
            # ⚠️ 显式写出来（而不是靠 `PlatformProfile.thinking` 的默认值）是因为
            # "用哪套参数名"在这家上**取决于它背后代理的是哪个模型**：它自己的
            # DeepSeek 系认 `reasoning_effort`，而某些第三方模型（比如 GLM 系）
            # 要 `thinking.type`。我们只对前者负责 —— 认不出来的情况交给
            # `_ADAPTIVE_PARAMS` 那套自适应：厂商报"参数无效"时这个字段会被
            # 自动禁用并重发，档位静默失效但**不会报错、不会中断对话**。
            thinking=reasoning_effort_style(),
        ),
    ),
    # ---- 补：新增服务商预设对应的平台策略 -------- #
    #
    # 本次把内置服务商从 4 家扩到 17 家（产品要求）。每条都写清"依据是什么"：
    # **文档核对过的**才敢说"它认这个字段"，其余的走 OpenAI 风格
    # （``reasoning_effort``）+ 自适应回退 —— 那条路线的兜底已经补齐
    # （思考字段现在也在 `_ADAPTIVE_PARAMS` 里，见上面的说明）。
    (
        ("api.minimaxi.com", "api.minimax.chat"),
        PlatformProfile(
            name="minimax",
            # 文档没给温度上限的明确说明，取保守区间（多数厂商至少接受 0~1）
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
        # Google Gemini 的 OpenAI 兼容端点
        ("generativelanguage.googleapis.com",),
        PlatformProfile(
            name="gemini",
            # 官方 temperature 区间是 0~2
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
            # 聚合网关：用它**自己**的归一化字段，而不是靠透传（见 openrouter_style）
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
        # 本地推理：Ollama / llama.cpp / vLLM 的自建端点
        ("localhost", "127.0.0.1", "0.0.0.0", "::1"),
        PlatformProfile(
            name="local",
            temperature_range=(0.0, 2.0),
            # 本地服务对 stream_options 的支持参差不齐（老版本 llama.cpp
            # 会直接 501）。这里仍然乐观尝试——不支持时自适应回退会关掉它。
        ),
    ),
)

# 未知厂商的兜底 Profile。
#
# ``stream_usage`` 这里取 **True（乐观）**，这一点是刻意权衡过的：
#
# - 取 False 的话，不支持的厂商是没问题了，但**支持**的厂商会永久拿不到 usage ——
#   而 usage 是费用统计与缓存命中率的唯一数据来源。这个损失是静默且不可逆的，
#   因为自适应回退只会"关"不会"开"。
# - 取 True，最坏情况是遇到不支持的厂商多花一次失败请求（每个进程一次），
#   然后被 ``AdaptiveFallbacks`` 永久禁用。
#
# 两害相权：一次可自愈的失败，远好过永久缺失统计数据。
DEFAULT_PROFILE = PlatformProfile(
    name="generic",
    temperature_range=(0.0, 1.0),  # 保守：多数厂商至少接受 0~1
    stream_usage=True,
    # 惩罚参数同样取**乐观**，理由和 stream_usage 一致：
    #
    # - 取 False：不支持的厂商是没问题了，但用户在设置里填的
    #   frequency_penalty **永远不生效**，而且界面上没有任何反馈 ——
    #   他只会得出"这个 App 不支持这个功能"的结论，然后放弃。
    # - 取 True：最坏是第一次多花一个失败请求，然后被 AdaptiveFallbacks
    #   永久禁用（`_ADAPTIVE_PARAMS` 里已经包含这两个名字）。
    #
    # 一次可自愈的失败，好过永久静默的失效。
    #
    # 注意：只有**用户显式填了值**才会发送（见 openai_compat._build_payload），
    # 所以乐观策略的代价只落在"确实想用它"的人身上，不会波及所有人。
    supports_penalties=True,
)


def detect_profile(base_url: str) -> PlatformProfile:
    """按端点域名推断厂商，推断不出就返回保守兜底 Profile。"""
    try:
        host = (urlparse(base_url).hostname or "").strip().lower()
    except ValueError:
        return DEFAULT_PROFILE

    if not host:
        return DEFAULT_PROFILE

    for hosts, profile in _PROFILES:
        for candidate in hosts:
            # 精确匹配或后缀匹配（``api.example.com`` 应命中 ``example.com``）
            if host == candidate or host.endswith(f".{candidate}"):
                return profile

    return DEFAULT_PROFILE


# --------------------------------------------------------------------------- #
# 自适应回退
# --------------------------------------------------------------------------- #
# 部分网关对不支持的入参，会把**字段名**直接写进错误信息里 ——
# 典型形状是 ``error.message`` 等于 ``Unknown parameter: 'stream_options'``。
# 把它提出来用于精确禁用，而不是一遇到 400 就把所有可选参数全砍掉。
#
# （这里刻意不贴完整的 JSON 示例：单独一行以 ``{`` 开头的注释会被 ruff 的
# ERA001 判成"注释掉的代码"，而它是说明文本。改成行内叙述既躲开误报，也更易读。）
_UNSUPPORTED_PARAM_HINTS = (
    "unknown parameter",
    "unsupported parameter",
    "invalid parameter",
    "not supported",
    "unrecognized request argument",
    "extra inputs are not permitted",  # vLLM / LMDeploy 的措辞
)


def extract_unsupported_param(body: str) -> str | None:
    """从错误响应里猜出哪个参数不被支持，猜不出返回 ``None``。

    返回的是我们**确实会发送**的那些参数名之一，避免把厂商返回的任意字符串
    当成参数名去禁用掉不相干的东西。
    """
    lowered = body.lower()
    if not any(hint in lowered for hint in _UNSUPPORTED_PARAM_HINTS):
        return None

    # JSON 字符串里的双引号会被转义成 ``\"``，直接比对 ``"param"`` 反而漏掉。
    # 先抹掉反斜杠，让转义写法和裸写法得到同一个结果。
    probe_text = lowered.replace("\\", "")

    # 先找带引号/带冒号的强证据，避免仅凭子串误判
    for param in _ADAPTIVE_PARAMS:
        for probe in (f"'{param}'", f'"{param}"', f"{param}:", f"{param} "):
            if probe in probe_text:
                return param

    # 再兜一层整词匹配：不少厂商的错误是直接写成
    # "unrecognized request argument supplied: top_p"，既没引号也没冒号。
    # 用整词而不是子串，是为了不让 "usage" 命中 "include_usage" 之类的意外组合。
    for param in _ADAPTIVE_PARAMS:
        if re.search(rf"\b{re.escape(param)}\b", probe_text):
            return param

    # 定位不到具体字段时，返回空串表示"确实是不支持参数，但不知道是哪一个"
    return ""


# 允许被自适应禁用的参数（只列我们有条件发送的那些）
_ADAPTIVE_PARAMS = (
    "stream_options",
    "include_usage",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "max_tokens",
    "tools",
    # 各家的"思考强度"字段（见 `THINKING_FIELD_NAMES` 的说明）：
    # 少了它们，厂商报"未知参数"时定位不到 ⇒ 禁不掉 ⇒ 重试仍失败（硬报错）。
    "reasoning_effort",
    "enable_thinking",
    "thinking_budget",
    "thinking",
    "reasoning",
)


@dataclass
class AdaptiveFallbacks:
    """记录运行期发现的不兼容参数。

    这是**每个 adapter 实例**各自的状态：同一个进程里可以同时连 OpenAI 和一个
    只支持基础参数的小网关，互不影响。
    """

    disabled: set[str] = field(default_factory=set)

    def disable(self, param: str) -> bool:
        """禁用一个参数；返回 True 表示这是首次禁用（调用方应当重试一次）。"""
        if param in self.disabled:
            return False
        self.disabled.add(param)
        logger.info("自适应禁用不被 %s 支持的参数，已重试", param)
        return True

    def enabled(self, param: str) -> bool:
        return param not in self.disabled


def looks_like_error_payload(data: Any) -> str | None:
    """识别「HTTP 200 但内容其实是错误」的网关响应。

    少数网关/代理会把错误包在 200 里返回（通常是代理层自己没拿到后端，
    于是塞了一个描述失败原因的 JSON）。按状态码判成功的话，后续解析会在
    ``choices[0]`` 上炸出一个和真实原因毫无关系的 KeyError/IndexError，
    界面上表现为"莫名其妙的错误"。

    只要能提取出 message 就返回它，调用方据此抛出一个说人话的异常。
    """
    if not isinstance(data, dict):
        return None

    # choices 存在就是正常响应（即使为空数组也算响应本身成功）
    if data.get("choices") is not None:
        return None

    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("msg") or error.get("type")
        if message:
            return str(message)
    elif isinstance(error, str) and error:
        return error

    # 有些网关只有 code + message，且 code 非 0 表示失败
    code = data.get("code")
    message = data.get("message")
    if isinstance(message, str) and message and code not in (None, 0, "0", 200, "200"):
        return message

    return None
