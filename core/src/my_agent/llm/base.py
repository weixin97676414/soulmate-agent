"""LLM 接入层的统一抽象。

对应《智能体框架开发文档》第 4.2 节。核心目标：**一个接口，多厂商**。
Agent 层只依赖本模块的 ``BaseLLM`` 与数据结构，永不接触厂商原始格式。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# 统一数据结构
# --------------------------------------------------------------------------- #


@dataclass
class ToolSpec:
    """工具定义，由适配器转换为厂商需要的格式。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    type: str = "function"


@dataclass
class ToolCall:
    """模型输出的「调用某工具及参数」的结构化指令。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_openai(self) -> dict[str, Any]:
        """转换为 OpenAI 工具调用结构。

        回传时优先使用模型给的原始参数串，保证与厂商的多轮协议一致
        （部分模型对 arguments 的 JSON 规范化敏感）。
        """
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.raw_arguments or dump_arguments(self.arguments),
            },
        }


@dataclass
@dataclass
class ImagePart:
    """消息里附带的一张图片。

    ``data_url`` 是 ``data:image/png;base64,...`` 形式。用 data URL 而不是
    本地路径，是因为**厂商只接受这种内联形式**（它们看不到用户的磁盘）。

    **``data_url`` 刻意设了 ``repr=False``**：dataclass 默认的 repr 会把整个
    base64 串打进日志。一张手机照片是几 MB，这个 repr 一旦被某个
    ``logger.debug("消息=%s", message)`` 命中，日志文件会瞬间爆掉，
    而且要过很久才会有人把"日志暴涨"和"加了图片功能"联系起来。
    """

    mime: str = "image/png"
    data_url: str = field(default="", repr=False)
    # 展示用（来自用户上传时的原始文件名）
    name: str = ""


@dataclass
class Message:
    """框架内部统一消息格式，与厂商消息结构解耦。"""

    role: str  # system / user / assistant / tool
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    # 推理模型（如 deepseek-reasoner）的思维链内容，仅用于展示，不回传厂商
    reasoning_content: str = ""
    # 随消息附带的图片。
    #
    # 做成**增量字段**而不是把 content 改成 parts 列表，是为了不动已有的一切：
    # 缓存前缀的稳定性、落盘格式、展示层、摘要压缩都建立在"content 是纯文本"
    # 这个前提上。图片只在**发出请求的那一刻**影响消息体（见适配器），
    # 落盘时按设计**不保存**（见 memory/short_term.py 的 to_records 说明）。
    images: list[ImagePart] = field(default_factory=list)
    # 这条工具结果里检测到的可疑指令标签（见 ``security/injection.py``）。
    #
    # 只存**标签**不存原文：那些内容已经进了上下文，再复制一份到消息对象上
    # 只会让落盘与日志的体积失控 —— 而日志是最容易被整段复制走的东西。
    # Agent 读它来决定要不要向用户告警，这是注入防护的第三层。
    injection_hits: list[str] = field(default_factory=list)
    # 这条消息**产生**的时刻（epoch 秒），None = 不知道。
    #
    # 为什么要有它：记忆需要时间维度 —— 用户的原话是"每个聊天记录的每句话都有一个
    # 准确的时间戳，让 AI 能分清'现在'和'以前'，别把旧的当当下聊"。
    #
    # ⚠️ **它只在"渲染给模型"时才变成文本**（见 memory/short_term.py 的
    # `_with_time_prefixes`）：content 里不写时间戳。写进去的话，落盘内容、摘要输入、
    # 界面回显都会被时间噪声污染，而且每轮渲染都会再叠一层。
    #
    # None 的两种来源：更早版本落盘的消息（当时的时间戳是错的，读回来一律当不知道）、
    # 手工构造的消息（system 与引擎合成的提示语）。**不知道就不加前缀** —— 给一个
    # 假时间比没有时间糟糕得多。
    created_at: float | None = None
    # 这条助手消息对应的**执行计划**（结构化 dict：goal / steps / state）。
    #
    # 用途只有一个：让界面在重开对话后仍能画出当时的计划卡片（产品要求
    # "计划随消息存进会话，可回看"）。
    #
    # ⚠️ **刻意不进 ``to_dict()``**：那个方法是**发给厂商的请求体**的构造器。
    # 计划是给人看的过程性内容，交给模型只会白占 token，还可能干扰推理 ——
    # 模型需要的是 ``plan_hint`` 那段提示（已单独注入），不是这份 JSON。
    plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.name:
            data["name"] = self.name
        # 图片只报数量，不带 base64 —— 这个 dict 会被 tracer / 日志用到
        if self.images:
            data["images"] = len(self.images)
        if self.injection_hits:
            data["injection_hits"] = list(self.injection_hits)
        return data

    def has_images(self) -> bool:
        return bool(self.images)


@dataclass
class LLMResponse:
    """一次非流式调用的完整结果。"""

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
    """流式输出的增量片段。

    一个流会产出若干 ``delta`` 文本片段，最后产出一个携带
    ``finish_reason`` / ``tool_calls`` / ``usage`` 的终结片段。
    """

    delta: str = ""
    reasoning_delta: str = ""
    tool_calls: list[ToolCall] | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None

    @property
    def is_final(self) -> bool:
        return self.finish_reason is not None


# --------------------------------------------------------------------------- #
# 工具调用的序列化辅助
# --------------------------------------------------------------------------- #


def dump_arguments(args: dict[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False)


def load_arguments(raw: str | None) -> dict[str, Any]:
    """尽力解析模型返回的参数串；解析失败返回空字典而非抛异常。

    模型偶尔会返回不完整或带注释的 JSON，此时把原始串保留在
    ``ToolCall.raw_arguments`` 里交给上层回填错误信息，比直接崩溃更稳。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --------------------------------------------------------------------------- #
