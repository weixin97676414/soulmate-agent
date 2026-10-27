





from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator



logger = logging.getLogger(__name__)





AdapterKind = Literal["openai_compat", "ollama", "anthropic"]
ConfirmMode = Literal["interactive", "deny", "auto_approve"]


class PeakWindow(BaseModel):






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
        
        return minutes >= start or minutes < end

    @staticmethod
    def _minutes(text: str) -> int:
        try:
            hour, minute = text.split(":", 1)
            return int(hour) * 60 + int(minute)
        except Exception:  
            return -1


class ModelSpec(BaseModel):


    id: str = Field(..., description="模型在框架内的唯一标识，如 deepseek-chat")
    name: str = Field("", description="界面上展示的友好名称")
    provider: str = Field("", description="服务商标识，如 deepseek / openai / ollama")
    adapter: AdapterKind = "openai_compat"
    base_url: str = Field("", description="OpenAI 兼容端点根地址")
    api_key: str = Field("", description="访问密钥（独立运行时由系统加密托管，配置文件里留空）")
    
    
    
    
    use_system_proxy: bool = Field(False, description="请求是否走系统代理")
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    api_key_unchanged: bool = Field(
        False,
        exclude=True,
        description="仅请求侧：true 表示沿用旧配置里的 Key（忽略本次提交的值）",
    )
    
    
    clear_api_key: bool = Field(
        False,
        exclude=True,
        description="仅请求侧：true 表示显式清除该模型的密钥",
    )
    
    
    
    inherit_key_from: str = Field(default="", exclude=True)
    model_name: str = Field(..., description="请求体里传给厂商的真实模型名")

    token_limit: int = Field(32768, ge=1024, description="上下文窗口大小")
    supports_tools: bool = True
    supports_stream: bool = True
    timeout: float = Field(120.0, gt=0)

    
    
    
    tier: Literal["cheap", "standard", "strong"] = Field(
        "standard", description="能力档位：cheap（便宜快速）/ standard / strong（最强）"
    )
    
    
    supports_vision: bool = Field(False, description="是否支持图片输入")
    
    
    
    
    supports_reasoning: bool = Field(True, description="是否接受思考强度参数")

    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int | None = Field(None, gt=0)
    enabled: bool = True
    is_default: bool = False

    
    
    
    fallback_models: list[str] = Field(default_factory=list, description="备用模型 id，按顺序降级")

    
    
    
    
    
    
    
    price_input_per_1m: float | None = Field(None, ge=0, description="未命中输入的单价")
    price_cached_input_per_1m: float | None = Field(
        None,
        ge=0,
        description="命中缓存的输入单价；留空则按未命中价计算（不打折，偏保守）",
    )
    price_output_per_1m: float | None = Field(None, ge=0, description="输出单价")

    
    
    price_input_per_1m_peak: float | None = Field(None, ge=0, description="高峰时段的输入单价")
    price_output_per_1m_peak: float | None = Field(None, ge=0, description="高峰时段的输出单价")
    
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







        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}{'*' * 6}{self.api_key[-4:]}"


class ModelsConfig(BaseModel):


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

















    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    prompt: str = Field(..., min_length=1, description="每轮交给智能体的指令")
    assistant_id: str = Field("", description="用哪个助手跑；留空用默认配置")
    enabled: bool = False

    
    
    trigger: Literal["interval", "daily", "weekly"] = Field(
        "interval", description="interval=按间隔；daily=每天；weekly=每周"
    )
    
    
    
    interval_minutes: int = Field(60, ge=1, le=43200, description="间隔（分钟），上限 30 天")
    at_time: str = Field("09:00", description="每天 / 每周的执行时刻 HH:MM（24 小时制）")
    weekday: int = Field(0, ge=0, le=6, description="每周几执行；0=周一，6=周日")
    
    
    
    
    
    
    start_at: str = Field(
        "",
        description="trigger=interval 时的起始时间 YYYY-MM-DDTHH:MM（本机时间）；留空=从现在起算",
    )

    
    
    
    
    
    
    
    
    condition: Literal["none", "url_changed", "file_changed"] = Field(
        "none", description="none=无条件；url_changed=网页有变化；file_changed=文件有更新"
    )
    condition_target: str = Field(
        "", description="条件的目标：网页地址（http/https）或本地文件路径"
    )

    
    
    
    
    
    
    
    
    origin: Literal["user", "agent", "builtin"] = Field(
        "user", description="谁建的：user=界面上手工建；agent=搭子在对话里建；builtin=客户端预置"
    )

    
    
    
    
    silent: bool = Field(False, description="跑完不推通知（只留痕）")

    @field_validator("at_time")
    @classmethod
    def _check_at_time(cls, value: str) -> str:

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

        if self.condition != "none" and not self.condition_target.strip():
            raise ValueError("选择了触发条件，就必须填写网页地址或文件路径")
        return self


