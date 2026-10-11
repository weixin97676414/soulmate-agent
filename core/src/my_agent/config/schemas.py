"""配置数据模型（Pydantic v2）。

客户端场景下配置由图形化设置中心读写，因此持久化格式选用 JSON 而非 YAML
（见《Windows客户端开发计划》8.1 节）。校验规则与开发文档第 9 章一致。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 这个模块以前没有任何日志 —— 而 `AssistantProfile._normalize_reasoning_effort`
# 需要**在归一化非法档位时留一条 warning**（那是"拼错的档位不再静默失效"的唯一线索）。
logger = logging.getLogger(__name__)

# 注意这里**没有** ``custom``。
# 枚举里曾经声明过它，但工厂遇到它直接抛 ConfigError —— 于是
# "配置项存在、实现不存在"，用户在界面上选得出来、保存得了、一请求就报错。
# 这类不一致比缺功能更难排查（看起来像是配置写错了），所以从枚举移除。
AdapterKind = Literal["openai_compat", "ollama", "anthropic"]
ConfirmMode = Literal["interactive", "deny", "auto_approve"]


class PeakWindow(BaseModel):
    """高峰时段（分时定价用）。

    ``days`` 是 ISO 周几（1=周一 … 7=周日）；空列表 = 每天。
    ``start``/``end`` 是 ``HH:MM``；``start > end`` 表示跨午夜（如 22:00→06:00）。
    """

    days: list[int] = Field(default_factory=list, description="1-7；空=每天")
    start: str = Field("00:00", description="HH:MM")
    end: str = Field("00:00", description="HH:MM")

    def contains(self, at: datetime) -> bool:
        if self.days and at.isoweekday() not in self.days:
            return False
        minutes = at.hour * 60 + at.minute
        start = self._minutes(self.start)
        end = self._minutes(self.end)
        if start <= end:
            return start <= minutes < end
        # 跨午夜：22:00-06:00
        return minutes >= start or minutes < end

    @staticmethod
    def _minutes(text: str) -> int:
        try:
            hour, minute = text.split(":", 1)
            return int(hour) * 60 + int(minute)
        except Exception:  # noqa: BLE001 - 坏配置不炸计价，回落成全天不命中
            return -1


class ModelSpec(BaseModel):
    """一个具体可用的模型端点。"""

    id: str = Field(..., description="模型在框架内的唯一标识，如 deepseek-chat")
    name: str = Field("", description="界面上展示的友好名称")
    provider: str = Field("", description="服务商标识，如 deepseek / openai / ollama")
    adapter: AdapterKind = "openai_compat"
    base_url: str = Field("", description="OpenAI 兼容端点根地址")
    api_key: str = Field("", description="访问密钥（独立运行时由系统加密托管，配置文件里留空）")
    # 是否让请求走**系统代理**。默认关 —— 实测用户机器上系统代理对国内厂商
    # （硅基流动/百炼/DeepSeek）直接表现为连接超时，而直连都在 300ms 内；
    # 需要代理访问 OpenAI/Anthropic 的用户可以按模型打开。
    # 本地端点（Ollama 等）在适配器里始终直连，与此字段无关。
    use_system_proxy: bool = Field(False, description="请求是否走系统代理")
    # ---- 仅请求侧的两个标记（都不落盘）--------------------------------- #
    #
    # ⚠️ **"空值 = 清除"这个语义已经被彻底删除。**
    #
    # 它曾经是本项目反复复发的事故源：只要前端在某一刻把 ``api_key`` 提交成空串
    # （而"某一刻"的触发条件有四五种：密钥库条目缺失、注入时机、
    # 明文回填的 IPC 竞态、掩码格式不一致……），用户已配好的 Key 就会被真的抹掉，
    # 症状是"模型突然不能用了"，而用户自己也不知道刚才点了什么。
    #
    # 现在：**空值永远只表示"我没改"**，一律沿用已保存的值。
    # 要真的删掉，必须由用户显式动作带上 ``clear_api_key=True``。
    #
    # ``api_key_unchanged`` 保留仅为兼容旧前端；新前端不需要它 ——
    # 因为 ``GET /v1/models`` 现在直接下发明文，字段里永远是真字符。
    api_key_unchanged: bool = Field(
        False,
        exclude=True,
        description="仅请求侧：true 表示沿用旧配置里的 Key（忽略本次提交的值）",
    )
    #: 仅请求侧：**用户显式要求清除**这条模型的密钥（界面上的「清除密钥」按钮）。
    #: 这是全应用**唯一**能删掉密钥的入口。
    clear_api_key: bool = Field(
        False,
        exclude=True,
        description="仅请求侧：true 表示显式清除该模型的密钥",
    )
    # 仅请求侧（同样不落盘）：「同步服务商模型」新增的条目用它声明
    # "我的 Key 从旧配置里的那条继承"。因为真实 Key 只存在后端，
    # 前端拿着的是脱敏预览，想带也带不了。
    inherit_key_from: str = Field(default="", exclude=True)
    model_name: str = Field(..., description="请求体里传给厂商的真实模型名")

    token_limit: int = Field(32768, ge=1024, description="上下文窗口大小")
    supports_tools: bool = True
    supports_stream: bool = True
    timeout: float = Field(120.0, gt=0)

    # 能力档位，供 ModelRouter 按任务复杂度挑选（见 llm/router.py）。
    # 默认 standard —— 不预设任何厂商档位，因为"哪个模型便宜/哪个强"随厂商
    # 与时间变化，写死会过时；由用户在设置里标注才是准的。
    tier: Literal["cheap", "standard", "strong"] = Field(
        "standard", description="能力档位：cheap（便宜快速）/ standard / strong（最强）"
    )
    # 是否具备视觉能力（可接收图片）。默认 False：不预设，
    # 因为绝大多数 OpenAI 兼容端点其实是纯文本模型，猜错会让用户白传图片。
    supports_vision: bool = Field(False, description="是否支持图片输入")
    # 是否接受"思考强度"。默认 True（与其他能力开关相反），因为**只有用户主动
    # 选过档位时才会发送这个字段** —— 不选的人完全不受影响，而选的人碰上不认的
    # 网关时由 llm/platform.py 的自适应回退兜住。默认 False 反而会让支持它的用户
    # 连控件都看不到。
    supports_reasoning: bool = Field(True, description="是否接受思考强度参数")

    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int | None = Field(None, gt=0)
    enabled: bool = True
    is_default: bool = False

    # 备用模型 id 列表，按顺序尝试（见 llm/fallback.py 的说明）。
    # 留空表示不降级 —— 默认值必须是不降级，因为这是一家 composer 之外的第三方服务：
    # 用户的请求会不会发到另一家、花另一家的钱，必须由用户显式决定。
    fallback_models: list[str] = Field(default_factory=list, description="备用模型 id，按顺序降级")

    # ---- 价格（可选，仅用于费用估算）----------------------------------- #
    #
    # **刻意不给默认值。** 厂商调价频繁，内置一份"参考价"会让界面显示一个
    # 看起来很精确、实则过时的金额——而用户看到"费用"两个字就会当真。
    # 留空时界面如实显示「未配置价格」，用户填了才算。
    #
    # 单位统一为「每百万 token」，与厂商报价单一致，避免换算错位。
    price_input_per_1m: float | None = Field(None, ge=0, description="未命中输入的单价")
    price_cached_input_per_1m: float | None = Field(
        None,
        ge=0,
        description="命中缓存的输入单价；留空则按未命中价计算（不打折，偏保守）",
    )
    price_output_per_1m: float | None = Field(None, ge=0, description="输出单价")

    # ---- 高峰时段价格（DeepSeek 式分时定价，产品要求）--------------------- #
    # 当前时间落在任一 peak_windows 内 → 用峰值价；某一项没填峰值就退回普通价。
    price_input_per_1m_peak: float | None = Field(None, ge=0, description="高峰时段的输入单价")
    price_output_per_1m_peak: float | None = Field(None, ge=0, description="高峰时段的输出单价")
    # 高峰时段的缓存命中输入价（产品要求：高峰价除输入/输出外还要有缓存命中）
    price_cached_input_per_1m_peak: float | None = Field(
        None, ge=0, description="高峰时段的缓存命中输入单价；留空回退普通缓存价"
    )
    peak_windows: list[PeakWindow] = Field(
        default_factory=list, description="高峰时段列表（一般配三个）"
    )

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def display_name(self) -> str:
        return self.name or self.model_name or self.id

    def masked_api_key(self) -> str:
        """返回脱敏后的 Key，用于回传给前端展示。

        ⚠️ **这个格式必须与桌面端 ``desktop/electron/secrets.ts`` 的 ``maskSecret()``
        逐字符一致。** 两边曾经不一致（这里是「前 4 位 + 6 个星」，那边是
        「前 3 位 + 4 个星」），后果是"这个 Key 用户没改过"的判定失效 ——
        掩码串被当成真 Key 写进配置，症状是**保存后立刻连不上、重启又好了**。
        """
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}{'*' * 6}{self.api_key[-4:]}"


class ModelsConfig(BaseModel):
    """models.json 的结构。"""

    default_model: str = ""
    models: list[ModelSpec] = Field(default_factory=list)

    def get(self, model_id: str) -> ModelSpec | None:
        return next((m for m in self.models if m.id == model_id), None)

    def resolve_default(self) -> ModelSpec | None:
        if self.default_model:
            found = self.get(self.default_model)
            if found and found.enabled:
                return found
        return next((m for m in self.models if m.enabled), None)


class ScheduledTaskSpec(BaseModel):
    """一个自动化任务。

    与「提醒」（reminder）的区别值得说清楚：提醒是**到点提醒人**，只发一条通知；
    自动化任务是**到点干活** —— 真的调用模型、消耗 token、产出一份结果。
    成本量级完全不同，所以这里默认 ``enabled=False``，必须用户显式打开。

    ## 「什么时候跑」与「该不该跑」是两件事

    ``trigger`` 系列字段决定**什么时候检查**；``condition`` 决定**这次检查要不要真的执行**。
    两者刻意分开而不是做成互斥的"触发方式"：用户想要的"网页有变化就告诉我"
    实际语义是"每隔一段时间看一眼，变了才跑"—— 没有时间轴就没有"看一眼"这件事。

    条件未满足时这一轮**不算执行**（不调模型、不花钱），但要等下个时间点才会再看一次，
    而不是每个 tick 都去抓一遍网页 —— 否则用户配的 1 分钟间隔会被我们放大成
    "每 10 秒请求一次人家的站点"。
    """

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    prompt: str = Field(..., min_length=1, description="每轮交给智能体的指令")
    assistant_id: str = Field("", description="用哪个助手跑；留空用默认配置")
    enabled: bool = False

    # ---- 什么时候检查（时间轴）----------------------------------------- #
    # interval：每 N 分钟；daily：每天 HH:MM；weekly：每周几的 HH:MM
    trigger: Literal["interval", "daily", "weekly"] = Field(
        "interval", description="interval=按间隔；daily=每天；weekly=每周"
    )
    interval_minutes: int = Field(60, ge=1, le=10080, description="间隔（分钟），上限一周")
    at_time: str = Field("09:00", description="每天 / 每周的执行时刻 HH:MM（24 小时制）")
    weekday: int = Field(0, ge=0, le=6, description="每周几执行；0=周一，6=周日")
    # interval 的**起始时间**（产品要求）：从这一刻开始计时，之后每
    # ``interval_minutes`` 分钟跑一次；到这一刻之前一次都不跑。
    # ⚠️ 空串是**合法值**，语义是"从现在起算"，与没有这个字段之前的行为完全一致 ——
    # 老版本写下的 settings.json 里根本没有这个键，一上来就必填会让老用户的所有任务
    # 在读配置时直接报错（而且是在启动路径上，症状是"客户端起不来"）。
    # daily / weekly 不用它：它们的时刻已经由 ``at_time`` 指定，不需要第二个锚点。
    start_at: str = Field(
        "",
        description="trigger=interval 时的起始时间 YYYY-MM-DDTHH:MM（本机时间）；留空=从现在起算",
    )

    # ---- 该不该真的跑（可选条件）--------------------------------------- #
    # none：到点就跑；url_changed：抓到的网页内容变了才跑；
    # file_changed：文件的修改时间或大小变了才跑。
    #
    # ⚠️ 第一次检查只**建立基线**（记住当前内容 / 现在的修改时间），不触发执行：
    # 否则"新建一个监控任务"这个动作本身就会立刻跑一轮，用户会以为它坏了。
    # 基线只存在内存里，所以重启后第一次检查同样只建立基线，不会把重启
    # 当成"网页变了"。
    condition: Literal["none", "url_changed", "file_changed"] = Field(
        "none", description="none=无条件；url_changed=网页有变化；file_changed=文件有更新"
    )
    condition_target: str = Field(
        "", description="条件的目标：网页地址（http/https）或本地文件路径"
    )

    # ---- 这条任务是"谁建的"（产品要求）---------------------- #
    # 用途只有一个：**锁定判定**。内置搭子相关的任务里，
    # 「我们预置的」与「这四个搭子自己建的」用户不能改/关/删，只能让搭子改；
    # 用户自己手工建的（哪怕指定内置搭子跑）不受限。判定见
    # ``task_store.locked_for_user()``，裁决只放在 HTTP 路由层。
    #
    # ⚠️ 默认 ``user``：这个字段是本次才加的，老配置里根本没有它 ——
    # 宁可少锁（老任务一律当"用户建的"），也不能把用户既有任务一夜之间锁死。
    origin: Literal["user", "agent", "builtin"] = Field(
        "user", description="谁建的：user=界面上手工建；agent=搭子在对话里建；builtin=客户端预置"
    )

    # ---- 跑完要不要打扰 ------------------------------------------------ #
    # 置真时调度器**不发通知事件**（那四条「全员进化」任务用：每周一次、静默收工，
    # 结果在那个 [自动化] 会话里，用户想看自己进去看）。
    # 留痕（审计）照旧写 —— 静默的是"弹窗"，不是"记录"。
    silent: bool = Field(False, description="跑完不推通知（只留痕）")

    @field_validator("at_time")
    @classmethod
    def _check_at_time(cls, value: str) -> str:
        """``HH:MM`` 必须是真实存在的时刻 —— 25:00 这种值会让"下次执行"永远算不出来。"""
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", (value or "").strip())
        if not match:
            raise ValueError("执行时刻必须是 HH:MM 格式，例如 09:00")
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError("执行时刻不合法（小时 00-23，分钟 00-59）")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("start_at")
    @classmethod
    def _check_start_at(cls, value: str) -> str:
        """``YYYY-MM-DDTHH:MM`` 必须是真实存在的时刻（界面用 ``datetime-local`` 控件喂它）。

        只做"能不能解析"，不做"必须在未来"这类判断：新建任务时把起始时间填成过去
        是**合法**的（等于"从现在起算"），而且用户也可能把老任务的时间改成过去
        来"让它马上进入周期"—— 拿"必须在未来"卡住它，只会让用户改不动。
        """
        raw = (value or "").strip()
        if not raw:
            return ""
        try:
            moment = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
        except ValueError as exc:
            raise ValueError("起始时间必须是 YYYY-MM-DDTHH:MM 格式，例如 2026-09-30T09:00") from exc
        return moment.strftime("%Y-%m-%dT%H:%M")

    @model_validator(mode="after")
    def _check_condition_target(self) -> ScheduledTaskSpec:
        """选了条件就必须给出目标 —— 空的 ``condition_target`` 只会让任务静默不跑。"""
        if self.condition != "none" and not self.condition_target.strip():
            raise ValueError("选择了触发条件，就必须填写网页地址或文件路径")
        return self


class ScheduledTaskDraft(ScheduledTaskSpec):
    """新建任务时的入参：与任务**同构**，只是 ``id`` 可以留空（由后端生成）。

    继承而不是另抄一份字段列表，是为了让"任务有哪些字段"只有一处定义 ——
    以后加一种触发方式时，抄出来的入参模型一定会漏。
    """

    id: str = Field("", max_length=64, description="留空则由后端生成")


class AgentSettings(BaseModel):
    """Agent 引擎参数，对应开发文档 config/agent.yaml。"""

    # 模型↔工具的**往返步数**上限（产品约定："不设对话轮数上限"）。
    #
    # 原先是 10、上限 50 —— 实测反馈"没执行几个就提示已达到最大执行轮数"，
    # 一个正常任务轻松就用完 10 个来回。改成 500、上限放宽到 10 万：
    # 对真实任务等于不限制，同时留一个极端兜底（真死循环时别把 token 无限烧下去）。
    max_iterations: int = Field(
        500, ge=1, le=100000, description="单次任务最大执行步数（模型↔工具往返），防失控"
    )
    # 默认 5 是当年防失控的保守值，但对"批量处理 30 个文件"这类正常需求
    # 会半路掐断（表现为"做着做着就停了"）。改成 500：真失控有
    # same_tool_failure_tolerance 与用户随时可停，不该靠一个这么小的数兜底。
    max_tool_calls_per_turn: int = Field(500, ge=1, le=100000)
    temperature: float = Field(0.7, ge=0, le=2)

    # ---- 另外三个采样参数：默认「不发送」-------------------------------- #
    # ``None`` 的含义是**这个字段根本不发**，而不是"发默认值"。为什么这个区别
    # 关键，见 llm/platform.py 的 clamp：不接受的厂商收到默认值同样会 400，
    # 问题出在字段本身而不在取值。
    #
    # 默认全关：大多数用户不需要调它们，而每多显式发一个字段，
    # 就多一分被某家网关拒掉的可能。
    top_p: float | None = Field(None, gt=0, le=1, description="核采样阈值；留空则不发送")
    # 频率惩罚 / 存在惩罚：取值范围 -2~2，正数才生效（负数反而是鼓励重复）。
    # 两者作用相反：前者压"同一个词反复出现"，后者压"已经提过的词"从而逼出
    # 新内容。同时调容易互相抵消，界面上的说明要写清楚。
    frequency_penalty: float | None = Field(
        None, ge=-2, le=2, description="频率惩罚（治重复用词）"
    )
    presence_penalty: float | None = Field(
        None, ge=-2, le=2, description="存在惩罚（促新话题）"
    )

    system_prompt: str = ""
    # ⚠️ 没有任何地方读这个字段。真正生效的是 ``security.confirm_mode``
    # （见 SecuritySettings）—— 权限判定走 ``PermissionGuard``，它只认那一处。
    # 留着只是不动旧配置的形状，排查"权限为什么没生效"时别按这个值判断。
    confirm_mode: ConfirmMode = "interactive"
    # 上下文预算的**硬上限**。``0`` = 跟随所选模型的上下文窗口（推荐，也是默认）。
    #
    # 它原先是固定 32000，后果比"值偏小"严重得多：``MemoryManager`` 直接拿它当
    # 裁剪预算，于是一个支持 100 万 token 的模型，记忆仍然在 3.2 万处被裁掉，
    # 而界面上把"上下文窗口"改到 100 万看起来完全没生效。
    # 这类"配置了但不起作用"的问题最难排查 —— 用户第一反应是怀疑自己没保存成功。
    #
    # 改成 0 = 跟随模型之后：窗口由模型配置（`ModelSpec.token_limit`）决定，
    # 这里只在用户**主动想省钱**时才填一个更小的数当上限。
    max_context_tokens: int = Field(0, ge=0, description="上下文硬上限；0=跟随模型窗口")
    # ⚠️ 这里**刻意没有** ``tool_result_max_chars``。
    #
    # 它曾经存在（默认 4000），把超长工具结果砍成"头 2000 + 中间省略 + 尾 2000"，
    # 而中间那段内容**被真正销毁**：对 http 取回、记忆检索、MCP 工具这些不产出
    # 文件的能力，"完整内容已落产物目录"那句注释根本不成立。
    # 用户的反馈是"很多用户的外部服务是花钱买的，我们没有资格给别人截掉或者省略"。
    #
    # 现在超容量时改为**无损外置**（全文写盘 + 投递开头与续读指引），
    # 所以这个配置项没有存在的意义了 —— 留一个"会丢内容"的旋钮本身就是隐患。
    same_tool_failure_tolerance: int = Field(3, ge=1, le=10)

    # ---- 上下文压缩（见 agent/context.py）------------------------------- #
    # 用量到这个比例就开始把早期对话压成摘要。提前压比撞到厂商硬限制再压更稳，
    # 也避免"输入刚好卡满、输出放不下"导致模型返回空内容
    compress_threshold: float = Field(0.8, ge=0.3, le=1.0)
    # 最近多少条消息不参与压缩 —— 它们是"当前在做什么"的直接上下文
    keep_recent_messages: int = Field(6, ge=2, le=40)
    # 压缩 / 规划 / 自检这三件事各要**额外**调一次模型，而它们产出的都是
    # "给自己看的中间结果"：填一个模型 id 就让它们走那个模型（省钱或反过来
    # 用更强的模型压得更准）；**留空 = 跟随当前会话的模型**，也就是老行为。
    #
    # 为什么不做成三个字段：这三个调用点对用户来说是同一件事（"不是回答问题
    # 的那次调用"），拆开只会让设置页多出三个下拉框，而没人会分别配它们。
    #
    # 配错的容错在 `llm/factory.py::resolve_utility_llm`：模型不存在或已停用时
    # **退回当前会话模型**并记一条 warning —— 不能让"辅助模型不存在"这种小事
    # 把整轮回答掐死。
    utility_model_id: str = Field(
        "",
        description="压缩 / 规划 / 自检用哪个模型（填模型 id）；留空 = 跟随当前会话模型",
    )

    # ---- 两个要多花一次 LLM 调用的增强，默认关闭 ------------------------- #
    # 复杂任务先出计划（agent/planner.py）
    enable_planner: bool = False
    # 交付前自检一轮（agent/reflection.py）
    enable_reflection: bool = False
    reflection_rounds: int = Field(1, ge=1, le=3)

    # AI 在单聊里自己发起后台群聊时，**自动弹一个只读观察窗**让用户看得见它在干什么。
    #
    # 默认开：后台讨论如果完全不可见，用户会以为"它是不是什么都没做"（这正是后台类功能
    # 最招人恨的地方）。观察窗不抢焦点（见 electron/main.ts 的 showInactive），
    # 但毕竟会多出一个窗口 —— 所以给一个可关的开关，关掉它的人通常是不想被打断。
    auto_open_group_window: bool = True

    # ---- 并发限流 -------------------------------------------------------- #    # 同时进行的对话数上限。不限制的话，用户连开十个会话就等于同时向厂商
    # 发十路请求：轻则触发限流、重则把本机事件循环与内存压垮。
    # 注意这是**全局**上限，会话级串行由 Session.lock 单独负责。
    max_concurrent_chats: int = Field(4, ge=1, le=64)
    # 排队等待上限（秒）。超时后**明确拒绝并说明原因**，而不是让界面一直转圈 ——
    # "点了没反应"是用户体验里最糟的一种失败。
    queue_wait_seconds: float = Field(15.0, ge=0, le=300)

    # ---- 模型路由（llm/router.py）--------------------------------------- #    # 按任务复杂度在 cheap / standard / strong 三档之间挑选。
    # 默认关闭：只在用户给模型标注过 tier 才有意义，否则会挑错
    enable_model_routing: bool = False

    # ---- 自动化任务 -------------------------------------------------------- #
    # 每项都会**真的调用模型**，所以默认空列表 + enabled=False 双层保守。
    # 运行期状态（上次执行时间）不放在这里 —— 它是易失的，
    # 而这份配置要落盘、还会被用户在界面上编辑，混进运行状态会互相干扰。
    scheduled_tasks: list[ScheduledTaskSpec] = Field(default_factory=list)
    # 调度循环的检查间隔（秒）。留出这个开关是因为它决定了"到点"的精度：
    # 60 秒意味着一个 5 分钟间隔的任务最晚可能晚 1 分钟才跑。
    scheduler_tick_seconds: int = Field(60, ge=10, le=600)


class SecuritySettings(BaseModel):
    """安全策略，对应开发文档第 10 章。"""

    allowed_dirs: list[str] = Field(default_factory=list, description="文件读写白名单根目录")
    # 出厂默认是「每次确认」（产品要求：所有搭子出厂即为此）。
    #
    # ⚠️ 这一条**推翻**了 2026-09 那版"出厂自动批准"（当时是为了让新装用户
    # 不被一个个确认框拦住）。现在的取舍是：**宁可多问一次，也不要让它悄悄
    # 动了文件**——用户原话是"所有搭子出厂设置为每次确认"。
    #
    # 这个默认值只在**首次启动生成配置**那一刻起作用：``settings.json`` 里已经
    # 写死旧值的老用户不受影响。用户想放宽随时可以在输入栏那行点「权限确认」改。
    #
    # 注意它只覆盖 confirm（需确认）级：admin（高危）级另有开关，
    # 生产里 ``PermissionGuard`` 的 ``_allow_admin`` 写死 False，前台永远不会
    # 静默执行高危操作（只有定时任务按次放开，见 ``agent/scheduler.py``）。
    confirm_mode: ConfirmMode = "interactive"
    #: ⚠️ **已失效**（产品要求确认弹窗"永不超时挂起"）——
    #: 确认请求现在无限等待，直到用户点「允许 / 拒绝」，或任务被停止/会话关闭/
    #: 进程重启而作废。字段**为兼容老配置保留**（直接删掉会让老 ``settings.json``
    #: 多出一个未知键），但改它不会有任何效果，设置页也不再展示这一项。
    #:
    #: 为什么值得留着记录：超时自动拒绝听着"保险"，实际是**静默毁掉用户的活**——
    #: 他走开两分钟回来，看到的是"操作被拒绝"，还得重做一遍，而屏幕上没有任何
    #: 东西告诉他"是你没及时点"。
    confirm_timeout_seconds: float = Field(
        120.0,
        gt=0,
        le=1800,
        description="[已失效] 人工确认的超时时间；现在无限等待，此项不再生效",
    )
    redact_enabled: bool = True
    audit_retention_days: int = Field(90, ge=1)

    def effective_allowed_dirs(self, fallback: list[str]) -> list[str]:
        return self.allowed_dirs or fallback


class UsageSettings(BaseModel):
    """用量统计与费用提示。"""

    currency: Literal["CNY", "USD"] = "CNY"
    daily_budget: float | None = Field(
        None,
        ge=0,
        description="每日费用软上限。超过后仅在发送前提示，**不阻止发送**；留空表示不提示。",
    )
    retention_days: int = Field(
        365,
        ge=1,
        description="用量流水保留天数。比审计（默认 90 天）长，因为要做月度对比。",
    )


class MemorySettings(BaseModel):
    """长期记忆（向量检索）设置。

    ## 嵌入后端三条路

    ``builtin``（默认）用随包分发的中文模型：装完就能用、不联网、不花配额。
    另外两条是给用户留的自由度 —— 想换更大的模型、或者本地已经跑着 Ollama。
    """

    long_term_enabled: bool = Field(
        True,
        description=(
            "启用长期记忆。默认**开启**：内置中文模型随包分发，不再依赖"
            "首次联网下载，也就没有理由为了让安装包小一点而默认关掉它。"
        ),
    )
    vector_top_k: int = Field(
        5,
        ge=1,
        le=50,
        description=(
            "默认检索条数：每次按语义检索长期记忆时取回几条。"
            "默认 5（产品指定）。"
        ),
    )
    # ⚠️ 这里刻意**不收紧上限**：界面上那个输入框限到 20（防误输入撑爆上下文），
    # 但后端留到 50 —— 老版本没有读这个值的地方，用户手改过配置文件的话
    # 可能存着比 20 大的数；收紧成 le=20 会让那些配置**加载直接失败**
    # （表现为整个客户端起不来），为了一个纯展示上限不值得。

    # ---- 嵌入后端 ------------------------------------------------------ #
    embedding_backend: Literal["builtin", "api", "ollama"] = Field(
        "builtin",
        description=(
            "builtin = 内置中文模型（离线、免费）；api = 自定义厂商接口；"
            "ollama = 本机 Ollama。默认 builtin：普通用户装完就该能用，"
            "不该先去申请一个 Key 才有记忆。"
        ),
    )

    # ---- 自定义厂商接口（backend=api）---------------------------------- #
    embedding_base_url: str = Field("", description="自定义嵌入端点，如 https://xxx/v1")
    embedding_model: str = Field("", description="嵌入模型名")
    embedding_key_model_id: str = Field(
        "",
        description=(
            "复用**已配置模型**的密钥（填该模型的 id）。这是推荐做法："
            "密钥继续走既有的 safeStorage 托管，不在这里再放一份明文。"
        ),
    )
    embedding_api_key: str = Field(
        "",
        description=(
            "直接填写的密钥。**留空表示复用上面那条模型**，所以只有在用户"
            "确实想为一个独立端点单独配 Key 时才填；填了会明文落进 settings.json。"
        ),
    )

    # ---- Ollama（backend=ollama）--------------------------------------- #
    embedding_ollama_url: str = Field(
        "http://127.0.0.1:11434", description="本机 Ollama 地址"
    )
    embedding_ollama_model: str = Field("", description="Ollama 里的嵌入模型名")

    # ---- 旧字段：仅用于升级时推导 backend，别再新增依赖 ----------------- #
    use_api_embedding: bool = Field(False, description="已废弃；升级时用于推导 embedding_backend")
    embedding_model_id: str = Field("", description="已废弃；升级时用于推导 embedding_key_model_id")


class CalendarSettings(BaseModel):
    """日历配置（本地 .ics 与 CalDAV 双后端）。

    ``caldav_password`` **只存在内存里**：它由 Electron 的 safeStorage 加密托管，
    启动时经 ``AGENT_SECRETS_FILE`` 注入，落盘时被 ``strip_secrets`` 清空。
    所以读配置文件永远读不到密码 —— 这是刻意的，和模型 API Key 同一套规则。
    """

    mode: Literal["auto", "local", "caldav"] = Field(
        "auto",
        description=(
            "auto = 配了 CalDAV 就用在线、没配就用本地文件（零基础用户不用配也能用）；"
            "local = 只用本地文件；caldav = 只用在线"
        ),
    )
    caldav_url: str = Field("", description="CalDAV 服务地址，例如 https://caldav.example.com/")
    caldav_username: str = Field("", description="日历账号")
    caldav_password: str = Field("", description="日历密码（仅内存，落盘即清空）")
    default_duration_minutes: int = Field(
        60, ge=5, le=24 * 60, description="新建日程时未给结束时间，默认持续多久"
    )
    calendar_name: str = Field("我的日程", description="本地日历显示名（同时写进导出的 .ics）")


class VoiceSettings(BaseModel):
    """语音对话模式的配置（**全在本机生效**）。

    识别与唤醒都跑在本机模型上（见 ``my_agent/voice/``），没有云端依赖，音频不出
    这台机器。所以这里每一项都是**隐私相关**的设置，改动只影响本机行为。
    """

    #: 唤醒词。说了它才开始录音。
    #:
    #: ⚠️ 不是随便什么词都行：唤醒词会被转成**拼音音素**交给 KWS 模型，音素必须落在
    #: 模型自带的那张表里（227 个）。所以设置页保存前会调
    #: ``/v1/voice/keywords/validate`` 校验、把不可用的词当场拦下 ——
    #: 否则模型会"照收不误但永远不响应"，那是最难查的一类失败。
    wake_words: list[str] = Field(
        default_factory=lambda: ["你好搭子"],
        description="唤醒词（可多个），说了它才开始录音",
    )
    #: 说完之后说这个词才发出去。默认「发送」，但有人习惯说 over / 开始，
    #: 所以做成可配 —— 这是用户在需求里明确要求的。
    send_word: str = Field("发送", description="说这个词才把内容发出去")
    cancel_word: str = Field("取消", description="说这个词放弃刚说的一句")
    #: 语音命令词：``{动作 id: 命令词}``。
    #:
    #: ⚠️ **只存用户改过的那几条**，其余走前端的出厂默认词（见 desktop 的
    #: ``services/voiceCommands.ts``）。这样**加新命令不需要迁移任何配置** ——
    #: 否则每加一个动作都得给所有老用户的 settings.json 补一遍默认值，迟早会漏。
    command_words: dict[str, str] = Field(
        default_factory=dict, description="语音命令词覆盖（动作 id → 命令词）"
    )
    #: 被用户停用的命令 id。有些人对"说一句话就能删文件"天然不安，必须让他能关掉。
    #: 停用的命令**不参与识别**，设置页也不再显示。
    disabled_commands: list[str] = Field(
        default_factory=list, description="已停用的语音命令 id"
    )

    #: 应用启动后的语音状态（产品拍板的三档）：
    #:
    #: - ``off``：不碰麦克风（"应用不在后台等待"）。想用语音得自己去语音设置里改档。
    #: - ``global``（**默认**）：只开**全局监听层** —— 一直在等「开启语音」那个词。
    #:   麦克风常开，但它只在等一个短词、不识别内容。
    #: - ``all``：全局层 + 全体搭子一起待命，启动后**直接**可以喊搭子。
    #:
    #: ⚠️ 默认从 ``off`` 改成 ``global``（产品要求："用户首启应默认为
    #: 说出指令随时开启"）。上一次定的是 ``off``，理由是"麦克风常开会让 Windows 托盘
    #: 一直显示正在使用麦克风，可能成为卸载理由" —— 那个顾虑还在，但**说一句就把语音
    #: 打开**这件事的价值更高：默认关的时候，用户根本不知道有语音这回事。
    #:
    #: 折中在于 ``global`` 这一档本身就很轻：它**不识别内容**，只在比对两个短词，
    #: 用户不说「开启语音」它就什么都不做。真正重的（识别搭子名字）要说了才进。
    startup_mode: Literal["off", "global", "all"] = Field(
        "global", description="启动后：不监听 / 只开全局监听 / 全局+全体搭子待命"
    )

    #: 全局监听层的两个指令词。**这一层优先级最高**：不管用户正在跟哪个搭子说话，
    #: 说「关闭语音」立刻把整个语音功能关掉（回到只等「开启语音」的状态）。
    #:
    #: ⚠️ 默认词组刻意取得长：这一层是常开的，短词（"开"、"停"）会在日常对话里
    #: 被频繁命中 —— 那比唤不醒糟得多，因为它会在用户没要求的时候动东西。
    enable_word: str = Field("开启语音", description="全局：开启语音功能的指令词")
    disable_word: str = Field("关闭语音", description="全局：关闭语音功能的指令词")

    @model_validator(mode="after")
    def _words_must_differ(self) -> VoiceSettings:
        """命令词不能为空、也不能两两撞车。

        最危险的是 ``send_word`` 与某个"批准类"命令词相同 —— 那时用户一句
        "发送"可能被同时理解成"批准删除"。宁可让保存失败并说清原因，
        也不放一组有歧义的配置进去。

        ## ⚠️ 这里曾有 ``confirm_word`` / ``reject_word`` / ``revise_word``

        它们 2026-10-05 被**删除**了。原因是它们从来**没有任何代码读过** ——
        批准高危操作、拒绝、改计划三个动作的实现，一律走命令表
        （``command_words`` + desktop 的 ``services/voiceCommands.ts``），
        词是「允许执行 / 拒绝执行 / 改一下」。

        留着它们的代价是真金白银的：语音设置面板上那三个框**看起来能配**，
        用户在"确认词"里填「确认」、对着弹窗说"确认"毫无反应，而
        **真正要喊的词在另一个区里**（还写着"允许执行"）。配置项骗人比没有更糟。

        删掉之后，老 ``settings.json`` 里残留的这三个键会被 pydantic **直接忽略**
        （本模型没有对应字段），所以不需要任何迁移。
        """
        labels = {
            "发送词": self.send_word,
            "取消词": self.cancel_word,
            # 全局层的两个指令也要参与查重：它们优先级最高，撞上别的词会出现
            # "我喊关闭语音，结果它把话发出去了"这种解释不清的行为。
            "开启语音指令": self.enable_word,
            "关闭语音指令": self.disable_word,
        }
        seen: dict[str, str] = {}
        for label, word in labels.items():
            text = (word or "").strip()
            if not text:
                raise ValueError(f"{label}不能为空")
            if text in seen:
                raise ValueError(f"{label}与{seen[text]}不能是同一个词：{text}")
            seen[text] = label

        # 命令词也不能跟上面几个撞：撞了就是歧义 —— 说「发送」时到底是把话发出去，
        # 还是执行某个界面动作？两边都不该猜。
        for action, word in (self.command_words or {}).items():
            text = (word or "").strip()
            if text and text in seen:
                raise ValueError(f"命令「{action}」的命令词「{text}」与{seen[text]}重复，换一个")
        return self


class AppSettings(BaseModel):
    """settings.json 的结构。"""

    app_name: str = "Soulmate Agent"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    trace_enabled: bool = True
    # 皮肤 id。必须与前端 ``AppSettings.theme`` 保持一致 —— 设置是**整份提交**的，
    # 枚举对不上会让保存直接失败（而且报错发生在校验层，界面上只看到"保存失败"）。
    # 皮肤 id。必须与前端 ``AppSettings.theme`` 保持一致 —— 设置是**整份提交**的，
    # 枚举对不上会让保存直接失败（而且报错发生在校验层，界面上只看到"保存失败"）。
    # 默认樱粉（sakura）是产品明确要求的出厂主题；已保存过设置的老用户不受影响。
    theme: Literal[
        "light",
        "dark",
        "system",
        "warm",
        "forest",
        "ocean",
        "sakura",
        "mint",
        "sky",
        "apricot",
        "plum",
        "pine",
        "charcoal",
        "deepday",
        "deepnight",
    ] = "sakura"
    language: str = "zh-CN"

    # 这里曾有 ``assistant_market_source``（助手集市的索引地址）。产品要求把
    # 「搭子集市」整体剔除，字段随之删除。老配置的 settings.json 里可能还留着
    # 这个键：``AppSettings`` 没有开 ``extra="forbid"``，pydantic 默认忽略多余
    # 字段，所以旧文件照常能读，下次保存时这个键自然消失。

    agent: AgentSettings = Field(default_factory=AgentSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    usage: UsageSettings = Field(default_factory=UsageSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    calendar: CalendarSettings = Field(default_factory=CalendarSettings)


# --------------------------------------------------------------------------- #
# MCP（Model Context Protocol）服务配置
# --------------------------------------------------------------------------- #
class McpServerConfig(BaseModel):
    """一个 MCP Server 的启动配置。

    对应开发文档 6.2 节的 ``McpClient`` 构造参数，并补充了图形化设置中心
    需要的字段（启用开关、超时、单工具权限覆盖）。
    """

    name: str = Field(..., min_length=1, max_length=64, description="服务标识，同时作为工具名前缀")

    # ---- 传输方式 -------------------------------------------------------- #
    # stdio 是本机子进程（npx / uvx / python）；后两种连远程 Server。
    # 三种共用同一套连接生命周期与重连策略，只有"怎么建连"不同。
    transport: Literal["stdio", "sse", "streamable_http"] = "stdio"
    # 远程端点的 URL（transport 非 stdio 时必填）
    url: str = Field("", description="远程 MCP 端点地址")
    # 远程端点需要的自定义头（通常是 Authorization）。
    # 注意：这里会随配置落盘，密钥类字段请在设置界面用环境变量方式提供
    headers: dict[str, str] = Field(default_factory=dict)

    command: str = Field("", description="可执行文件，如 npx / uvx / python（仅 stdio）")
    args: list[str] = Field(default_factory=list, description="启动参数")
    env: dict[str, str] = Field(default_factory=dict, description="附加环境变量")
    cwd: str | None = Field(None, description="工作目录；留空则继承客户端进程")

    enabled: bool = True
    auto_start: bool = Field(True, description="客户端启动时是否自动连接")
    description: str = ""
    timeout: float = Field(60.0, gt=0, le=600, description="单次工具调用的超时时间")
    # 覆盖某个工具的权限级别：{"write_file": "admin"}
    permission_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_transport_fields(self) -> McpServerConfig:
        """按传输方式校验必填项。

        ``command`` 从必填改成可选是必须的 —— 远程 Server 根本没有本地命令。
        但"可选"不等于"可以不填"：stdio 缺 command 会在建连时才炸，
        那时用户看到的是一个 npx 的报错，猜不到是自己没填命令。
        """
        if self.transport == "stdio":
            if not self.command.strip():
                raise ValueError("stdio 传输必须填写启动命令（command）")
        elif not self.url.strip():
            raise ValueError(f"{self.transport} 传输必须填写端点地址（url）")
        return self

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """服务名会拼进工具名，必须限制字符集，否则工具名会被模型网关拒绝。"""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("服务名不能为空")
        if not all(ch.isalnum() or ch in "_-" for ch in cleaned):
            raise ValueError("服务名只能包含字母、数字、下划线和短横线")
        return cleaned

    @field_validator("env")
    @classmethod
    def _stringify_env(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(k): str(v) for k, v in (value or {}).items()}


class CustomSkillParam(BaseModel):
    """自定义技能的一个参数。界面上按这个生成输入项，同时转成工具 Schema 给模型。"""

    name: str = Field(..., min_length=1, max_length=40)
    description: str = ""
    required: bool = True
    default: str | None = None
    type: Literal["string", "number", "boolean"] = "string"

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("参数名不能为空")
        # 参数名要同时能进 JSON Schema、进模板占位符（{name}），所以限定字符集
        if not all(ch.isalnum() or ch == "_" for ch in cleaned):
            raise ValueError("参数名只能包含字母、数字和下划线")
        return cleaned


class CustomSkillDef(BaseModel):
    """用户自定义技能（声明式）。

    ## 为什么是"声明式"而不是让用户写 Python

    1. **打包后装不了新依赖**：核心是 PyInstaller 打的包，运行时没有编译环境。
    2. **安全**：让用户写代码等于把"任意代码执行"交出去；声明式只有两种动作
       （发一个 HTTP 请求 / 跑一条命令），风险面清楚得多。

    占位符用 ``{参数名}``，请求/命令发出去之前会先做参数替换。
    """

    id: str = Field(..., min_length=1, max_length=64, description="工具名（会原样进工具 Schema）")
    name: str = Field(..., min_length=1, max_length=48, description="界面上的显示名")
    description: str = Field("", max_length=600, description="模型决定要不要调用的唯一依据，写清楚什么时候用")
    params: list[CustomSkillParam] = Field(default_factory=list)

    # instruction：**纯指导型**技能 —— 不执行任何动作，`instructions` 的内容
    # 会在对话时拼进 system（见 agent/scheduler.py / routes/chat.py 的
    # persona 组装处）。上传的技能包里只有 SKILL.md 时就是这种。
    kind: Literal["http", "command", "instruction"] = "http"

    # ---- instruction ----
    instructions: str = Field("", description="指导内容原文（来自 SKILL.md），会注入 system")

    # ---- http ----
    url: str = Field("", description="请求地址，可含 {参数名} 占位符")
    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, description="请求头，值可含 {参数名}")
    body_template: str = Field("", description="请求体模板，可含 {参数名}；GET/DELETE 通常留空")

    # ---- command ----
    command_template: str = Field("", description="要执行的命令，可含 {参数名}，例如 ping {host}")

    timeout: float = Field(30.0, gt=0, le=120)
    permission_level: Literal["safe", "confirm", "admin"] = "confirm"
    enabled: bool = True

    # ---- 技能包来源（导入时写入；手动填写的技能与老数据一律留空）----
    #
    # ⚠️ 这几个字段**全部可缺省**：老机器上的 ``custom_skills.json`` 没有这些键，
    # 反序列化后就是默认值，**不需要任何迁移**。所以以后往这里加字段也必须给默认值。
    #
    # ⚠️ 这一条尤其要紧：``load_custom_skills()`` 解析失败时会**返回空配置**
    # （见 `config/loader.py`），也就是说 —— 加一个**没有默认值**的字段，
    # 老配置会当场校验失败，用户那几百个技能会**静默全消失**。
    origin: Literal["user", "factory"] = Field(
        "user",
        description=(
            "技能从哪来。user = 用户自己导入 / AI 创建 / 手动建；"
            "factory = 随客户端分发的出厂技能（见 resources/factory_skills）。"
            "⚠️ 只用来区分来源，不参与分类判定（那是 skill/groups.py 的事）"
        ),
    )
    source_format: str = Field(
        "",
        description=(
            "来源格式（界面按它显示徽标）：claude-skill / skill-json / cursor-mdc / "
            "clinerules / agents-md / plain-md / mcp-json / script / folder / manual"
        ),
    )
    package_root: str = Field(
        "",
        description="该技能在技能包内的子目录（空 = 包根）。落盘时**只落这棵子树**，"
        "多技能包才不会互相覆盖",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="SKILL.md frontmatter 里的 allowed-tools（原样保留，仅作提示展示）",
    )
    scripts: list[str] = Field(
        default_factory=list, description="随包提供的可执行脚本（包内相对路径）"
    )
    pack_files: list[str] = Field(
        default_factory=list,
        description="该技能在包内**占用哪几个文件**（空 = 由 package_root 决定整棵子树）。"
        "落盘范围靠它区分：规则文件与脚本只落自己那一份，指导型技能落整棵子树",
    )
    note: str = Field(
        "",
        description="导入时产生的提示（例如解释器未找到、功能受限、字段被截断）。"
        "**界面必须如实展示** —— 静默降级是这个项目最不能接受的失败方式",
    )
    domain: str = Field(
        "",
        description=(
            "技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）："
            "电商 / 金融 / 营销 / 教育 / 医疗 / 科技 / 学术 / 设计 / 法律 / 人力 / "
            "办公 / 生活 / 媒体 / 系统。空 = 没归类（界面归到「其它」）。"
            "⚠️ 与 `category` 是两个维度：那个说'这技能干什么'，这个说'属于哪个领域'。"
        ),
    )

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not all(ch.isalnum() or ch in "_-" for ch in cleaned):
            raise ValueError("技能 id 只能包含字母、数字、下划线和短横线")
        return cleaned

    def to_tool_schema(self) -> dict[str, Any]:
        """转成工具 Schema（与 ``SkillMeta.parameters`` 同形）。"""
        properties: dict[str, Any] = {}
        for param in self.params:
            item: dict[str, Any] = {"type": param.type, "description": param.description}
            if param.default is not None:
                item["default"] = param.default
            properties[param.name] = item
        return {
            "type": "object",
            "properties": properties,
            "required": [p.name for p in self.params if p.required],
        }

    def render(self, values: dict[str, Any], template: str) -> str:
        """把 ``{参数名}`` 替换成实际值。

        **用占位符而不是 f-string / format**：``format`` 会把 ``{}`` 当表达式解析，
        模板里出现花括号（比如 JSON）就会炸。这里只做最朴素的字符串替换。
        """
        result = template
        for param in self.params:
            value = values.get(param.name)
            if value is None:
                value = param.default if param.default is not None else ""
            result = result.replace("{" + param.name + "}", str(value))
        return result

    @staticmethod
    def _split_command_template(template: str) -> list[str]:
        """把命令模板切成 argv token（Windows 友好、**不做任何转义处理**）。

        规则（有意保持极简，且**不是** shell 语义）：
        * 空白分隔 token；
        * 被 ``"`` 或 ``'`` 包住的片段算**同一个** token，引号本身去掉
          （这样 ``"C:\\Program Files\\a.exe"`` 才不会被切成两段）；
        * **不处理转义**：Windows 路径里的 ``\\`` 原样保留 ——
          用 ``shlex`` 会把它当转义符吃掉，``C:\\Program Files`` 会被切坏；
        * 引号不配对时按普通字符处理（宁可把原样的内容传下去让程序自己报错，
          也不要在这里抛异常把整条技能打成"配置错误"）。

        ⚠️ 这里**不实现**管道 ``|``、重定向 ``>``、``&&`` 这些 shell 语法：
        命令已经改为不经 shell 执行（见 ``skill/custom.py::_run_command``），
        它们本来就不再具有 shell 的含义。
        """
        tokens: list[str] = []
        current: list[str] = []
        quote: str | None = None
        started = False
        for char in template:
            if quote is not None:
                if char == quote:
                    quote = None
                else:
                    current.append(char)
                continue
            if char in ("'", '"'):
                quote = char
                started = True
                continue
            if char.isspace():
                if started or current:
                    tokens.append("".join(current))
                    current = []
                    started = False
                continue
            current.append(char)
            started = True
        if started or current:
            tokens.append("".join(current))
        return tokens

    def render_argv(self, values: dict[str, Any], template: str) -> list[str]:
        """把命令模板渲染成 **argv 数组**（占位值各自独立成一个参数）。

        ⚠️ **这是命令注入的根治做法**。占位符的值来自**模型**（技能是模型按用户
        要求"造"出来的，参数由模型填），如果把值直接拼进一条 shell 命令，值里的
        ``&`` / ``|`` / ``>`` 就是 shell 语法 —— ``{host}`` 被填成
        ``x & del /f /q ...`` 就会真的执行。这里的做法是**先切 token、再逐个 token
        替换占位符**，值里有什么都不会改变参数结构；执行侧再走
        ``create_subprocess_exec``（不经过 shell）—— 两条一起做才成立。

        ⚠️ **口径变化（2026-10-09，第 84 批）**：模板里写 shell 语法的技能
        （管道 ``|``、重定向 ``>``、``&&``、``%VAR%`` 等）**不再有 shell 的含义**，
        它们会被当成普通参数原样传给被调用的程序。这是"不再经过 shell"的必然代价，
        已在文档里如实告知。
        """
        return [self.render(values, token) for token in self._split_command_template(template)]


class CustomSkillsConfig(BaseModel):
    """custom_skills.json 的结构。"""

    skills: list[CustomSkillDef] = Field(default_factory=list)

    def get(self, skill_id: str) -> CustomSkillDef | None:
        return next((item for item in self.skills if item.id == skill_id), None)

    def upsert(self, skill: CustomSkillDef) -> None:
        for index, item in enumerate(self.skills):
            if item.id == skill.id:
                self.skills[index] = skill
                return
        self.skills.append(skill)

    def remove(self, skill_id: str) -> bool:
        before = len(self.skills)
        self.skills = [item for item in self.skills if item.id != skill_id]
        return len(self.skills) != before


class McpConfig(BaseModel):
    """mcp.json 的结构。"""

    servers: list[McpServerConfig] = Field(default_factory=list)

    def get(self, name: str) -> McpServerConfig | None:
        return next((item for item in self.servers if item.name == name), None)

    def upsert(self, server: McpServerConfig) -> None:
        for index, item in enumerate(self.servers):
            if item.name == server.name:
                self.servers[index] = server
                return
        self.servers.append(server)

    def remove(self, name: str) -> bool:
        before = len(self.servers)
        self.servers = [item for item in self.servers if item.name != name]
        return len(self.servers) != before


def default_wake_words(name: str) -> list[str]:
    """按搭子名字生成出厂唤醒词：「你好」+ 名字。

    ## 为什么不是"直接用名字"

    唤醒词是**用户叫它**时说的，而名字会出现在对话正文里（"让小助帮我查一下"）。
    直接用名字的话，用户每提一次搭子名就会把它唤起来 —— 那是灾难性的误触发。
    「你好 X」这个形式的误触发概率低得多，也更符合中文里"喊人"的语感。

    ## 为什么要带前缀，而不是让用户自己填

    新建搭子就该**马上能喊**，不该先逼用户去想一个"识别得准的词"。
    不满意随时改（搭子的语音设置里能改，跟别的搭子撞车了保存时会拦住）。
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return ["你好搭子"]
    return [f"你好{cleaned}"]


