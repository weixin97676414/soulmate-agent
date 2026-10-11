"""Agent 核心引擎：ReAct 变体的主循环。

对应《智能体框架开发文档》第 7 章。主循环基于「模型是否返回 tool_calls」
判断分支：有则执行工具、回填结果、继续；无则返回最终回答。

本项目额外做了一层封装：``run_stream()`` 产出 ``AgentEvent`` 事件流，
由服务层直接转成 SSE 推给桌面客户端，从而实现「工具调用卡片」的
实时状态更新（运行中 → 成功/失败/被拒绝）。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..errors import LLMError, SkillPermissionError
from ..llm.base import BaseLLM, ImagePart, ToolCall, ToolSpec
from ..memory.short_term import MemoryManager, internal_hint
from ..observability.tracer import Tracer
from ..skill.base import SkillContext, wants_terminate
from ..skill.manager import SkillManager
from .context import ContextGuard, ContextPolicy, looks_like_context_overflow
from .planner import Plan, Planner, coerce_step_status, plan_hint
from .reflection import Reflector, revision_hint
from .text_tools import extract_text_tool_calls, render_tools_section

logger = logging.getLogger(__name__)

# 模型返回空内容（既没文本也没工具调用）时回填的提示语。
# 走 internal_hint 标记：它会进入消息列表并落库，但展示层据此过滤，
# 用户不会在对话记录里看到这条自己从没发过的消息。
NUDGE_TEXT = "请针对我上一条消息给出明确的回复。"

# 用户在计划卡片上点「不用了」时，助手回的那句话。
# 必须**有**这么一句：否则用户消息后面没有任何回应，重开对话看到的是
# "说了话却没人搭理"，比不给取消按钮还糟。
PLAN_ABORTED_TEXT = "好，这次先不动手。需要的时候再说一声。"


# --------------------------------------------------------------------------- #
# 回复正文的时间戳净化（一条回复里几十个 `[09-28 18:00]`）
# --------------------------------------------------------------------------- #
# 根因：发给模型的历史消息每条都带 `[MM-DD HH:MM] ` 前缀（见 memory/short_term.py，
# 那是给模型的上下文，用户看不到），模型**模仿这个格式**，在每次工具调用之后的
# 正文开头自己写一个当前时刻。治法是三层：系统提示词禁令 + 这里对正文段剥前缀
# + 工具卡片直接显示该次调用的时刻（时间跟工具卡走）。
_STAMP_CHAIN = re.compile(r"^(?:\[\d{1,2}-\d{1,2} \d{1,2}:\d{2}\]\s*)+")
# 一个时间戳在流式到来时的**所有可能前缀**（写到哪算哪都算"仍像时间戳"）
_STAMP_PARTIAL = re.compile(r"\[\d{0,2}(?:-\d{0,2})?(?: \d{0,2})?(?::\d{0,2})?\]?")


def strip_timestamp_prefix(text: str) -> str:
    """剥掉一段正文开头连续的时间戳前缀（`[09-28 18:00] [09-28 18:01] 正文`）。"""
    if not text:
        return text
    return _STAMP_CHAIN.sub("", text, count=1)


# 系统提示词里的禁令（与上面的净化互为攻防：禁令管住大多数，净化兜住漏网的）
_NO_STAMP_RULE = (
    "\n\n## 输出格式的一条硬性规矩\n"
    "回复正文里**绝对不要**输出 `[09-28 18:00]` 这种时间戳前缀 —— "
    "那是对话记录的内部格式，界面会自动显示每条消息和每次工具调用的时刻，"
    "你写出来只会变成一串串的噪音。需要知道现在几点时，调用 system_time 技能。"
)


class _StampStripper:
    """流式版的段首时间戳剥离器。

    ## 为什么要"扣住开头几个字"

    delta 是逐字到来的：`[`、`09`、`-`…… 单看任何一个 delta 都判断不了它是不是
    时间戳的开头。这里把段首**还像一个时间戳**的字符先扣住不发，一旦能确定
    （拼出了完整时间戳 → 剥掉；或形状不对 → 原样放行）再吐给界面 ——
    否则用户会在流式过程中看到时间戳闪现、又在消息定稿时消失。
    """

    # 超过这个长度还没形成完整时间戳的，绝不再是时间戳（正常的 `["]` 引用、
    # `[笔记]` 这类正文开头不会长得这么像）。防极端情况下一直扣着不吐字。
    _MAX_PENDING = 20

    def __init__(self) -> None:
        self._pending = ""
        self._decided = False

    def feed(self, delta: str) -> str:
        """喂一个 delta，返回**此刻可以外发**的文本（可能为空串）。"""
        if self._decided:
            return delta
        self._pending += delta
        # 连排的时间戳逐个剥（"[..][..] 正文"）
        while True:
            matched = _STAMP_CHAIN.match(self._pending)
            if not matched:
                break
            self._pending = self._pending[matched.end():]
        # 刚剥完一个戳、后面还没有字符时保持**未决**：下一个戳可能紧跟着来
        # （"[..][..] 正文"），一旦在这里误判成"不是戳"就漏剥了
        if self._pending == "":
            return ""
        # 开头仍"像一个写到一半的时间戳" → 继续扣住
        if self._pending.startswith("["):
            partial = _STAMP_PARTIAL.match(self._pending)
            if partial and partial.end() == len(self._pending) <= self._MAX_PENDING:
                return ""
        self._decided = True
        text, self._pending = self._pending, ""
        return text

    def flush(self) -> str:
        """段结束时把扣住的内容全部放行（模型只发了半个时间戳的兜底）。"""
        text, self._pending = self._pending, ""
        self._decided = True
        return text


def _thinking_no_effect_notice() -> str:
    """"设了思考强度却没有任何思考内容"时给用户看的提示。

    文案有三条自我要求：
    1. **说清后果的范围**：回答本身不受影响，只是那个档位没生效。否则用户会
       以为整个回答都是"降级产物"，白白不信任一次正常结果。
    2. **给出各家的真实差异**，而不是让他怀疑是不是应用坏了；
    3. **不承诺做不到的事**：不写"请到某某页面切换"，因为我们暂时没有那个
       自定义入口 —— 提示一个不存在的按钮比不提示更糟。
    """
    return (
        "你为这次对话选了「思考强度」，但模型没有返回任何思考内容。"
        "这通常说明这家服务商对思考参数的写法与我们发送的不一致 —— "
        "各家并不统一：OpenAI 用 reasoning_effort，通义用 enable_thinking + "
        "thinking_budget，智谱用 thinking 对象。"
        "回答质量本身不受影响，只是这个档位没有生效。"
    )


# 计划确认回调：拿到计划（``Plan.to_dict()``）后挂起，直到用户在前端点
# 「开始执行」（approved=True）或「改一下」（approved=False + feedback=意见）
# 或「不用了」（approved=False + 空 feedback）。
#
# 为什么是**回调**而不是布尔开关：计划模式只在单聊启用（见 ``AgentConfig``
# 的 ``plan_decider`` 说明），而且"等用户点头"需要一个能挂起整条事件流的通道 ——
# 布尔开关既表达不了单聊/群聊的差别，也没有地方挂起。
PlanDecider = Callable[[dict[str, Any]], Awaitable[tuple[bool, str]]]


def apply_plan_update(plan: Plan, arguments: dict[str, Any]) -> tuple[bool, str]:
    """把 ``plan_update`` 的参数落到计划上，返回 ``(是否生效, 回填给模型的话)``。

    为什么这个判定在引擎里而不是在技能里：技能**看不到计划**（计划活在本轮引擎
    状态里）。让技能"假装更新成功"是典型的静默失败 —— 模型会以为自己汇报过了，
    而卡片上什么都没变。所以技能只收参数，真伪一律由这里裁决。

    步号非法时**明说可用步号**：否则模型只会反复试同一个错号，最后交出一份
    进度全掉的计划。
    """
    step_id = str(arguments.get("step") or "").strip()
    status = coerce_step_status(arguments.get("status"))
    note = str(arguments.get("note") or "").strip()

    step = plan.find(step_id)
    if step is None:
        available = "、".join(item.id for item in plan.steps) or "（无）"
        return False, (
            f"[无效步号] 计划里没有第 {step_id or '?'} 步，本次汇报没有生效。"
            f"可用的步号是：{available}。请用正确的步号重新调用 plan_update。"
        )
    step.status = status
    if note:
        step.note = note
    return True, f"第 {step_id} 步已标记为「{status}」。"


@dataclass
class AgentConfig:
    """Agent 行为参数，对应开发文档 config/agent.yaml。"""

    # 模型↔工具的**往返次数**上限。
    #
    # 这里曾经是 10，是框架早期"防死循环"的保守值 —— 但实测反馈"没执行几个就
    # 提示已达到最大执行轮数"：一个正常任务（搜索→打开→阅读→再点→总结）很容易
    # 就用完 10 个来回。用户的原话是"我们一直都是不设对话轮数上限"。
    #
    # 改成 500：对真实任务而言等于"不限制"，同时保留一个极端的兜底，
    # 避免真出现死循环时把 token 无限烧下去。真正的防失控靠这三条，
    # 而不是靠"做到第 N 步就停"：
    #   1. 同一工具连续失败会被摘除（`same_tool_failure_tolerance`）；
    #   2. 用户随时可以停；
    #   3. 这里的极端上限。
    max_iterations: int = 500
    max_tool_calls_per_turn: int = 500
    temperature: float = 0.7
    max_tokens: int | None = None

    # 另外三个采样参数。``None`` 表示**不发送**（而不是"发默认值"）——
    # 这两者的区别见 llm/platform.py 的 clamp：不接受的厂商收到默认值同样会被拒。
    #
    # 默认全关是刻意的：大多数用户不需要调它们，而每多显式发一个字段，
    # 就多一分被某家网关拒掉的可能。要调的人自己去设置里填。
    top_p: float | None = None
    # 频率惩罚：说过的词降低权重 —— 治"车轱辘话"
    frequency_penalty: float | None = None
    # 存在惩罚：提过的词降低权重 —— 逼它换角度，促进覆盖面
    presence_penalty: float | None = None
    # 思考强度："low" / "medium" / "high"；None = 不发送这个字段。
    # 它是**会话级**的（见 storage/db.py 的 v6 迁移），因为用户对"这次值不值得
    # 多想一会儿"的判断是按对话来的，不是按人来的。
    reasoning_effort: str | None = None
    # 这里曾有 ``system_prompt: str``：它承接「搭子 / 会话 / 全局」三处的自定义
    # 提示词，并在为空时回落到内置的那段通用提示词。**已按产品要求整体退役** ——
    # 完整提示词现在只由搭子自己的五个人格文档组装（见 ``_system_prompt``），
    # 不设任何兜底。那三处的字段与 DB 列都还留着（零迁移风险），只是没人读了。
    #
    # 助手的人格与记忆（昵称 + IDENTITY/SOUL/USER/MEMORY/RULES 拼好的一段）。
    # 它是 system 消息的**唯一来源**，所以不必再与别的来源区分，但仍单独占一个
    # 字段：这份内容是磁盘上的活文件，要能作为**惰性提供者**
    # （``Callable[[], str]``）被反复重读 —— 搭子在一轮对话中途改写人格文件后
    # 要立刻生效（见 ``_refresh_system_if_persona_changed``），传死字符串做不到。
    persona: str | Callable[[], str] = ""
    same_tool_failure_tolerance: int = 3
    enabled_skills: set[str] | None = None

    # 这一轮对话是**替哪个搭子**在跑。它不参与提示词组装（人格由 ``persona``
    # 负责），只用来判定"哪些专属技能对这个搭子不存在"（心鉴学那套，见
    # ``skill/builtin/xjx.py``）。空串 = 没有搭子在场的执行路径（CLI / SDK），
    # 按"非归属"处理，专属技能一律不给。
    target_assistant: str = ""

    # 当前模型的上下文窗口。上下文压缩要拿它算用量比例。
    token_limit: int = 32000
    context_policy: ContextPolicy = field(default_factory=ContextPolicy)

    # Planner / Reflection 都会**额外花一次 LLM 调用**，所以默认关闭，
    # 由用户在设置里按需开启（详见各自模块开头的取舍说明）。
    enable_planner: bool = False
    enable_reflection: bool = False
    reflection_rounds: int = 1

    # 计划确认回调。**它是"要不要走计划模式"的唯一开关**：
    #
    # - 单聊（routes/chat.py）注入它 → 多步任务先出计划、挂起等用户点头；
    # - 群聊 / 定时任务 / 命令行不注入 → ``None``，引擎直接走原来的 ReAct 循环，
    #   一行行为都不变（产品约定：本次只在单聊用）。
    #
    # 为什么不复用 ``enable_planner``：那个字段只管"要不要花这次 LLM 调用生成计划"，
    # 而"用户能不能看见、能不能改"是另一个维度的事。两者分开，群聊那条路径就不会
    # 因为某人把设置里的开关打开而突然开始弹计划卡片。
    plan_decider: PlanDecider | None = None


@dataclass
class AgentEvent:
    """Agent 循环对外产出的事件。

    事件类型：
      - ``message_start``  本轮助手消息开始
      - ``delta``          文本增量
      - ``reasoning``      推理模型思维链增量
      - ``plan``           执行计划生成 / 状态变化（前端画计划卡片；仅单聊）
      - ``plan_update``    计划某一步的进度变化（前端打勾）
      - ``tool_call``      模型请求调用工具（前端插入卡片，状态=运行中）
      - ``tool_result``    工具执行完毕（前端更新卡片，status=ok/error/denied）
      - ``message_end``    本轮助手消息结束
      - ``usage``          token 用量
      - ``context_compressed`` / ``reflection`` / ``injection_suspected`` / ``warning``
        过程提示（压缩、自检、注入可疑、需要用户知道的降级）
      - ``done``           整个任务结束
      - ``error``          任务级错误
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> tuple[str, dict[str, Any]]:
        return self.type, self.data