class ScheduledTaskDraft(ScheduledTaskSpec):






    id: str = Field("", max_length=64, description="留空则由后端生成")


class AgentSettings(BaseModel):


    
    
    
    
    
    max_iterations: int = Field(
        500, ge=1, le=100000, description="单次任务最大执行步数（模型↔工具往返），防失控"
    )
    
    
    
    max_tool_calls_per_turn: int = Field(500, ge=1, le=100000)
    temperature: float = Field(0.7, ge=0, le=2)

    
    
    
    
    
    
    
    top_p: float | None = Field(None, gt=0, le=1, description="核采样阈值；留空则不发送")
    
    
    
    frequency_penalty: float | None = Field(
        None, ge=-2, le=2, description="频率惩罚（治重复用词）"
    )
    presence_penalty: float | None = Field(
        None, ge=-2, le=2, description="存在惩罚（促新话题）"
    )

    system_prompt: str = ""
    
    
    
    confirm_mode: ConfirmMode = "interactive"
    
    
    
    
    
    
    
    
    
    max_context_tokens: int = Field(0, ge=0, description="上下文硬上限；0=跟随模型窗口")
    
    
    
    
    
    
    
    
    
    same_tool_failure_tolerance: int = Field(3, ge=1, le=10)

    
    
    
    compress_threshold: float = Field(0.8, ge=0.3, le=1.0)
    
    keep_recent_messages: int = Field(6, ge=2, le=40)
    
    
    
    
    
    
    
    
    
    
    utility_model_id: str = Field(
        "",
        description="压缩 / 规划 / 自检用哪个模型（填模型 id）；留空 = 跟随当前会话模型",
    )

    
    
    enable_planner: bool = False
    
    enable_reflection: bool = False
    reflection_rounds: int = Field(1, ge=1, le=3)

    
    
    
    
    
    auto_open_group_window: bool = True

    
    
    
    max_concurrent_chats: int = Field(4, ge=1, le=64)
    
    
    queue_wait_seconds: float = Field(15.0, ge=0, le=300)

    
    
    enable_model_routing: bool = False

    
    
    
    
    scheduled_tasks: list[ScheduledTaskSpec] = Field(default_factory=list)
    
    
    scheduler_tick_seconds: int = Field(60, ge=10, le=600)


class SecuritySettings(BaseModel):


    allowed_dirs: list[str] = Field(default_factory=list, description="文件读写白名单根目录")
    
    
    
    
    
    
    
    
    
    
    
    
    confirm_mode: ConfirmMode = "interactive"
    
    
    
    
    
    
    permission_overrides: dict[str, str] = Field(default_factory=dict)
    
    
    
    
    
    
    
    
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
    
    
    
    

    
    embedding_backend: Literal["builtin", "api", "ollama"] = Field(
        "builtin",
        description=(
            "builtin = 内置中文模型（离线、免费）；api = 自定义厂商接口；"
            "ollama = 本机 Ollama。默认 builtin：普通用户装完就该能用，"
            "不该先去申请一个 Key 才有记忆。"
        ),
    )

    
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

    
    embedding_ollama_url: str = Field(
        "http://127.0.0.1:11434", description="本机 Ollama 地址"
    )
    embedding_ollama_model: str = Field("", description="Ollama 里的嵌入模型名")

    
    use_api_embedding: bool = Field(False, description="已废弃；升级时用于推导 embedding_backend")
    embedding_model_id: str = Field("", description="已废弃；升级时用于推导 embedding_key_model_id")