class AssistantProfile(BaseModel):
    """一个助手 = 一份 Agent 配置预设（对齐 Cherry Studio 的"助手"概念）。

    把「人设 + 模型 + 可用工具 + 权限策略」打包成一个可切换的整体：
    用户不用每次对话都重新调参数，也让模型少看到一堆用不上的工具
    """
    """一个助手 = 一份 Agent 配置预设（对齐 Cherry Studio 的"助手"概念）。

    把「人设 + 模型 + 可用工具 + 权限策略」打包成一个可切换的整体：
    用户不用每次对话都重新调参数，也让模型少看到一堆用不上的工具
    （工具越多，模型选错的概率越高）。
    """

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    # 对话里显示的昵称（产品明确要求与 id、name 区分）：留空则回退用 name。
    # id 是内部标识不能改，name 是管理用的显示名，昵称才是"它在对话里叫什么"。
    nickname: str = Field("", max_length=48)
    emoji: str = "🤖"
    description: str = ""
    system_prompt: str = ""

    model_id: str = Field("", description="留空表示跟随全局默认模型")
    temperature: float | None = Field(None, ge=0, le=2)
    # 不设上限（产品明确要求）：上一版 le=50 会让"长任务跑不完"。
    # None = 跟随全局 AgentSettings.max_iterations（那边有自己的防死循环上限）。
    max_iterations: int | None = Field(None, ge=1)
    # 工具调用次数上限，None = 跟随全局（产品要求助手可单独设置）
    max_tool_calls_per_turn: int | None = Field(None, ge=1)
    # 思考强度："low" / "medium" / "high"。``None`` = 跟随全局设置（等于不发送该参数）。
    #
    # 产品要求群聊里"跟随每个搭子自己的设置"，所以这个档位挂在**搭子**上。
    # 单人对话仍以会话级档位优先（用户对"这一轮值不值得多想"的判断是按对话来的）。
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        None, description="思考强度；留空跟随全局"
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _normalize_reasoning_effort(cls, value: Any) -> Any:
        """先归一（空串 / 非法值），再交给 `Literal` 校验。

        两件事都在这里做，缺一个都会出问题：

        1. **空串 = 「跟随全局」**。前端下拉里"不发送（服务商默认）"那一项的值就是空串
           （与 `ChatRequest`、`routes/groups.py::GroupUpdate` 同一口径）。
           ⚠️ 少了这一步，收紧成 `Literal` 之后**保存搭子设置会直接 422** ——
           那是"修静默失效"顺手改出的新故障。`' high '` 这种带空白也一并收拢成 `'high'`。
        2. **非法值归一成 `None` 并告警**，而不是像那两处一样严格拒绝：
           那两个模型是**纯请求体**，而这个是**落盘结构**
           （`assistants.json` 的每个搭子、搭子包/群包导入都从这里过）——
           严格拒绝的话，用户配置里早就存着的一个拼错值会让整份配置**校验失败**，
           等于"为了修一个静默失效把应用弄成打不开"。
           归一化之后旧值照样能起来，而**下一次**写回去的就是干净值。
        """
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned in ("low", "medium", "high"):
            return cleaned
        logger.warning(
            "搭子的思考强度「%s」不是 low/medium/high，已按「跟随全局」处理", value
        )
        return None

    # 这个搭子**额外勾选**的技能（只会是「通用技能」与「我的技能」两类）。
    #
    # ⚠️ 口径 **反转过**：以前"空列表 = 不限制（开放全部已启用技能）"，
    # 现在是"**一个都没勾**" —— 为空时这个搭子只有「内置技能」（外加自己的专属技能）。
    # 用户原话："以后没有默认加载全部技能的搭子了"、"如果没有选择只默认加载内置技能"。
    # 实际可用集合由 `SkillManager.allowed_names` 展开（见 `skill/groups.py`）——
    # **不要**在任何地方再按"空 = 全开"去解释它。
    # 内置搭子的这个字段同时被 `assistants/locked_builtins.py` 锁住：不可改，且装配时被忽略。
    enabled_skills: list[str] = Field(default_factory=list)

    # 群聊里的团队角色（产品要求「总管 + 各专职 + 审核员」的团队分工）：
    #
    # - ``coordinator``：协调者（总管）—— 开场做策划与分工、汇总结论；
    # - ``worker``：执行者 —— 只做分给自己的那部分；
    # - ``advisor``：优化顾问 —— 交付后只提**必要**的建设性建议（倒数第二序）；
    # - ``reviewer``：审核员 —— 按判据验收交付物并**把关优化顾问的建议**，不达标打回给总管；
    # - 空串：未指定 —— 讨论时按**发言位次**兜底（首位当总管、倒数第二当优化顾问、
    #   末位当审核员），这样老群（成员没有角色）与用户手建的群也能直接按分工跑起来。
    #
    # ⚠️ 默认空串是为了**非破坏**：老的 ``assistants.json`` 里没有这个字段，
    # 加载时自动取默认值，不会报错也不需要迁移。
    group_role: Literal["", "coordinator", "worker", "reviewer", "advisor"] = Field(
        "", description="群聊角色：协调者 / 执行者 / 优化顾问 / 审核员；留空 = 按发言位次兜底"
    )
    confirm_mode: ConfirmMode | None = Field(
        None, description="该助手专属的权限策略；留空表示沿用全局设置"
    )

    # ---- 语音 ------------------------------------------------------------ #
    #: 这个搭子**自己的一套**语音设置（产品要求："每个搭子都是一套
    #: 独立的语音控制设置"）。
    #:
    #: 为什么唤醒词要挂在搭子上：它天然就是"这个搭子叫什么"—— 喊「你好小助」就该
    #: 小助应答。新建搭子时按名字自动生成（见 ``default_wake_words``），
    #: 所以多数用户零配置就能用。
    #:
    #: ⚠️ 全局的 ``AppSettings.voice`` 仍然保留，但角色变了：它是**新建搭子的模板**
    #: （复制一份当起点）。老配置因此不需要任何迁移 —— 搭子身上没有这个键时
    #: pydantic 自动取默认值。
    voice: VoiceSettings = Field(default_factory=VoiceSettings)

    # ---- 头像 ------------------------------------------------------------ #
    # 用户上传的图片（data URL）。留空表示继续用 emoji。
    #
    # **为什么是 data URL 而不是文件路径**：渲染层走 ``file://`` 加载页面，
    # 本地图片路径在 CSP 下能不能用属于实现细节（``img-src 'self'`` 对 file://
    # 的行为并不统一），而 ``data:`` 是明确允许的。代价是它会进 assistants.json，
    # 所以上传处**必须先压到很小**（见前端的 AVATAR_MAX_SIZE）。
    avatar: str = ""

    # 聊天背景（data URL，压缩后入库）。只作用于**这个助手**的对话区；
    # 空 = 跟随全局壁纸。与头像同理必须先压小，否则 assistants.json 膨胀。
    chat_background: str = ""

    # ---- 人格锁 ---------------------------------------------------------- #
    # 只保护"人格"那部分（系统提示词 + SOUL.md），**不拦**模型、工具这类普通设置 ——
    # 这是用户明确要的粒度：他怕的是手滑把人设改坏，不是怕别人翻他电脑。
    #
    # 存**哈希 + 盐**而不是明文，用标准库 ``hashlib.pbkdf2_hmac``，不引入新依赖。
    #
    # ⚠️ 定位要说清楚：**防手滑，不防人**。本机单人应用，真要防别人得靠系统账户。
    # 所以设置里必须有重置入口（见 routes/assistants.py 的 reset），
    # 否则用户把自己锁在外面，这个功能就变成了数据丢失。
    persona_password_hash: str = ""
    persona_password_salt: str = ""

    @model_validator(mode="after")
    def _seed_wake_words(self) -> AssistantProfile:
        """没配过唤醒词时，按名字自动生成一个。

        ## 为什么放在 model 层，而不是"新建搭子"那段业务代码里

        放业务代码里的话，**只有新建的搭子**才有独立唤醒词，而**已存在的**搭子
        （四个内置的、用户之前建的）会全部停在出厂默认的「你好搭子」上 ——
        它们互相撞车，而且保存任何一个都会因为"唤醒词和别的搭子重复"被 409 拦住。

        挂在 model 上就顺带解决了：每次从 ``assistants.json`` 读出来都走一遍 ——
        已经配过的不动，还是出厂默认的就按名字补上。于是：
          · 老用户升级后，每个搭子立刻有了各自的唤醒词；
          · 新建搭子零配置就能喊；
          · **不需要任何一次性迁移脚本**（那种脚本迟早会被漏在某条启动路径上，
            而漏掉的表现正好就是"喊谁都醒不了"）。
        """
        current = list(self.voice.wake_words or [])
        if current == VoiceSettings().wake_words:
            self.voice.wake_words = default_wake_words(self.name)
        return self

    builtin: bool = Field(
        False,
        description=(
            "内置预设（出厂自带）。⚠️ 四个在册内置搭子（见 ``locked_builtins``）"
            "不可改、不可删；这个标志本身只表示来路，老版本留下的内置记录也是 True"
        ),
    )
    sort_order: int = 100

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not all(ch.isalnum() or ch in "_-" for ch in cleaned):
            raise ValueError("助手 id 只能包含字母、数字、下划线和短横线")
        return cleaned

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        # 这个搭子有没有**额外勾选**技能。
        #
        # ⚠️ 语义 变了：以前它表示"是否限制了技能范围"（False = 全开），
        # 现在"全开"这种搭子已经不存在了 —— 它只说明"用户额外勾了几个通用/我的技能"。
        # 刻意**不改名**：这个名字已被前端与多处测试引用，改名要动一大片而收益为零，
        # 用这条注释把口径钉住即可。
        data["restricts_skills"] = bool(self.enabled_skills)
        # 哈希与盐**绝不**下发给界面：它们唯一的作用是在服务端比对，
        # 发出去等于把口令材料交给渲染层 —— 而渲染层正是要渲染模型输出、
        # 最不该持有凭据的那一侧。界面只需要知道"有没有上锁"。
        data.pop("persona_password_hash", None)
        data.pop("persona_password_salt", None)
        data["persona_locked"] = bool(self.persona_password_hash)
        return data

    # ------------------------------------------------------------------ #
    # 人格锁
    # ------------------------------------------------------------------ #
    def set_persona_password(self, password: str) -> None:
        """设置（或清空）人格密码。传空串表示解锁。"""
        if not password:
            self.persona_password_hash = ""
            self.persona_password_salt = ""
            return
        import hashlib
        import os

        self.persona_password_salt = os.urandom(16).hex()
        self.persona_password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(self.persona_password_salt), 120_000
        ).hex()

    def verify_persona_password(self, password: str) -> bool:
        """比对密码。**没上锁时永远返回 True**（没有锁就等于没拦）。"""
        if not self.persona_password_hash:
            return True
        if not password:
            return False
        import hashlib
        import hmac

        expected = self.persona_password_hash
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(self.persona_password_salt), 120_000
        ).hex()
        # 定长比较：普通 == 会因提前返回而泄露比较进度（时序侧信道）
        return hmac.compare_digest(expected, actual)