# 适配器抽象
# --------------------------------------------------------------------------- #
class _NullLease:
    """没有注册表时的空租约 —— 让适配器不必到处判 ``None``。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


_NULL_LEASE = _NullLease()


async def _leased(lease: Any, source: AsyncIterator[StreamChunk]) -> AsyncIterator[StreamChunk]:
    """把租约的生命周期套在一次流式调用的外面。

    写成生成器（而不是在适配器里加 ``async with``）是为了让调用点只有一处、
    且不必给几十行循环重新缩进。
    """
    async with lease:
        async for chunk in source:
            yield chunk


class BaseLLM(ABC):
    """所有模型适配器必须实现的统一接口。"""

    def __init__(
        self,
        *,
        model_name: str,
        supports_tools: bool = True,
        supports_stream: bool = True,
        supports_reasoning: bool = True,
        token_limit: int = 32768,
    ) -> None:
        self.model_name = model_name
        # 注册表租约工厂（由 ``LlmRegistry.register`` 注入）。
        #
        # 它让"这一次流式调用正在使用本适配器"变成注册表能看见的事实，从而让
        # 被换掉的旧注册表**等到没有在途请求再关**。没有它的话，"搭子回答到一半
        # 时切到设置页"会把回答当场掐断，报的却是"模型流式调用网络异常"。
        # 详见 ``llm/registry.py`` 顶部。
        self._lease_factory: Any = None
        self.supports_tools = supports_tools
        self.supports_stream = supports_stream
        # 能否接受"思考强度"。默认 True 是**乐观**取舍，理由与其他能力开关不同：
        #
        # 思考强度**只在用户主动选过档位时才发送**（None 表示完全不发）。所以
        # 默认放开不会让任何人付出代价 —— 不选的人一个字段都不多、和以前完全一样；
        # 而选的人如果正好碰上不认这家的网关，`llm/platform.py` 的自适应回退会
        # 禁用该字段并自动重试一次。
        #
        # 反过来默认 False 的代价是：支持它的用户也要先知道去设置里打开开关，
        # 否则那个控件根本不出现 —— 对零基础用户等于"这个功能不存在"。
        self.supports_reasoning = supports_reasoning
        self._token_limit = token_limit

    @property
    def token_limit(self) -> int:
        """模型上下文窗口大小，用于记忆截断决策。"""
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
        """非流式对话，返回完整响应。"""

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
        # 思考强度（"low" / "medium" / "high"）。``None`` = **完全不发送**这个字段 ——
        # 多数网关不认识它，而默认发送等于让所有人都替少数推理模型承担被拒的风险。
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式对话，逐片段产出 ``StreamChunk``。

        采样参数为什么是**三个可选关键字**而不是打成一个配置对象：

        - ``None`` 统一表示「**不发送这个字段**」，而不是「发送默认值」。
          这两者完全不同 —— 不接受的厂商收到默认值同样会 400，
          问题在于字段本身而不在取值（见 ``llm/platform.py`` 的 ``clamp``）。
        - ``temperature`` 已经存在，再引入一个能改它的对象会出现两个来源，
          谁生效取决于实现细节，是最容易埋出诡异 bug 的那种设计。
        - 各适配器本来就要逐项判断"这家支不支持"，字段平铺反而更直白。

        只有 ``temperature`` 有默认值，其余三个默认关闭 —— 大多数用户不需要调它们，
        而每多显式发送一个字段，就多一分被某家网关拒掉的可能。
        """

    def set_lease_factory(self, factory: Any) -> None:
        """由 ``LlmRegistry`` 注入租约工厂。适配器自己不关心谁在用。"""
        self._lease_factory = factory

    def lease(self) -> Any:
        """借出一个"我正在使用本适配器"的声明（未接入注册表时是空租约）。"""
        if self._lease_factory is None:
            return _NULL_LEASE
        return self._lease_factory()

    def leased_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        """``stream()`` 的带租约版本 —— **引擎应该用它而不是 ``stream()``**。

        整个消费期间持有租约：期间就算用户在设置页改了模型（会触发
        ``reload_models``），旧注册表也只会被标记为待回收，不会当场关掉
        正在使用的 HTTP 客户端。

        为什么把租约放在**整个回合**而不是每次 HTTP 调用：一次对话回合里模型可能
        被反复调用（每轮工具之后都要再问一次），逐次加租约需要在循环里四处插桩；
        而按回合持有只是让旧注册表多存活一会儿（无害），换来的是一处修改覆盖
        所有调用方（对话 / 群聊 / 定时任务 / 命令行都走引擎）。
        """
        return _leased(self.lease(), self.stream(*args, **kwargs))

    async def list_models(self) -> list[str]:
        """拉取该端点可用的模型名列表（用于设置中心的连通性测试）。"""
        raise NotImplementedError

    async def aclose(self) -> None:
        """释放底层连接资源。"""
        return None