class Agent:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        skill_manager: SkillManager,
        memory: MemoryManager,
        config: AgentConfig,
        ctx: SkillContext,
        tracer: Tracer | None = None,
        utility_llm: BaseLLM | None = None,
    ) -> None:
        self.llm = llm
        # 压缩 / 规划 / 自检走哪一个模型（产品要求：可指定）。
        #
        # 默认 ``None`` = 跟随 ``llm``，也就是老行为；由调用方用
        # ``AppRuntime.utility_llm(llm)`` 解析设置后传进来 —— 引擎不碰配置，
        # 这样四条调用路径（对话 / 群聊 / 定时任务 / 命令行）行为一致。
        #
        # ⚠️ 它**必须与 ``llm`` 来自同一个注册表**：整轮租约是注册表级的
        # （见 run_stream 的说明），跨注册表取用会让租约保护不到它。
        self.utility_llm = utility_llm or llm
        self.skills = skill_manager
        self.memory = memory
        self.config = config
        self.ctx = ctx
        self.tracer = tracer or Tracer()
        self.context_guard = ContextGuard(config.context_policy)
        self.planner = Planner(enabled=config.enable_planner)
        self.reflector = Reflector(
            enabled=config.enable_reflection, max_rounds=config.reflection_rounds
        )
        # 本回合的执行计划（None = 这一轮没走计划模式）。
        #
        # 放实例属性而不是在循环里传参：``plan_update`` 工具的进度要在
        # ``_execute_tool_calls`` 里落到**同一份**计划上，而那个方法与主循环
        # 隔了两层调用。每轮 ``run_stream`` 开头重置。
        self._active_plan: Plan | None = None
        # 落库用的那条助手消息（计划挂在它身上）。进度每次变化都要回写它，
        # 否则重开对话看到的计划永远停在"一步没做"（见 _sync_plan_message）
        self._plan_message = None

    # ------------------------------------------------------------------ #
    # 主循环（流式）
    # ------------------------------------------------------------------ #
    async def run_stream(
        self, user_input: str, *, images: list[ImagePart] | None = None
    ) -> AsyncIterator[AgentEvent]:
        """跑一轮完整任务，产出事件流。

        ⚠️ **整个回合都持有模型注册表的租约**（用户要求：「只要客户端没有完全退出，
        buddy 的任务就不能中断」）。

        为什么必须是"整轮"而不是"每次模型调用"：一轮任务里模型会被反复调用
        （每执行完一批工具都要再问一次），而**工具执行期间可能持续很久**。
        如果租约只覆盖单次 ``stream()``，那么在工具执行时用户切到设置页改一次模型
        （会触发 ``PUT /v1/models`` → ``reload_models`` → ``retire()``），
        旧注册表会被**当场关掉**，该轮随后的调用就会抛 httpx 的
        ``RuntimeError: Cannot send a request, as the client has been closed.``
        —— 这正是用户报的那个错。

        整轮持租之后，改配置只会让旧注册表"排队等最后一个租约结束再回收"。
        """
        async with self.llm.lease():
            async for event in self._run_stream_impl(user_input, images=images):
                yield event

    async def _run_stream_impl(
        self, user_input: str, *, images: list[ImagePart] | None = None
    ) -> AsyncIterator[AgentEvent]:
        self.memory.add_user(user_input, images=images)
        # system 在**本轮开始时**算一次并保持稳定。``ensure_system`` 一旦发现内容
        # 不同就会整体替换第 0 位消息，而那是缓存前缀的起点 —— 每轮都变等于缓存全废。
        self.memory.ensure_system(self._system_prompt())

        # ---- 计划阶段：多步任务先出计划，停下等用户点头（仅单聊）---------- #
        #
        # 条件有两个，缺一不可：
        #   1. ``plan_decider`` 不为 None —— 只有单聊注入它（群聊 / 定时任务 /
        #      命令行都没有），这是"本次只在单聊用"这条口径的唯一落点；
        #   2. ``should_plan`` 判定是多步任务 —— 复用零成本启发式，
        #      简单问答不该被打扰（产品约定：AI 自己判断）。
        self._active_plan = None
        if self.config.plan_decider is not None and self.planner.should_plan(
            user_input, need_tools=self.llm.supports_tools
        ):
            async for event in self._plan_phase(user_input):
                yield event
            if self._active_plan is not None and self._active_plan.state == "aborted":
                # 用户点了「不用了」：这一轮到此为止，**一个工具都不执行**。
                #
                # 但必须补一句回应，而且要**走正规的事件流**（start → delta → end）：
                # 只往记忆里塞一条消息的话，前端一个字节都收不到，用户看到的是
                # "说了话却没人搭理"—— 那比不给这个按钮还糟。
                self.memory.add_assistant(PLAN_ABORTED_TEXT)
                yield AgentEvent("message_start", {"iteration": 0})
                yield AgentEvent("delta", {"text": PLAN_ABORTED_TEXT})
                yield AgentEvent(
                    "message_end",
                    {"iteration": 0, "content": PLAN_ABORTED_TEXT, "tool_calls": []},
                )
                yield self._done_event(iterations=0)
                return
            if self._active_plan is not None:
                # 已确认的计划注入上下文：后面每一轮都有一个"目标锚点"
                # （这是计划模式最初的价值，见 planner.py 顶部）。
                # 走 internal_hint：它进上下文参与推理，但用户看到的计划是那张
                # 卡片，不该在正文里再出现一份重复的编号列表。
                self.memory.add_user(plan_hint(self._active_plan))

        # 计划要挂在本轮**第一条** assistant 消息上：前端是按消息渲染卡片的，
        # 挂到最后一条会让卡片跑到正文下面去。
        #
        # ⚠️ 这里只记一个"该挂计划"的布尔，**不在这一刻取快照**：进度是模型在
        # 吐正文**之前**汇报上来的（先调 plan_update，再输出文字），提前 to_dict()
        # 会让落库的计划永远停在"一步没做"。真正的取值推迟到挂载那一刻。
        plan_pending = self._active_plan is not None and self._active_plan.state == "executing"
        self._plan_message = None

        # 同一工具连续失败计数：达到阈值后从工具列表中摘除，避免死循环
        failure_counts: dict[str, int] = {}
        disabled_tools: set[str] = set()
        empty_response_nudges = 0
        # 自检已经重答过几次（防止"改—查—改"无限循环）
        review_rounds = 0
        iteration = 0
        collected_text = ""
        collected_reasoning = ""
        # 这一轮对话里**是否真的收到过思考内容**。
        #
        # 用途见下面"设了档位却没有任何思考内容"那条诊断：各家厂商对"思考强度"
        # 的字段名各不相同（OpenAI 是 reasoning_effort、通义是 enable_thinking、
        # 智谱是 thinking），而它们对**不认识的字段是静默忽略**的 ——
        # 请求成功、回答正常，只有那个开关什么都没干，用户完全看不出来。
        # 所以这里要自己判断一次，把它变成一条看得见的提示。
        saw_reasoning = False
        # 本轮文本是否已经写进记忆。中断收尾时靠它避免重复写入
        # （主循环已经把文本 add_assistant 过，CancelledError 分支不能再加一条）。
        text_persisted = False

        try:
            while iteration < self.config.max_iterations:
                iteration += 1
                with self._span(f"step:{iteration}"):
                    yield AgentEvent("message_start", {"iteration": iteration})

                    collected_text = ""
                    collected_reasoning = ""
                    text_persisted = False
                    tool_calls: list[ToolCall] = []
                    usage: dict[str, Any] = {}
                    # 每个正文段一个剥离器：模型爱在工具调用之后的正文开头
                    # 模仿历史前缀写 `[09-28 18:00]`（见 _StampStripper 的说明）
                    segment_stripper = _StampStripper()

                    # 不支持原生工具调用的模型走文本协议：正文要**先缓冲**，
                    # 解析掉 ```tool_call 代码块之后再吐给界面。边流边显示的话，
                    # 用户会在气泡里先看到一大段原始 JSON 再看到它"消失"。
                    live_text = self.llm.supports_tools

                    # 上下文接近窗口上限时先压缩。压缩比裁剪温和：裁剪会把最旧的
                    # 消息整条丢掉，而丢掉的往往正是用户一开始的约定
                    if self.context_guard.should_compress(self.memory, self.config.token_limit):
                        if await self.context_guard.compress(
                            self.utility_llm, self.memory, token_limit=self.config.token_limit
                        ):
                            yield AgentEvent(
                                "context_compressed",
                                {"summary_chars": len(self.memory.summary)},
                            )

                    retried_for_overflow = False
                    # 超限的第二级兜底是否已用过（见下面的 except 分支）
                    externalized_for_overflow = False
                    while True:
                        produced = False
                        try:
                            # 用 leased_stream 而不是 stream：整个回合持有注册表租约，
                            # 这样"用户中途改模型设置"不会把正在进行的回答掐断
                            # （详见 llm/registry.py 顶部与 base.py 的 leased_stream）。
                            async for chunk in self.llm.leased_stream(
                                self.memory.get_context(),
                                # 不支持原生工具调用的模型不传 tools，
                                # 它靠 system 里的文本协议来发起调用
                                self._tool_specs(disabled_tools)
                                if self.llm.supports_tools
                                else None,
                                temperature=self.config.temperature,
                                max_tokens=self.config.max_tokens,
                                top_p=self.config.top_p,
                                frequency_penalty=self.config.frequency_penalty,
                                presence_penalty=self.config.presence_penalty,
                                reasoning_effort=self.config.reasoning_effort,
                            ):
                                produced = True
                                if chunk.reasoning_delta:
                                    saw_reasoning = True
                                    collected_reasoning += chunk.reasoning_delta
                                    yield AgentEvent(
                                        "reasoning", {"text": chunk.reasoning_delta}
                                    )
                                if chunk.delta:
                                    visible = segment_stripper.feed(chunk.delta)
                                    collected_text += visible
                                    if live_text and visible:
                                        yield AgentEvent("delta", {"text": visible})
                                if chunk.is_final:
                                    tool_calls = chunk.tool_calls or []
                                    usage = chunk.usage or {}
                            break
                        except LLMError as exc:
                            # 厂商报上下文超限：先用**压缩**救一次；压缩救不回来时，
                            # 再把超长的工具结果**无损外置**后重试一次。
                            #
                            # 必须**还没往界面吐过任何内容**才能重试 —— 已经流出去的
                            # 正文撤不回来，重来一次会让用户看到两遍开头。
                            #
                            # ⚠️ 这里的外置是**事后**兜底，不是预判式截断：
                            # 正常路径（内容装得下）永远不会走到，模型始终整段拿到内容。
                            # 只有当厂商已经**明确拒绝**、且压缩无效时才退一步 ——
                            # 全文仍在磁盘上，模型可用 read_tool_output 读完。
                            if not produced and looks_like_context_overflow(str(exc)):
                                if not retried_for_overflow:
                                    retried_for_overflow = True
                                    if await self.context_guard.compress(
                                        self.utility_llm,
                                        self.memory,
                                        token_limit=self.config.token_limit,
                                    ):
                                        logger.info("厂商报告上下文超限，已压缩历史后重试")
                                        continue
                                if not externalized_for_overflow:
                                    externalized_for_overflow = True
                                    if self.memory.externalize_oversized():
                                        continue
                            raise

                    if not live_text:
                        collected_text, text_calls = extract_text_tool_calls(collected_text)
                        collected_text = strip_timestamp_prefix(collected_text)
                        if collected_text:
                            yield AgentEvent("delta", {"text": collected_text})
                        if text_calls:
                            tool_calls = text_calls
                    else:
                        # 流式段收尾：把剥离器扣住的尾巴放行（模型只发了半个
                        # 时间戳就结束段落时，扣住的字符要交还给正文）
                        collected_text += segment_stripper.flush()

                    message = self.memory.add_assistant(
                        collected_text,
                        tool_calls,
                        collected_reasoning,
                        # 取**此刻**的计划（可能已经被 plan_update 推着走了几步）
                        plan=self._active_plan.to_dict() if plan_pending else None,
                    )
                    if plan_pending:
                        # 记住这条消息：之后每次进度变化都要回写它，
                        # 否则用户在历史里看到的计划永远停在"没开始"
                        self._plan_message = message
                        plan_pending = False
                    text_persisted = True
                    self.tracer.add_usage(usage)
                    if usage:
                        yield AgentEvent("usage", usage)

                    yield AgentEvent(
                        "message_end",
                        {
                            "iteration": iteration,
                            "content": collected_text,
                            "tool_calls": [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in tool_calls
                            ],
                        },
                    )

                    # ---- 分支一：没有工具调用 → 自检后交付 ------------------ #
                    if not tool_calls:
                        if not collected_text.strip() and empty_response_nudges < 2:
                            # 模型返回空内容，回填一次提示让它明确作答
                            empty_response_nudges += 1
                            self.memory.add_user(internal_hint(NUDGE_TEXT))
                            continue
                        # 真的产出内容了就把计数清零。原实现只加不减，
                        # 一次抖动会永久占掉这个补救配额（B2 残留）
                        empty_response_nudges = 0

                        if self.reflector.should_review(
                            collected_text, rounds_done=review_rounds
                        ):
                            review_rounds += 1
                            review = await self.reflector.review(
                                self.utility_llm,
                                user_input=user_input,
                                answer=collected_text,
                                tool_summary=self._tool_summary(),
                            )
                            if review.needs_revision:
                                self.memory.add_user(revision_hint(review.feedback))
                                yield AgentEvent("reflection", {"feedback": review.feedback})
                                # 让模型带着意见重答一次（次数受 reflection_rounds 限制）
                                continue

                        # 设了档位却一条思考内容都没收到 → 把"静默失效"变成"看得见"。
                        #
                        # 为什么必须提示：这件事**没有任何其他观测手段** ——
                        # 请求是成功的、回答是正常的，用户唯一能感觉到的只是
                        # "这个开关好像没用"，而他无法区分"没生效"和"这个模型就这样"。
                        # 说清楚之后，他至少知道该去换写法，而不是反复点那个按钮。
                        if self.config.reasoning_effort and not saw_reasoning:
                            yield AgentEvent(
                                "warning",
                                {"message": _thinking_no_effect_notice()},
                            )
                        yield self._done_event(iteration)
                        return

                    # ---- 分支二：执行工具并回填 ---------------------------- #
                    terminated = False
                    async for event in self._execute_tool_calls(
                        tool_calls[: self.config.max_tool_calls_per_turn],
                        failure_counts,
                        disabled_tools,
                    ):
                        if event.type == "tool_result" and wants_terminate(
                            str(event.data.get("result", ""))
                        ):
                            terminated = True
                        yield event

                    if terminated:
                        logger.info("工具结果带终止标记，提前结束本轮任务")
                        yield self._done_event(iteration, terminated=True)
                        return

                    # 工具正常跑完说明模型没有卡住，把空回复计数清零
                    empty_response_nudges = 0

                    # 超过单轮上限时明确告知模型，避免它以为工具都执行了
                    if len(tool_calls) > self.config.max_tool_calls_per_turn:
                        skipped = tool_calls[self.config.max_tool_calls_per_turn :]
                        for tc in skipped:
                            self.memory.add_tool(
                                tc.id,
                                tc.name,
                                f"[未执行] 单轮工具调用数已达上限"
                                f"（{self.config.max_tool_calls_per_turn}），请分批重试。",
                            )

            # ---- 达到最大轮数 ----------------------------------------- #
            #
            # 文案要说清**是哪个上限、当前值多少、去哪改**。
            # 原先是"已达到最大执行轮数，任务未完成。请缩小任务范围或补充信息后重试。"
            # —— 用户看到它完全不知道该动哪里，只能猜（反馈原话是"是否没有生效？"）。
            logger.warning("达到最大循环轮数 %s", self.config.max_iterations)
            yield AgentEvent(
                "error",
                {
                    "code": "agent_max_iterations",
                    "message": (
                        f"这一次任务已经来回执行了 {iteration} 步（模型↔工具往返），"
                        f"达到了当前上限 {self.config.max_iterations} 步，因此停下来了。"
                        "这不是出错，是防失控的兜底。"
                        "可以在「设置 → 模型与智能体」里调大「单次任务最大执行步数」，"
                        "或者把任务拆成几步分别交给它。"
                    ),
                    "iterations": iteration,
                    "limit": self.config.max_iterations,
                },
            )
            yield self._done_event(iteration, partial=True)

        except asyncio.CancelledError:
            # 中断时保留已生成的部分文本，避免 UI 上出现过又"消失"的回复。
            # 但主循环已经 add_assistant 过一次，这里再加一条会让同一段文本
            # 在历史里出现两次，所以用 text_persisted 判重。
            if collected_text.strip() and not text_persisted:
                message = self.memory.add_assistant(
                    collected_text,
                    None,
                    collected_reasoning,
                    plan=self._active_plan.to_dict() if plan_pending else None,
                )
                if plan_pending:
                    self._plan_message = message
            # 关键：把「已声明但没回填结果」的工具调用补成完整序列。
            # 不做的话记忆里会留下 assistant(tool_calls=[A,B]) + 只有 tool(A)，
            # 下次请求厂商返回 `tool_calls must be followed by tool messages`，
            # **这个会话从此永久报错**，直到用户手动清空历史。
            sealed = self._seal_dangling_tool_calls()
            logger.info(
                "任务被用户中断（已完成 %s 轮，补齐 %s 个未回填的工具调用）", iteration, sealed
            )
            # 必须继续向外抛，否则会吞掉取消信号导致任务无法真正停止
            raise

    # ------------------------------------------------------------------ #
    # 计划阶段
    # ------------------------------------------------------------------ #
    async def _plan_phase(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """出计划 → 推给用户 → 挂起等决定 → 带意见则重拟。

        只产事件、不碰上下文：要不要采纳、采纳后怎么注入，留给调用方
        ``_run_stream_impl`` —— 它才知道后面还有什么要收尾。

        「改一下」做成**循环**而不是单次：用户可能来回改两三稿才满意，
        每一稿都重新出计划、重新等确认，直到他点「开始执行」或「不用了」。
        """
        decider = self.config.plan_decider
        if decider is None:  # pragma: no cover - 调用方已判过，纯防御
            return

        feedback = ""
        while True:
            plan = await self.planner.make_plan(
                self.utility_llm,
                user_input=user_input,
                tool_names=self.skills.all_names(),
                feedback=feedback,
            )
            if plan is None:
                # 解析不出"至少两步" → 这不是多步任务，别打扰用户，按原 ReAct 走。
                # 首次就如此属于正常降级（与旧行为一致）；重拟后如此说明用户的
                # 意见把它缩成了单步，同样直接放行。
                self._active_plan = None
                return

            # 每一版计划换一个新 id：用户点「改一下」重拟后，旧卡片上的按钮
            # 就不该再能唤醒新一版计划（前端也据 id 判断卡片是否还"活着"）
            plan.id = uuid4().hex
            plan.state = "awaiting"
            self._active_plan = plan
            yield AgentEvent("plan", plan.to_dict())

            approved, feedback = await decider(plan.to_dict())
            if approved:
                plan.state = "executing"
                yield AgentEvent("plan", plan.to_dict())
                return
            if not feedback.strip():
                # 「不用了」：用户主动放弃，卡片上如实标成已取消
                plan.state = "aborted"
                yield AgentEvent("plan", plan.to_dict())
                return
            logger.info("用户对上一版计划提了修改意见，重拟一版")

    def _consume_plan_update(
        self, tc: ToolCall, outcome: tuple[str, str, float]
    ) -> tuple[tuple[str, str, float], AgentEvent | None]:
        """把 ``plan_update`` 的结果换成"引擎按真实计划裁决"的结果。

        返回（可能被替换过的）工具结果 + 要广播的进度事件。
        不是 ``plan_update``、或本轮根本没走计划模式时，原样返回。
        """
        if tc.name != "plan_update":
            return outcome, None
        status, _, duration_ms = outcome
        plan = self._active_plan
        if plan is None:
            # 没有计划却来汇报（比如普通对话里模型顺手调了它）：
            # 明确拒绝，绝不假装成功 —— 否则模型会以为汇报过了，一路跑下去。
            return (
                status,
                "[本轮没有执行计划] plan_update 只在计划模式下有效，本次汇报未生效。"
                "请直接继续完成任务，不要再调用它。",
                duration_ms,
            ), None
        ok, message = apply_plan_update(plan, tc.arguments)
        if not ok:
            # 步号非法：不产生进度事件，但把"可用步号"回填给模型
            return (status, message, duration_ms), None
        if plan.state == "executing" and all(
            step.status in ("done", "failed") for step in plan.steps
        ):
            plan.state = "done"
        self._sync_plan_message()
        return (status, message, duration_ms), AgentEvent("plan_update", plan.to_dict())

    def _sync_plan_message(self) -> None:
        """把计划的最新状态回写到落库用的那条消息上。

        进度是逐次汇报上来的，而历史记录读的是"消息上的 plan 字段" ——
        不回写的话，用户重开对话看到的永远是最初那一版（一步都没做）。
        """
        if self._plan_message is not None and self._active_plan is not None:
            self._plan_message.plan = self._active_plan.to_dict()

    # ------------------------------------------------------------------ #
    # 中断收尾
    # ------------------------------------------------------------------ #
    def _seal_dangling_tool_calls(self) -> int:
        """给「已声明但没有结果」的 tool_call 补一条中断说明，返回补齐数量。

        直接从记忆里反查而不是靠外部记账：assistant(tool_calls) 是主循环
        先整批写入的，工具则是一个个执行的，中断可能发生在任意一条之间。
        从消息序列反查能覆盖所有中断点，也不依赖调用顺序。
        """
        messages = self.memory.messages
        answered = {
            message.tool_call_id
            for message in messages
            if message.role == "tool" and message.tool_call_id
        }

        for message in reversed(messages):
            if message.role != "assistant":
                continue
            # 只看最后一条 assistant：它才是「可能没执行完」的那一批
            if not message.tool_calls:
                return 0
            missing = [call for call in message.tool_calls if call.id not in answered]
            for call in missing:
                self.memory.add_tool(
                    call.id, call.name, "[任务已中断] 该工具未执行完成，如需继续请重新提出。"
                )
            return len(missing)
        return 0

    # ------------------------------------------------------------------ #
    # 工具执行
    # ------------------------------------------------------------------ #
    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        failure_counts: dict[str, int],
        disabled_tools: set[str],
    ) -> AsyncIterator[AgentEvent]:
        """执行一批工具调用。

        **互不冲突的调用会并行执行**：模型一口气请求「查天气 + 查日程 + 读表格」
        时，串行等于把三个网络往返加起来，用户要多等好几秒。

        但并行是有边界的，见 ``_can_run_parallel``。
        """
        prepared: list[tuple[ToolCall, Any, str]] = []

        # 先把卡片推给前端再执行：并行时"卡片先全部出现、结果陆续回填"
        # 比"一张张卡依次冒出来"更贴近实际发生的事情
        for tc in tool_calls:
            meta = self.skills.get(tc.name).meta if self.skills.has(tc.name) else None
            display_name = (meta.display_name or tc.name) if meta else tc.name

            if tc.name in disabled_tools:
                message = f"工具 {tc.name} 已因连续失败被停用，请改用其他方案。"
                self.memory.add_tool(tc.id, tc.name, message)
                yield AgentEvent(
                    "tool_result",
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "display_name": display_name,
                        "status": "error",
                        "result": message,
                        "duration_ms": 0,
                    },
                )
                continue

            yield AgentEvent(
                "tool_call",
                {
                    "id": tc.id,
                    "name": tc.name,
                    "display_name": display_name,
                    "description": meta.description if meta else "",
                    "params": tc.arguments,
                    "permission_level": meta.permission_level if meta else "safe",
                    # 该次调用的开始时刻（epoch 秒）：界面把它显示在工具卡片上 ——
                    # 正文里不许模型写时间戳，时间跟工具卡走
                    "started_at": time.time(),
                },
            )
            prepared.append((tc, meta, display_name))

        if not prepared:
            return

        if self._can_run_parallel(prepared):
            outcomes = await asyncio.gather(
                *(self._run_one(tc, failure_counts, disabled_tools) for tc, _, _ in prepared)
            )
            for (tc, _, display_name), outcome in zip(prepared, outcomes, strict=True):
                # plan_update 的进度由引擎按真实计划裁决（见 _consume_plan_update），
                # 必须在 add_tool **之前**换掉回填文本，否则模型拿到的是技能的假回话
                outcome, plan_event = self._consume_plan_update(tc, outcome)
                message = self.memory.add_tool(tc.id, tc.name, outcome[1])
                # 命中可疑指令就单独发一条事件。
                # **这是三层防护里最不该省的一层**：边界标记与就地警示都可能被模型
                # 绕过，但"某个工具返回了可疑内容"这件事必须让人知道 ——
                # 否则回答看起来一切正常，实际却是被一段文件内容指挥出来的。
                if message.injection_hits:
                    yield self._injection_event(tc, display_name, message.injection_hits)
                yield self._result_event(tc, display_name, *outcome)
                if plan_event is not None:
                    yield plan_event
            self._refresh_system_if_persona_changed(prepared, outcomes)
            return

        persona_touched = False
        for tc, _, display_name in prepared:
            outcome = await self._run_one(tc, failure_counts, disabled_tools)
            # 同并行分支：plan_update 的进度以引擎的裁决为准
            outcome, plan_event = self._consume_plan_update(tc, outcome)
            message = self.memory.add_tool(tc.id, tc.name, outcome[1])
            if message.injection_hits:
                yield self._injection_event(tc, display_name, message.injection_hits)
            if tc.name == "self_persona_update" and outcome[0] == "ok":
                persona_touched = True
            yield self._result_event(tc, display_name, *outcome)
            if plan_event is not None:
                yield plan_event
        if persona_touched:
            self._refresh_system_if_persona_changed()

    def _refresh_system_if_persona_changed(
        self,
        prepared: list[tuple[ToolCall, Any, str]] | None = None,
        outcomes: list[tuple[str, str, float]] | None = None,
    ) -> None:
        """人格/规则/记忆文件被改写后，**立即**重算 system 消息。

        ``ensure_system`` 只在每轮开始时执行一次（为了 prompt cache），这意味着
        助手在同**一轮**里改完自己的 SOUL/RULES/MEMORY/USER 后，本轮后续的
        推理用的还是旧人格 —— 用户的体感是"改了但没生效"。这里在确认写入
        成功后立刻重建：代价是缓存前缀作废一次（本轮剩下的推理不走缓存），
        换来的是行为马上符合预期，值得。
        """
        if prepared is not None and outcomes is not None:
            changed = any(
                tc.name == "self_persona_update" and outcome[0] == "ok"
                for (tc, _, _), outcome in zip(prepared, outcomes, strict=True)
            )
            if not changed:
                return
        self.memory.ensure_system(self._system_prompt())

    @staticmethod
    def _injection_event(
        tc: ToolCall, display_name: str, hits: list[str]
    ) -> AgentEvent:
        logger.warning("工具 %s 的返回内容疑似包含指令注入：%s", tc.name, "、".join(hits))
        return AgentEvent(
            "injection_suspected",
            {
                "id": tc.id,
                "name": tc.name,
                "display_name": display_name,
                # 只给标签，不给原文 —— 原文已经在上下文里了，
                # 再往界面上搬一遍只是多一处泄漏面
                "labels": list(hits),
            },
        )

    def _can_run_parallel(self, prepared: list[tuple[ToolCall, Any, str]]) -> bool:
        """判断这批调用能不能并发。

        两条否决条件都不是性能考虑，而是正确性：

        1. **同名工具不并发** —— 两个 ``write_file`` 同时写同一路径，最终内容
           取决于调度顺序，而两者都会回报"成功"；
        2. **需要确认的工具不并发** —— 同时弹两个确认框，用户根本分不清
           自己正在批准哪一件；而且确认本身就该按模型给出的顺序来。
        """
        if len(prepared) < 2:
            return False

        names = [tc.name for tc, _, _ in prepared]
        if len(set(names)) != len(names):
            return False

        for _, meta, _ in prepared:
            if meta is None:
                continue
            if self.skills.guard.resolve_level(meta) != "safe":
                return False
        return True

    async def _run_one(
        self,
        tc: ToolCall,
        failure_counts: dict[str, int],
        disabled_tools: set[str],
    ) -> tuple[str, str, float]:
        """执行单个工具，返回 ``(status, 回填文本, 耗时毫秒)``。"""
        started = asyncio.get_event_loop().time()
        status = "ok"
        try:
            result_text = await self.skills.execute(
                tc.name,
                tc.arguments,
                self.ctx,
                # 把"本会话允许的技能集合"传下去：模型可能凭历史消息或幻觉
                # 发出一个已禁用工具的调用，"没暴露"和"不能执行"是两件事
                within=self.config.enabled_skills,
                # 专属技能同理："清单里没给这个搭子"和"调不了"缺一不可
                for_assistant=self.config.target_assistant,
            )
            failure_counts.pop(tc.name, None)
        except SkillPermissionError as exc:
            status = "denied"
            result_text = f"[权限拒绝] {exc}"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任何工具异常都回填给模型
            status = "error"
            failure_counts[tc.name] = failure_counts.get(tc.name, 0) + 1
            result_text = f"[工具执行失败] {exc}"
            if failure_counts[tc.name] >= self.config.same_tool_failure_tolerance:
                disabled_tools.add(tc.name)
                result_text += (
                    f"\n（工具 {tc.name} 已连续失败 {failure_counts[tc.name]} 次，"
                    f"本轮任务内不再提供该工具，请换一种方案，或向用户说明原因。）"
                )
        duration_ms = round((asyncio.get_event_loop().time() - started) * 1000, 2)
        return status, result_text, duration_ms

    @staticmethod
    def _result_event(
        tc: ToolCall, display_name: str, status: str, result_text: str, duration_ms: float
    ) -> AgentEvent:
        return AgentEvent(
            "tool_result",
            {
                "id": tc.id,
                "name": tc.name,
                "display_name": display_name,
                "status": status,
                "result": result_text,
                "duration_ms": duration_ms,
            },
        )

    # ------------------------------------------------------------------ #
    # 提示词与摘要
    # ------------------------------------------------------------------ #
    def _system_prompt(self) -> str:
        """本轮要用的 system：**只有人格文档**（外加不支持工具的模型的工具文本段）。

        ## 为什么这里既没有"兜底提示词"，也没有当前日期

        完整提示词由搭子自己的五个人格文档拼成（``assistants/persona.py`` 的
        IDENTITY → SOUL → USER → MEMORY → RULES），**不再回落**内置的那段通用
        提示词 —— 那是用户明确要求去掉的日常兜底，也不再注入"当前日期"。

        日期同样刻意不注入：``system`` 位于消息序列的**第 0 位**，而各家厂商的
        prompt caching 本质都是**前缀匹配**，任何随时间变化的内容都会让
        「system + 全部历史消息」的缓存整段失效（那是长会话里最大的一块输入
        成本，命中价通常只有 1/10 ~ 5 折）。需要精确时间时由模型调用
        ``system_time`` 技能，而不是把时间塞进每一轮请求里。

        人格非空是**结构保证**：``build_persona_section`` 总会注入「你的名字」，
        所以这里不会拼出一条空的 system。

        ``supports_tools=false`` 的模型拿不到工具 Schema，全靠提示词兜底，
        所以这里把工具清单渲染成文本说明。用**完整**的启用技能列表（不含本轮
        被临时停用的），否则 system 会随 ``disabled_tools`` 变化 ——
        而它一变，``ensure_system`` 就会替换第 0 位消息，缓存前缀直接报废。
        """
        # 人格与记忆拼在**这里**，而不是另起一条 system 消息：
        # ensure_system 每轮都会把第 0 位消息替换成 _system_prompt() 的结果，
        # 另起一条会被静默抹掉（这正是摘要必须单独插的原因，但人格不该那样）。
        # 拼进返回值还有一个好处：用户改完 SOUL.md，下一轮立即生效。
        persona = self.config.persona
        if callable(persona):
            persona = persona()
        base = persona or ""
        # 回复正文禁止时间戳：发给模型的历史每条都带
        # `[MM-DD HH:MM]` 前缀（memory/short_term.py，给模型的时间维度），
        # 模型会**模仿**这个格式在正文里刷屏。界面本来就显示每条消息与每次
        # 工具调用的时刻，正文里再写一遍纯属噪音。⚠️ 这里是**静态文本**，
        # 不会破坏 prompt caching 的前缀匹配（与上面"不注入当前日期"同一条规矩）。
        base = f"{base}{_NO_STAMP_RULE}"
        if self.llm.supports_tools:
            return base
        section = render_tools_section(self._tool_specs(None) or [])
        return f"{base}\n\n{section}" if section else base

    def _tool_summary(self) -> str:
        """摘要本轮做过的操作，供交付前自检判断"该做的做了没"。

        ⚠️ **不裁剪**（这里曾经是"每条只留 200 字符 + 只取最近 10 条"）。

        那个裁剪的理由是"自检不需要那么多细节"，但它有两个说不通的地方：
        一是自检要判断的恰恰是"该做的做了没"，而"做了什么"的细节被砍掉后
        它就只能靠猜；二是用户的要求是"不要做任何截断/省略"，这条规则没有
        例外条款。工具结果本来就已在上下文里，这里再复制一份给自检并不会
        多出多少 token，却能让自检看到完整过程。
        """
        lines: list[str] = []
        for message in self.memory.messages:
            if message.role != "tool":
                continue
            text = " ".join(message.content.split())
            lines.append(f"- {message.name or '工具'}：{text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _tool_specs(self, disabled_tools: set[str] | None) -> list[ToolSpec] | None:
        """构建工具列表；没有可用工具时返回 None。

        刻意**不**在这里判断 ``supports_tools``：不支持原生工具调用的模型
        同样需要这份清单（渲染成文本写进 system），是否把它塞进请求体
        由调用点决定。
        """
        if len(self.skills) == 0:
            return None
        specs = self.skills.to_tool_specs(
            filter_names=self.config.enabled_skills,
            for_assistant=self.config.target_assistant,
        )
        if disabled_tools:
            specs = [s for s in specs if s.name not in disabled_tools]
        return specs or None

    def _done_event(self, iterations: int, **extra: Any) -> AgentEvent:
        return AgentEvent(
            "done",
            {
                "trace_id": self.tracer.trace_id,
                "iterations": iterations,
                # 用完整用量（含缓存命中量/命中率）：界面要据此显示
                # "这次有多少输入走了缓存"，那正是成本优化的效果所在
                "usage": self.tracer.usage.to_dict(),
                **extra,
            },
        )

    def _span(self, name: str, **meta: Any):
        return self.tracer.span(name, **meta)