class AssistantsConfig(BaseModel):
    """assistants.json 的结构。"""

    assistants: list[AssistantProfile] = Field(default_factory=list)
    default_assistant: str = ""

    def get(self, assistant_id: str) -> AssistantProfile | None:
        """按 id 取搭子；查不到时**兜底认旧 id**。

        ⚠️ 为什么要兜底：内置搭子在 2026-09-26 改过 id（``office → RelationBuddy``、
        ``lovebuddy → LoveBuddy``），而 ``audit_log`` 这类**历史记录**里存的仍是旧 id
        —— 那些记录我们刻意**不改写**（它们记的是"当时确实发生了这件事"，改掉就等于
        篡改凭证）。于是把旧 id 在这里认成新 id，历史记录里才显示得出搭子名，
        而不是一串 ``office``。

        只在**新 id 确实存在**时才认：若用户自己建过一个 id 恰好等于旧内置 id 的搭子，
        上面的第一次查找就已经命中它，行为与以前完全一致。
        """
        found = next((item for item in self.assistants if item.id == assistant_id), None)
        if found is not None:
            return found
        # 延迟导入：presets 依赖本模块，模块级导入会成环
        from ..assistants.presets import RENAMED_BUILTIN_IDS

        new_id = RENAMED_BUILTIN_IDS.get(assistant_id)
        if not new_id:
            return None
        return next((item for item in self.assistants if item.id == new_id), None)

    def upsert(self, profile: AssistantProfile) -> None:
        for index, item in enumerate(self.assistants):
            if item.id == profile.id:
                self.assistants[index] = profile
                return
        self.assistants.append(profile)

    def remove(self, assistant_id: str) -> bool:
        before = len(self.assistants)
        self.assistants = [item for item in self.assistants if item.id != assistant_id]
        return len(self.assistants) != before

    def sorted(self) -> list[AssistantProfile]:
        return sorted(self.assistants, key=lambda item: (item.sort_order, item.name))