class CalendarSettings(BaseModel):







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






    
    
    
    
    
    
    
    
    
    
    
    wake_words: list[str] = Field(
        default_factory=lambda: ["你好搭子"],
        description="唤醒词（可多个），说了它才开始录音",
    )
    
    
    send_word: str = Field("发送", description="说这个词才把内容发出去")
    
    
    
    
    
    
    cancel_word: str = Field("清空", description="说这个词清空刚说进输入栏的那一句")
    
    
    
    
    
    command_words: dict[str, str] = Field(
        default_factory=dict, description="语音命令词覆盖（动作 id → 命令词）"
    )
    
    
    disabled_commands: list[str] = Field(
        default_factory=list, description="已停用的语音命令 id"
    )

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    startup_mode: Literal["off", "global", "all"] = Field(
        "global", description="启动后：不监听 / 只开全局监听 / 全局+全体搭子待命"
    )

    
    
    
    
    
    
    
    
    
    
    
    
    
    enable_word: str = Field("打开语音", description="全局：打开语音功能的指令词")
    disable_word: str = Field("关闭语音", description="全局：关闭语音功能的指令词")

    @model_validator(mode="after")
    def _words_must_differ(self) -> VoiceSettings:




















        labels = {
            "发送词": self.send_word,
            "清空输入栏": self.cancel_word,
            
            
            "打开语音指令": self.enable_word,
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

        
        
        for action, word in (self.command_words or {}).items():
            text = (word or "").strip()
            if text and text in seen:
                raise ValueError(f"命令「{action}」的命令词「{text}」与{seen[text]}重复，换一个")
        return self


class AppSettings(BaseModel):


    app_name: str = "Soulmate Agent"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    trace_enabled: bool = True
    
    
    
    
    
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

    
    
    
    

    agent: AgentSettings = Field(default_factory=AgentSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    usage: UsageSettings = Field(default_factory=UsageSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    calendar: CalendarSettings = Field(default_factory=CalendarSettings)





class McpServerConfig(BaseModel):






    name: str = Field(..., min_length=1, max_length=64, description="服务标识，同时作为工具名前缀")

    
    
    
    transport: Literal["stdio", "sse", "streamable_http"] = "stdio"
    
    url: str = Field("", description="远程 MCP 端点地址")
    
    
    headers: dict[str, str] = Field(default_factory=dict)

    command: str = Field("", description="可执行文件，如 npx / uvx / python（仅 stdio）")
    args: list[str] = Field(default_factory=list, description="启动参数")
    env: dict[str, str] = Field(default_factory=dict, description="附加环境变量")
    cwd: str | None = Field(None, description="工作目录；留空则继承客户端进程")

    enabled: bool = True
    auto_start: bool = Field(True, description="客户端启动时是否自动连接")
    description: str = ""
    timeout: float = Field(60.0, gt=0, le=600, description="单次工具调用的超时时间")
    
    permission_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_transport_fields(self) -> McpServerConfig:






        if self.transport == "stdio":
            if not self.command.strip():
                raise ValueError("stdio 传输必须填写启动命令（command）")
        elif not self.url.strip():
            raise ValueError(f"{self.transport} 传输必须填写端点地址（url）")
        return self

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:

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
        
        if not all(ch.isalnum() or ch == "_" for ch in cleaned):
            raise ValueError("参数名只能包含字母、数字和下划线")
        return cleaned


class CustomSkillDef(BaseModel):











    id: str = Field(..., min_length=1, max_length=64, description="工具名（会原样进工具 Schema）")
    name: str = Field(..., min_length=1, max_length=48, description="界面上的显示名")
    description: str = Field("", max_length=600, description="模型决定要不要调用的唯一依据，写清楚什么时候用")
    params: list[CustomSkillParam] = Field(default_factory=list)

    
    
    
    kind: Literal["http", "command", "instruction"] = "http"

    
    instructions: str = Field("", description="指导内容原文（来自 SKILL.md），会注入 system")

    
    url: str = Field("", description="请求地址，可含 {参数名} 占位符")
    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, description="请求头，值可含 {参数名}")
    body_template: str = Field("", description="请求体模板，可含 {参数名}；GET/DELETE 通常留空")

    
    command_template: str = Field("", description="要执行的命令，可含 {参数名}，例如 ping {host}")

    timeout: float = Field(30.0, gt=0, le=120)
    permission_level: Literal["safe", "confirm", "admin"] = "confirm"
    enabled: bool = True

    
    
    
    
    
    
    
    
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





        result = template
        for param in self.params:
            value = values.get(param.name)
            if value is None:
                value = param.default if param.default is not None else ""
            result = result.replace("{" + param.name + "}", str(value))
        return result

    @staticmethod
    def _split_command_template(template: str) -> list[str]:















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














        return [self.render(values, token) for token in self._split_command_template(template)]


class CustomSkillsConfig(BaseModel):


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













    cleaned = (name or "").strip()
    if not cleaned:
        return ["你好搭子"]
    return [f"你好{cleaned}"]


class AssistantProfile(BaseModel):












    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    
    
    nickname: str = Field("", max_length=48)
    emoji: str = "🤖"
    description: str = ""
    system_prompt: str = ""

    model_id: str = Field("", description="留空表示跟随全局默认模型")
    temperature: float | None = Field(None, ge=0, le=2)
    
    
    max_iterations: int | None = Field(None, ge=1)
    
    max_tool_calls_per_turn: int | None = Field(None, ge=1)
    
    
    
    
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        None, description="思考强度；留空跟随全局"
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _normalize_reasoning_effort(cls, value: Any) -> Any:















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

    
    
    
    
    
    
    
    
    enabled_skills: list[str] = Field(default_factory=list)

    
    
    
    
    
    
    
    
    
    
    
    group_role: Literal["", "coordinator", "worker", "reviewer", "advisor"] = Field(
        "", description="群聊角色：协调者 / 执行者 / 优化顾问 / 审核员；留空 = 按发言位次兜底"
    )
    confirm_mode: ConfirmMode | None = Field(
        None, description="该助手专属的权限策略；留空表示沿用全局设置"
    )

    
    
    
    
    
    
    
    
    
    
    
    voice: VoiceSettings = Field(default_factory=VoiceSettings)

    
    
    
    
    
    
    
    avatar: str = ""

    
    
    chat_background: str = ""

    
    
    
    
    
    
    
    
    
    persona_password_hash: str = ""
    persona_password_salt: str = ""

    @model_validator(mode="after")
    def _seed_wake_words(self) -> AssistantProfile:















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
        
        
        
        
        
        
        data["restricts_skills"] = bool(self.enabled_skills)
        
        
        
        data.pop("persona_password_hash", None)
        data.pop("persona_password_salt", None)
        data["persona_locked"] = bool(self.persona_password_hash)
        return data

    
    
    
    def set_persona_password(self, password: str) -> None:

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
        
        return hmac.compare_digest(expected, actual)


class AssistantsConfig(BaseModel):


    assistants: list[AssistantProfile] = Field(default_factory=list)
    default_assistant: str = ""

    def get(self, assistant_id: str) -> AssistantProfile | None:











        found = next((item for item in self.assistants if item.id == assistant_id), None)
        if found is not None:
            return found
        
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






    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=48)
    
    member_assistant_ids: list[str] = Field(default_factory=list)
    
    
    speaking_order: list[str] = Field(default_factory=list)

    
    
    
    
    
    
    
    
    avatar: str = Field("", description="群头像（data URL）；留空由前端按规则补一张")

    
    
    
    
    
    confirm_mode: ConfirmMode | None = Field(
        None, description="该群专属的权限策略；留空沿用各成员自己的设置"
    )
    
    
    
    
    
    
    
    
    
    
    
    
    
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        "medium", description="该群的思考强度；默认「中」，可清回跟随成员各自的设置"
    )

    
    
    
    
    
    
    
    
    
    
    
    reviewer_id: str = Field("", description="该群已确认的审核员搭子 id；空 = 还没提交")
    advisor_id: str = Field("", description="该群已确认的优化顾问搭子 id；空 = 还没提交")

    
    
    
    
    
    
    
    
    coordinator_id: str = Field("", description="该群已指名的总管搭子 id；空 = 走位次兜底")

    def roles_ready(self) -> bool:





        return bool(self.reviewer_id.strip()) and bool(self.advisor_id.strip())

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    wake_words: list[str] = Field(
        default_factory=lambda: ["你好群聊"],
        description="语音唤醒词（可多个）；说了它切到这个群",
    )

    @model_validator(mode="after")
    def _seed_wake_words(self) -> GroupProfile:






















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





    settings: AppSettings
    models: ModelsConfig
    mcp: McpConfig = Field(default_factory=McpConfig)
    assistants: AssistantsConfig = Field(default_factory=AssistantsConfig)