class GroupProfile(BaseModel):
    """一个「AI 群」：把多个搭子拉进同一个群，轮流接话（多智能体协作）。

    群历史是**运行时内存态**（第一版不落盘，重启后群还在、聊天记录清空）；
    群定义（哪些搭子）持久化到 ``groups.json``。
    """

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    # 群成员（搭子 id，按加入顺序轮流发言）
    member_assistant_ids: list[str] = Field(default_factory=list)
    # 发言顺序（产品要求：可设置）。留空则用 member_assistant_ids 的顺序。
    # 只包含成员 id 的子集时，先按它排、其余成员按原顺序跟在后面。
    speaking_order: list[str] = Field(default_factory=list)

    #: 群头像。**data URL**，与 `AssistantProfile.avatar` 同一种
    #: 存法（同一个 `storage/images.py` 负责校验与编码）。
    #:
    #: ⚠️ 空串是**正常状态**，不是"没设置好"：群头像库在前端（随包的 24 张图，
    #: 见 `desktop/src/services/avatarPack.ts`），后端看不到那些 URL。所以
    #: **"从来没设过的群"一律是空串**，由前端在渲染时按"优先不与现有群重复"的
    #: 规则补一张并写回来 —— 与搭子的默认头像完全同一套做法
    #: （`assignMissingAvatars`）。后端这边不需要、也不该知道有哪几张可选。
    avatar: str = Field("", description="群头像（data URL）；留空由前端按规则补一张")

    # ---- 群级策略（留空 = 各成员按自己档案里的设置，也就是老行为）-------- #
    #
    # 权限策略：界面上是一个「群里一律批准」开关（打开写 auto_approve）。
    # ⚠️ 它只对 **confirm 级**生效：admin（高危）级仍然必须人工确认，
    # 群里的开关绝不能变成"高危操作的后门"（见 security/permission.py 的 check）。
    confirm_mode: ConfirmMode | None = Field(
        None, description="该群专属的权限策略；留空沿用各成员自己的设置"
    )
    # 思考强度：产品要求"群聊里也要能调，并且按这个群覆盖成员各自的设置"。
    # 优先级：群 > 成员 > 不发送该参数。
    #
    # ⚠️ 出厂值是 **`medium`**，不是 `None`（"每次创建的新群与
    # 新对话，思考强度默认为中"）。
    #
    # 为什么值得改掉原来的 `None`：`None` 的语义是"跟随每个成员自己的设置"，
    # 而群里的成员常常各有各的档位（甚至有的没设）—— 于是新群第一次讨论，
    # 用户根本预料不到它会想多久，而"思考强度"恰恰是他为了**这一次讨论**
    # 才去调的东西。给一个明确的中间档，他至少知道起点在哪，再往两边调。
    #
    # `None` 仍然**合法**：界面上选"跟随每个搭子"就是它，那是用户明确的选择。
    # 已有群（配置里存着 null 的）保持不变 —— 只对新群生效。
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        "medium", description="该群的思考强度；默认「中」，可清回跟随成员各自的设置"
    )

    # ---- 群角色确认（AI 不能跳过审核员 / 优化顾问）-------- #
    #
    # 这两个角色是**流程上绕不过去的一步**：AI 建群之后必须调 team_assign_group_roles
    # 把它们对应的搭子 id 交上来，系统记在这里；没记下来，AI 发起的讨论会被闸门拦住
    # （见 ``Orchestrator.start_discussion``）。
    #
    # 为什么不用一个布尔开关："本次需不需要审核员"那种判定，模型一步就能带过
    # （截图里就是一句 require_reviewer=false）。改成"必须交出谁的 id"之后，
    # 它要么给出一个真实的搭子、要么被拒绝 —— 没有第三种走法。
    #
    # 默认空串 → 老 groups.json 反序列化后天然是"未确认"，无需迁移。
    reviewer_id: str = Field("", description="该群已确认的审核员搭子 id；空 = 还没提交")
    advisor_id: str = Field("", description="该群已确认的优化顾问搭子 id；空 = 还没提交")

    # ---- 群总管（建群必须把总管指名道姓交出来）---------- #
    #
    # 在这之前，谁当总管是**按发言位次兜底**算出来的（首位），而模型嘴上又爱自称
    # "我是这个群的总管" —— 于是出现"自称总管却不把自己拉进群"的错位：群里真正
    # 的总管是首发那位搭子，模型却按自己的身份在指挥，用户看到的分工是假的。
    # 所以建群时总管必须**由调用方显式交出 id**，并且必须在成员里（见
    # ``Orchestrator.create_group``）；空串只留给"用户手建的群 / 导入的群包"
    # 这类没有模型在场的路径，那时才回到位次兜底。
    coordinator_id: str = Field("", description="该群已指名的总管搭子 id；空 = 走位次兜底")

    def roles_ready(self) -> bool:
        """两个角色是否都已提交（闸门与返回体共用同一判据）。

        这里只看"有没有提交"，"提交的人还在不在群里 / 搭子还在不在"由
        ``Orchestrator`` 侧核对（它才拿得到搭子配置）。
        """
        return bool(self.reviewer_id.strip()) and bool(self.advisor_id.strip())

    # ---- 语音唤醒（也要能"喊"进一个群）------------------- #
    #
    #: 说了它就把界面切到这个群（与鼠标点群列表项**完全同一条路**，
    #: 见 ``Orchestrator``/前端的 ``switchGroup``）。
    #:
    #: 与 ``AssistantProfile.voice.wake_words`` 是**同一套机制** —— 同一个本地 KWS
    #: 模型、同样的拼音匹配、同样要过 ``/v1/voice/keywords/validate`` 的校验 ——
    #: 只是归属不同：那边是"喊谁醒谁"，这边是"喊哪个群进哪个群"。
    #:
    #: ⚠️ 出厂值是 ``["你好群聊"]`` 这个**哨兵值**，而不是空列表，也不是群名：
    #:
    #:   · **不能直接用群名** —— ``name`` 是这个 model 上更靠后的字段，声明顺序上
    #:     拿不到（pydantic 的 ``default_factory`` 在字段定义时求值）。
    #:   · **不能用空列表** —— 那样就分不清"从来没配过"和"用户明确清空了"。
    #:     下面 ``_seed_wake_words`` 判的是"等于出厂哨兵值才补"，空列表因此能
    #:     被表示成用户的明确意图（"这个群我不想用语音喊"）。
    wake_words: list[str] = Field(
        default_factory=lambda: ["你好群聊"],
        description="语音唤醒词（可多个）；说了它切到这个群",
    )

    @model_validator(mode="after")
    def _seed_wake_words(self) -> GroupProfile:
        """没配过唤醒词时，按群名自动生成一个（「你好」+ 群名）。

        ## 为什么挂在 model 层，而不是建群那段业务代码里

        与 ``AssistantProfile._seed_wake_words`` 同一个理由，而且对群更要紧：
        放业务代码里的话，**只有新建的群**才有唤醒词，而**已经存在的**群
        （用户之前手建的、AI 用建群技能建的、从群包导入的）会永远停在哨兵值上 ——
        而哨兵值是"你好群聊"，于是**所有老群共用同一个唤醒词**，喊一句会随机
        落进其中一个。那种失败（"喊了没反应"或"进错了群"）用户根本无从排查。

        挂在这里：每次从 ``groups.json`` 读出来都走一遍，已经配过的不动、
        还是哨兵值的按群名补上。于是：
          · 老用户升级后，每个群立刻有了各自的唤醒词；
          · 新建群零配置就能喊；
          · **不需要任何一次性迁移脚本**（那种脚本迟早会被漏在某条启动路径上，
            而漏掉的表现正好就是"喊谁都醒不了"）。

        ## 为什么是「你好 X」而不是裸群名

        与 ``default_wake_words`` 完全一致：群名会出现在讨论正文里
        （"让「学习计划讨论组」再想想"），裸名字会让用户每提一次群名就切一次页面。
        """
        current = [word for word in (self.wake_words or []) if word.strip()]
        if current == ["你好群聊"]:
            self.wake_words = default_wake_words(self.name)
        return self

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not all(ch.isalnum() or ch in "_-" for ch in cleaned):
            raise ValueError("群 id 只能包含字母、数字、下划线和短横线")
        return cleaned


class GroupsConfig(BaseModel):
    """groups.json 的结构。"""

    groups: list[GroupProfile] = Field(default_factory=list)

    def get(self, group_id: str) -> GroupProfile | None:
        return next((item for item in self.groups if item.id == group_id), None)

    def upsert(self, profile: GroupProfile) -> None:
        for index, item in enumerate(self.groups):
            if item.id == profile.id:
                self.groups[index] = profile
                return
        self.groups.append(profile)

    def remove(self, group_id: str) -> bool:
        before = len(self.groups)
        self.groups = [item for item in self.groups if item.id != group_id]
        return len(self.groups) != before


class AppConfig(BaseModel):
    """聚合后的运行时配置。

    定义在文件末尾：``mcp`` 字段引用了上面才定义的 ``McpConfig``。
    """

    settings: AppSettings
    models: ModelsConfig
    mcp: McpConfig = Field(default_factory=McpConfig)
    assistants: AssistantsConfig = Field(default_factory=AssistantsConfig)
