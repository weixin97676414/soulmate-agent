"""应用运行时（AppRuntime）。

把配置、模型注册表、Skill 管理器、会话管理器、持久化层、运行中任务与
待确认请求聚合成一个对象，由 FastAPI 的 app.state 持有。路由函数通过依赖
注入拿到它，避免到处使用全局单例（文档里用 ``SkillManager.instance()``，
但单例会让测试互相污染，这里改为显式持有）。

**降级策略**：数据库不可用时（磁盘只读、文件被占用等）自动降级为纯内存
模式，应用仍可正常对话，只是重启后数据不保留。宁可少一个功能，不可打不开。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from ..agent.evolution_tasks import ensure_builtin_tasks
from ..agent.history import HistorySearch
from ..agent.orchestrator import Orchestrator
from ..agent.scheduler import TaskScheduler
from ..agent.session import Session, SessionManager
from ..agent.task_store import ScheduledTaskStore
from ..assistants.bootstrap import BuiltinAssistants
from ..assistants.library import BuddyLibrary
from ..config.lines import DEFAULT_LINE
from ..config.loader import ConfigStore
from ..config.paths import AppPaths
from ..config.schemas import (
    AppConfig,
    AppSettings,
    AssistantProfile,
    AssistantsConfig,
    GroupsConfig,
    ModelsConfig,
    ModelSpec,
    ScheduledTaskSpec,
)
from ..config.secrets import ENV_SECRETS_FILE, apply_secrets, read_secrets_file
from ..config.skill_secrets import (
    ENV_SKILL_SECRETS_FILE,
    SkillSecrets,
    read_skill_secrets_file,
)
from ..errors import LLMError
from ..llm.base import BaseLLM
from ..llm.factory import build_llm, build_registry
from ..llm.registry import LlmRegistry
from ..mcp.manager import McpManager
from ..memory.long_term import LongTermMemory
from ..model_hub import ModelDownloader
from ..observability.metrics import METRICS
from ..observability.request_context import current_session_id
from ..observability.trace_store import TraceStore
from ..observability.tracer import Tracer
from ..security.confirm import ConfirmRequest
from ..security.paths import PathPolicy
from ..security.permission import PermissionGuard
from ..services import AuditService, UsageService
from ..skill.manager import SkillManager
from ..storage.audit import AuditRepository
from ..storage.db import Database
from ..storage.files import WorkspaceStore
from ..storage.group_events import GroupEventRepository
from ..storage.group_threads import GroupThreadRepository
from ..storage.life import ExpenseRepository, ReminderRepository
from ..storage.runs import RunStore
from ..storage.sessions import SessionRepository
from ..storage.usage import UsageRepository
from ..utils.timefmt import format_now
from .events import EventBus, ReminderScheduler

# 关停时等待在途任务收尾的上限。给足时间让 CancelledError 分支写完它该写的
# （补写部分文本、补齐未回填的工具调用），但不能无限等 —— 一个不响应取消的
# 任务会把整个退出流程挂住，用户看到的是"点了关闭但窗口不消失"。
SHUTDOWN_GRACE_SECONDS = 5.0

logger = logging.getLogger(__name__)


class RunningTask:
    """一个正在执行的 Agent 任务。"""

    def __init__(self, task_id: str, session_id: str, task: asyncio.Task) -> None:
        self.id = task_id
        self.session_id = session_id
        self.task = task
        self.started_at = time.time()
        self.tracer = Tracer()


@dataclass
class PendingConfirm:
    """一次等待用户响应的确认请求。

    ``owner`` 记录它属于哪个会话：一个会话被中断/关闭时，只应该让
    **它自己**的挂起确认失效，不能顺带把别的会话正在等待的确认一起拒掉。

    ``interrupted`` 区分"用户点了拒绝"和"这条任务被打断了"（停止生成、会话被关、
    进程重启）—— 两者都让操作不执行，但对用户来说是完全不同的两件事：
    前者是他自己的决定，后者是"我走开了一下，回来它自己没了"。
    上层靠它决定怎么记录与怎么解释，所以不能都只给一个 ``False``。
    """

    owner: str
    future: asyncio.Future[bool]
    interrupted: bool = False


@dataclass
class PendingPlan:
    """一次等待用户拍板的执行计划（单聊计划模式）。

    与 ``PendingConfirm`` 分开两套映射，而不是复用一套：确认通道承载的是
    **权限**语义（超时=拒绝、关系到安全），计划等待承载的是**交互**语义
    （不超时、用户可能想半天）。混在一起的话，任何一处调整超时或清理逻辑
    都会波及另一条路径。

    ``future`` 的结果是 ``(approved, feedback)``：

    - ``(True, "")``  → 用户点了「开始执行」
    - ``(False, 意见)`` → 用户点了「改一下」并写了意见，需要带着意见重拟
    - ``(False, "")`` → 用户点了「不用了」（或会话被关掉）
    """

    owner: str
    future: asyncio.Future[tuple[bool, str]]


@dataclass
class PendingInteraction:
    """一次等待用户回答的交互请求（选择 / 敏感输入）。

    ## 为什么这是**第三套**映射，而不是并进前两套

    前两套的分工在 ``PendingPlan`` 的注释里写过（确认=权限语义、计划=交互语义），
    而这一套与前两套都不同：**答案不是布尔，也不是"批准 + 意见"，而是任意结构** ——
    选择题回一个选项 id，敏感输入回一串名字。硬塞进任何一套都要把那套的 future 类型
    改成"联合类型"，读取方再各自判断，等于把三件事的复杂度叠在一起。

    ⚠️ 它的**答案里绝不含敏感值**：``kind == "secret"`` 那条路上，用户在弹窗里
    粘贴的内容由渲染层直接写进本地加密文件，回传到这里的只有名字
    （见 ``security/interaction.py`` 的模块注释）。所以这个 future 的结果
    可以安全地进日志。

    ## 收尾

    与计划一样**不设超时**（用户可能就是想半天，或者走开了一下）。收尾靠
    ``reject_pending``：断连 / 停止 / 关会话 / 退出时给它一个"没答"的结果
    （``{"cancelled": True, "interrupted": True}``），否则技能会永远挂在那里。
    """

    owner: str
    future: asyncio.Future[dict[str, Any]]


class AppRuntime:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths.ensure()

        # 密钥注入必须排在所有"读配置"的动作之前：LLM 注册表、MCP 管理器
        # 都在构造时就把 Key 用掉了，晚一步注入等于没注入。
        self.secrets = read_secrets_file(os.environ.get(ENV_SECRETS_FILE))
        # 用户经 `request_secret` 交给技能的密钥（私钥 / API Secret…）。
        # ⚠️ 与上一行**是两条互不相干的链路**：不同的临时文件、不同的环境变量、
        # 不同的存储文件。产品要求"不要动现有密钥存储逻辑"，
        # 所以这里绝不要想着把两者合并（理由见 ``config/skill_secrets.py`` 模块顶部）。
        self.skill_secrets = read_skill_secrets_file(os.environ.get(ENV_SKILL_SECRETS_FILE))
        # ⚠️ 内置搭子的数据源在这里注入（审计 M-20）：`config` 不再 import `assistants`，
        # 由这个组合根把"内置搭子长什么样"交给它（实现在 `assistants/bootstrap.py`）。
        self.config_store = ConfigStore(
            paths,
            manage_secrets=self.secrets is not None,
            builtin=BuiltinAssistants(),
        )
        self.config: AppConfig = self.config_store.load()
        if self.secrets is not None:
            apply_secrets(self.config, self.secrets)

        # AI 群：定义持久化（groups.json）。
        # 聊天记录**内存**保存一份（讨论过程中要频繁读写，走库太慢），
        # 同时逐条落库（见 GroupEventRepository）—— 切页面/重启后由前端重放恢复。
        self.groups: GroupsConfig = self.config_store.load_groups()
        # ⚠️ 键是 **(group_id, thread_id)** 而不是 group_id —— 一个群可以有多条
        # 对话（产品要求），各自有独立的上文。用单个 group_id 当键的话，
        # 切到另一条对话后模型会看到**上一条对话**的发言，表现为"它记得我没说过的话"。
        self._group_history: dict[tuple[str, str], list[dict[str, str]]] = {}

        settings = self.config.settings
        self.skills = SkillManager(
            PermissionGuard(
                confirm_mode=settings.security.confirm_mode,
                allow_admin=False,
            )
        )
        # 用户自定义技能。先放个空配置占位：真正的加载在 _register_builtin_skills 里
        # （那里同时注册内置与自定义，保证"技能总数"只在一处统计）。
        from ..config.schemas import CustomSkillsConfig

        self.custom_skills: CustomSkillsConfig = CustomSkillsConfig(skills=[])

        # 技能用的自定义技能存取口（见 skill/custom.py 的 CustomSkillStore）
        from ..skill.custom import CustomSkillStore

        self._custom_skill_store = CustomSkillStore(
            self.config_store.load_custom_skills,
            self.config_store.save_custom_skills,
            self.reload_custom_skills,
            skills_root=self.paths.skills_dir,
            # 只用于"这个 id 是不是内置技能"的重名判定（见 skill/install.py）
            skills=self.skills,
        )
        self.registry: LlmRegistry = build_registry(
            self.config.models, on_fallback=self._on_model_fallback
        )

        # ---- 持久化（尚未连接，由 initialize() 完成） ---------------- #
        self.db = Database(paths.db_file)
        self.sessions_repo = SessionRepository(self.db)
        self.audit_repo = AuditRepository(self.db)
        self.expense_repo = ExpenseRepository(self.db)
        self.reminder_repo = ReminderRepository(self.db)
        self.usage_repo = UsageRepository(self.db)
        # 窄服务（审计 L-01）：路由只认识这两个对象，不再直接摸上面的仓库。
        # ⚠️ 旧的转发方法（`record_usage` / `record_audit` / `record_op` / `price_of`）
        # 已在第 102 批**删除** —— 调用点全部切到 `self.usage.*` / `self.audit.*`。
        # 别再加回"顺手转发一个"：那会让服务里那份实现不再是唯一入口。
        # （下面那几个 `*_repo` 是**仓库本身**，服务要读它们，必须留着；调用方请走服务。）
        self.usage = UsageService(self)
        self.audit = AuditService(self)
        self.group_event_repo = GroupEventRepository(self.db)
        # 群「对话」（一个群多条独立消息流）。与单聊的 sessions 同构，见该模块说明。
        self.group_thread_repo = GroupThreadRepository(self.db, self.group_event_repo)
        # 未完成运行的进度（断点续跑）。与审计分开：那个要留存可查，这个跑完就删。
        self.runs = RunStore(self.db)
        self.workspace = WorkspaceStore(
            workspace_dir=paths.workspace_dir,
            artifacts_dir=paths.artifacts_dir,
            db=self.db,
        )
        self.sessions = SessionManager(
            repository=self.sessions_repo,
            on_persist_error=self._on_session_persist_error,
        )

        # 嵌入后端缓存：内置模型加载一次约 1.5s + 585MB，绝不能让每个搭子
        # 各加载一份（内存直接爆）。所有 per-assistant 实例**共享同一对 embedder**。
        # ⚠️ 必须在 self.long_term 之前初始化：_build_long_term_memory 会先读它。
        self._embedder_pair: tuple[Any, Any] | None = None
        # 每搭子独立的长期记忆实例（按 assistant_id 分 collection）。惰性构建：
        # 只有某个搭子真正读写记忆时才建它的实例，避免一启动就建一堆。
        self._memory_by_assistant: dict[str, LongTermMemory] = {}

        # 长期记忆：**惰性**实例（构造时既不导入 chromadb 也不建目录），
        # 所以即使功能一直没被使用，也不会在启动路径上留下任何成本。
        self.long_term = self._build_long_term_memory(paths)
        self.db_ready = False

        self.tasks: dict[str, RunningTask] = {}
        self.pending_confirms: dict[str, PendingConfirm] = {}
        # 等待产品拍板的执行计划（单聊计划模式；与确认通道分开，理由见 PendingPlan）
        self.pending_plans: dict[str, PendingPlan] = {}
        # 等待用户回答的交互请求（选择 / 敏感输入；第三套，理由见 PendingInteraction）
        self.pending_interactions: dict[str, PendingInteraction] = {}
        # 全局对话并发闸门（惰性创建，见 _ensure_slots）
        self._chat_slots: asyncio.Semaphore | None = None
        self._chat_slots_limit: int | None = None
        # 启动后台任务的句柄：投放区里技能包带的 MCP 配置靠它接入。
        # **必须留引用** —— 只 create_task 不存起来的话，任务可能被 GC 掉
        # （表现为"接了一半就没动静了"，且没有任何日志）。
        self._inbox_mcp_task: asyncio.Task[None] | None = None

        # 服务端主动推送通道（提醒到点等）
        self.events = EventBus()
        # 已结束的 Trace（内存有界留存），供 `GET /v1/traces/{id}` 查询。
        # 之前 Tracer 一直在产出 span 却没有任何接口能取回来 ——
        # 界面上显示了 trace_id，用户照着查却是 404。
        self.traces = TraceStore()
        self.reminder_scheduler = ReminderScheduler(self.reminder_repo, self.events)
        # 定时任务：与提醒共用事件通道，但会真的调用模型（见 agent/scheduler.py）
        self.task_scheduler = TaskScheduler(self)
        # 定时任务的配置读写门面：HTTP 路由与「搭子自建任务」技能都走它，
        # 保证 id 生成、字段归一化、"保存后重启调度"只有一份实现
        self.task_store = ScheduledTaskStore(self)
        # 搭子团队：AI 自己建搭子/建群，并把群讨论挪到后台跑（见 agent/orchestrator.py）。
        # 技能通过 ctx.service("team") 拿到它 —— 拿不到 runtime 本身，
        # 于是"这个技能到底改了什么"始终是有界的。
        self.orchestrator = Orchestrator(self)
        # 跨来源检索（群聊记录 / 单聊历史 / 长期记忆）：只读门面，
        # 注入给 `history_search` 技能用（见 agent/history.py）
        self.history_search = HistorySearch(self)
        # 官网搭子库：查清单 + 从官网导入搭子/搭子群。与 team 同一个套路（门面注入给技能），
        # 见 assistants/library.py 里"为什么单独一层"的说明。
        self.buddy_library = BuddyLibrary(self)
        # 当前线路（大陆 / 首尔）。主进程会在核心就绪后、以及线路结论变化时
        # 用 `PUT /v1/client/line` 同步进来；默认大陆，与客户端侧默认一致。
        # 它决定"官网搭子库页面"与"兑换码接口"用哪个域名（见 config/lines.py），
        # 以及**本地模型从国内源还是国外源下载**（见 model_hub/catalog.py）。
        self.line: str = DEFAULT_LINE

        # 本地模型下载器（语音 / 嵌入模型 起改为按需下载）。
        #
        # ⚠️ 它要发进度事件，而 `EventBus.publish` 是**同步**方法、下载器的 `publish`
        # 是 **async**（它活在 asyncio 任务里）—— 所以中间必须有一个适配器，
        # 不能把 `self.events.publish` 直接传进去（那会 `await` 一个 int，
        # 直到第一次下载才炸，而那时用户已经等着进度条了）。
        self.model_downloader = ModelDownloader(
            paths.models_dir, publish=self._publish_model_event
        )

        # 当前登录会话的凭证（心鉴学报告接口的凭证**由核心代发**）。
        #
        # 为什么不落盘：它是运行期的一次性登录态，写进配置文件等于在磁盘上留一份可被
        # 拷走的凭证；核心重启后主进程会重新推一次（见 `PUT /v1/client/session`）。
        # 为什么不交给模型：模型只要能拿到它，就能把它写进回复、导出文件或日志 ——
        # 所以凭证只活在内存里，由内置工具 `xjx_fetch_report` 在请求头里用掉，
        # **不进任何工具返回值、不进日志**（日志出口另有 security/redact.py 兜底）。
        self.session_token: str = ""

        # 文件访问白名单：工作区与产物目录永远放行，否则「上传了附件却读不了」
        self.path_policy = self._build_path_policy()
        self._register_builtin_skills()

        # MCP 服务：把第三方 Server 的工具包装成 Skill 注册进上面的 manager。
        # 构造在这里、连接放到 initialize()，因为建连是 IO 且可能很慢（npx 现下载）。
        self.mcp = McpManager(
            self.config.mcp,
            self.skills,
            persist=self.config_store.save_mcp,
            on_status_change=self._on_mcp_status,
            # 把目录白名单传下去：MCP 的 cwd 决定第三方 Server 在哪儿读写文件，
            # 用户既然配了白名单，就不该有一个子系统绕过它
            path_policy=self.path_policy,
        )
        # MCP 技能的权限改动要**写回配置**：配置是权限的唯一真相来源，
        # 不落盘的话下一次 sync_skills 会拿旧值覆盖回来（详见 set_permission 的注释）
        self.skills.set_permission_listener(self._persist_mcp_permission)

    # ------------------------------------------------------------------ #
    # 当前登录凭证（只在内存里，见 __init__ 里那段说明）
    # ------------------------------------------------------------------ #
    def set_session_token(self, token: str) -> None:
        """主进程推来的登录凭证；空串 = 已登出。

        ⚠️ 这个方法**只改内存、不写日志、不回显**。要排查问题时看"有没有凭证"
        （``bool(runtime.session_token)``），不要把它本身打出来。
        """
        self.session_token = (token or "").strip()

    @property
    def has_session_token(self) -> bool:
        """有没有登录凭证。给"如实告诉模型需要重新登录"用，不泄露凭证本身。"""
        return bool(self.session_token)

    def _persist_mcp_permission(self, skill: Any, level: str) -> None:
        """把某个 MCP 技能的权限写进它所属 Server 的 permission_overrides。"""
        server = getattr(skill, "mcp_server", None)
        tool = getattr(skill, "mcp_tool", None)
        if server and tool:
            self.mcp.set_tool_permission(server, tool, level)

    def _build_path_policy(self) -> PathPolicy:
        security = self.config.settings.security
        return PathPolicy(
            security.allowed_dirs,
            # ⚠️ `skills_dir` 必须**永远**可读，与工作区同级 —— 这是 补的洞：
            #
            # 指导型技能的正文默认不注入 system，模型要用的时候得自己去读
            # `<技能包目录>/SKILL.md`（见 `skill/custom.py::collect_instructions`）。
            # 而技能包目录在**用户数据目录**下，用户的文件白名单里通常没有它 ⇒
            # 配过白名单的用户，模型读不到那个文件 —— 表现是"技能装了、界面上也在、
            # 但搭子就是按不出来"，而且报错说"不在白名单内"，用户根本想不到
            # 要去把自己的应用数据目录加进白名单。
            #
            # 技能包是**应用自己落盘**的东西（`paths.py` 里就把它与 workspace 分开，理由是
            # "清空工作区不该删掉已装技能的辅助文件"），本就不该按"用户的文件"来管。
            always_allowed=[
                self.paths.workspace_dir,
                self.paths.artifacts_dir,
                self.paths.skills_dir,
            ],
        )

    # ------------------------------------------------------------------ #
    # 助手（Agent 预设）
    # ------------------------------------------------------------------ #
    @property
    def assistants(self) -> AssistantsConfig:
        return self.config.assistants

    def resolve_assistant(self, assistant_id: str | None) -> AssistantProfile | None:
        """按 id 取助手；id 为空或找不到时返回 None（调用方沿用默认配置）。"""
        if not assistant_id:
            return None
        return self.assistants.get(assistant_id)

    # 权限策略的**惰性**读取口（群聊那处按同样的理由写在 routes/groups.py 里，
    # 因为它要按群 id 重读 runtime.groups）。
    #
    # 为什么不能直接取值：搭子级的权限策略过去是在任务开始时被**快照**进
    # SkillContext 的，于是"任务跑到一半把模式改成自动批准"要等下一次任务才生效
    # （实测反馈）。调用方把这个方法包成闭包交给 SkillContext，
    # PermissionGuard 每次工具调用都会现场解析一次 —— 即时生效。
    def assistant_confirm_mode(self, assistant_id: str | None) -> str | None:
        """搭子级的权限确认策略；None = 没有覆盖、沿用全局。"""
        profile = self.resolve_assistant(assistant_id)
        return profile.confirm_mode if profile else None

    def save_assistants(self, config: AssistantsConfig) -> AssistantsConfig:
        saved = self.config_store.save_assistants(config)
        # ConfigStore 内部用 model_copy 生成了新的 AppConfig，runtime.config
        # 原来的引用会失效；不同步刷新的话，紧接着读 assistants 会拿到旧值。
        self.config = self.config.model_copy(update={"assistants": saved})
        return saved

    async def save_scheduled_tasks(
        self, specs: list[ScheduledTaskSpec]
    ) -> list[ScheduledTaskSpec]:
        """写回定时任务配置，并**立刻**重起调度。

        重起这一步不能省：调度器只在启动时建过一次循环，不重起的话
        "新建的任务要等下次启动客户端才会跑" —— 用户会认为功能坏了。
        已存在任务的计时由 ``TaskScheduler.restart()`` 保留，不会因此集体补跑。
        """
        settings = self.config.settings.model_copy(
            update={
                "agent": self.config.settings.agent.model_copy(
                    update={"scheduled_tasks": specs}
                )
            }
        )
        saved = self.config_store.save_settings(settings)
        self.config = self.config.model_copy(update={"settings": saved})
        await self.task_scheduler.restart()
        return list(saved.agent.scheduled_tasks)

    def seed_evolution_tasks(self) -> None:
        """补齐四条「全员进化中 X」预置任务；幂等，没缺的什么都不做。

        ⚠️ 这里**特意不走** ``save_scheduled_tasks``：那个方法会顺带 ``restart()`` 调度器，
        而本方法是在 ``task_scheduler.start()`` **之前**调用的（让这几条从本次启动起就在
        时间轴上）。在 start 之前 restart 会把调度器提前拉起来，和"启动顺序"那几行注释
        矛盾。所以这里只落盘 + 刷新内存里的 config，让紧接着的 ``start()`` 一次读到新配置。

        只补不覆盖：这几条一旦存在（哪怕用户/搭子改过时间或内容），启动就不该再碰它们。
        """
        current = list(self.config.settings.agent.scheduled_tasks or [])
        merged = ensure_builtin_tasks(current, list(self.config.assistants.assistants))
        if merged is current:
            return
        settings = self.config.settings.model_copy(
            update={
                "agent": self.config.settings.agent.model_copy(
                    update={"scheduled_tasks": merged}
                )
            }
        )
        saved = self.config_store.save_settings(settings)
        self.config = self.config.model_copy(update={"settings": saved})
        logger.info("已播种内置搭子的「全员进化」任务：新增 %d 条", len(merged) - len(current))

    @property
    def skill_services(self) -> dict[str, Any]:
        """注入给技能的共享服务（无助手绑定，memory 用全局单例）。"""
        return self.skill_services_for(None)

    def skill_services_for(
        self, assistant_id: str | None, group_id: str | None = None
    ) -> dict[str, Any]:
        """注入给技能的共享服务，其中 ``memory`` 绑定到**当前搭子**。

        ``group_id`` 非空（= 正在群聊）时，``memory`` 改绑**群记忆库** ——
        产品要求群记录成为群内成员的共同记忆，所以群里说"记住这件事"
        要落进群库（每个成员都看得到），而不是只落到当前发言那位搭子自己那儿。

        数据库不可用时返回空值而不是缺失键：技能会通过
        ``ctx.service()`` 得到「数据库未就绪」的明确提示。
        """
        if not self.db_ready:
            services: dict[str, Any] = {"expenses": None, "reminders": None}
        else:
            services = {"expenses": self.expense_repo, "reminders": self.reminder_repo}

        # 用户给技能的密钥（私钥 / API Secret…）。只有"真的发请求"的技能会读它，
        # 见 ``security/secret_ref.py``。
        #
        # ⚠️ 这里给的是**同一个对象**（不是副本），所以 ``apply_skill_secrets``
        # 热更新之后技能立刻能看到新值 —— 而那正是"用户刚粘贴完就能用"的实现方式。
        # 换成 `dict(...)` 拷贝的话，用户得重启客户端才生效。
        services["skill_secrets"] = self.skill_secrets

        # 长期记忆按开关提供。关掉时**故意不放这个键**，让 ctx.service("memory")
        # 抛出「拿不到服务」并触发技能里的启用说明——比给一个半死的对象清楚得多。
        if self.config.settings.memory.long_term_enabled:
            services["memory"] = (
                self.memory_for_group(group_id) if group_id else self.memory_for(assistant_id)
            )
        services["custom_skill_store"] = self._custom_skill_store
        # 搭子团队（建搭子 / 建群 / 后台群聊）：与 tasks 同一个套路 ——
        # 技能不直接改配置文件，走这层门面，规则（先查再建、同名拒绝）只有一份实现。
        services["team"] = self.orchestrator
        # 官网搭子库：技能靠它查"官网有没有合适的搭子"，以及从官网把包导进来
        services["buddy"] = self.buddy_library
        # 跨来源检索（群聊记录 / 单聊历史 / 长期记忆）。三份数据住在三处，
        # 技能拿不到 runtime，所以由这层只读门面统一去翻（见 agent/history.py）。
        services["history"] = self.history_search
        # 定时任务：搭子可以自己建/改/删/立刻跑（产品要求「搭子自建技能」）。
        # 它换了「直接改配置文件」那条路，走的是同一份门面实现。
        services["tasks"] = self.task_store
        # 日历：技能只认这个门面（本地 .ics 与 CalDAV 的选择在它内部完成），
        # 免得"查看/新建/修改/删除"四个技能各写一遍后端判断然后长歪。
        from ..calendar.service import CalendarService

        services["calendar"] = CalendarService(self.config.settings.calendar, self.paths)
        # 心鉴学取报告：**凭证只从这里出**。把 runtime 整个递给技能，技能就能顺
        # 手读到凭证、改线路、翻配置 —— 门面只开三个口（当前线路 / 有没有凭证 /
        # 发一次报告请求），见 skill/builtin/xjx_report.py。
        from ..skill.builtin.xjx_report import XjxGateway

        services["xjx"] = XjxGateway(self)
        return services

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #
    async def _adopt_legacy_memory_namespaces(self) -> None:
        """把旧内置搭子 id 的长期记忆库接管到新 id（见 ``presets.RENAMED_BUILTIN_IDS``）。

        长期记忆是按搭子分库的（``assistant_<id>``）：改了 id 就等于换了个库，
        老用户的记忆还在磁盘上却查不到 —— 表现为"我存过的资料不见了"。
        这里在启动时搬一次，失败只记 warning（记忆是增强能力，不能影响启动）。
        """
        if not self.config.settings.memory.long_term_enabled:
            return
        from ..assistants.presets import RENAMED_BUILTIN_IDS

        for old_id, new_id in RENAMED_BUILTIN_IDS.items():
            try:
                legacy = self._build_long_term_memory(self.paths, namespace=old_id)
                target = self.memory_for(new_id)
                if await target.adopt_legacy_collection(legacy.collection_name):
                    logger.info("已接管旧搭子记忆库: %s → %s", old_id, new_id)
            except Exception as exc:  # noqa: BLE001 - 单个库失败不影响启动
                logger.warning("接管旧搭子记忆库失败（%s → %s）: %s", old_id, new_id, exc)

    async def initialize(self) -> None:
        """连接数据库、恢复会话、清理过期审计、准备工作区目录。"""
        try:
            await self.db.connect()
            self.db_ready = True
        except Exception as exc:  # noqa: BLE001 - 降级而非崩溃
            logger.error("数据库初始化失败，降级为纯内存模式（数据不会保留）: %s", exc)
            self.db_ready = False
            self.sessions = SessionManager(repository=None)
            self.workspace = WorkspaceStore(
                workspace_dir=self.paths.workspace_dir,
                artifacts_dir=self.paths.artifacts_dir,
                db=None,
            )

        self.workspace.ensure_dirs()
        # 内置搭子改过 id（office → RelationBuddy 等）：把旧 id 下的长期记忆库接管过来。
        # 放在这里而不是懒加载路径上，是因为它必须**在用户第一次提问之前**做完 ——
        # 否则第一次检索会查到空库，用户会以为"我存过的资料丢了"。
        await self._adopt_legacy_memory_namespaces()
        restored = await self.sessions.initialize()
        await self.reminder_scheduler.start()
        # 连接 MCP Server 并注册工具；单个服务失败不影响整体启动
        await self.mcp.start_all()
        self.mcp.start_health_loop()
        # 技能投放区（``skills/inbox``）：用户把技能文件夹/文件丢进去，
        # 启动时自动接入。幂等（内容没变的不动），失败只记日志不阻断启动 ——
        # 投放区里有个坏包不该让客户端打不开。
        inbox = self.scan_skill_inbox()
        # 包里带的 MCP 服务配置：扫描只把它们**解析**出来（同步、快），真正接入是
        # async 且会拉起子进程的，所以丢到后台去做，启动不等它。
        # ⚠️ 这一步不能省：界面上那个「重新扫描」按钮已于 移除，
        # 这里是投放区 MCP 配置**唯一**还能被接上的途径（见 ``skill/inbox.py``）。
        roots = inbox.get("mcp_roots") if isinstance(inbox, dict) else None
        if roots:
            self._inbox_mcp_task = asyncio.create_task(
                self._connect_inbox_mcp(roots), name="inbox-mcp"
            )
        # 「全员进化」的四条预置任务：**在调度器启动之前**补齐，
        # 这样它们第一次启动就在时间轴上，不用等下一轮配置改动
        self.seed_evolution_tasks()
        # 放在 MCP 之后：定时任务可能要调用 MCP 工具，先让它们注册好。
        # 放到最后一行也顺带保证了"启动完成的日志打完才可能出现任务执行"。
        await self.task_scheduler.start()
        # 四分类名单自检（见 skill/groups.py::validate_registry）：名单里要是有一个写错的
        # 名字，那个技能会**静默掉进「内置技能」**（未登记一律算内置）—— 表现是
        # "它变成了关不掉的"，用户既关不掉也找不到原因，事后极难倒推。
        # ⚠️ 这里只**告警**、不抛异常：名单写错属开发期问题，不该让用户打不开客户端。
        from ..skill import groups

        missing = groups.validate_registry(self.skills.source_map())
        if missing:
            logger.warning(
                "技能分类名单里有 %d 个名字对不上任何已注册技能（它们会被当成内置技能）：%s",
                len(missing),
                "、".join(missing),
            )
        logger.info(
            "运行时已就绪：持久化=%s，历史会话=%s，模型=%s，技能=%s",
            "开启" if self.db_ready else "关闭",
            restored,
            len(self.registry),
            len(self.skills),
        )

        if self.db_ready:
            try:
                await self.audit_repo.purge_older_than(
                    self.config.settings.security.audit_retention_days
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("清理过期审计记录失败: %s", exc)

            # 断点续跑的两件清理：①上次被强杀留下的"还在跑"（没有可续跑的现场）
            # ②太久以前的待续跑记录（用户早忘了它是什么，留着只会让人以为"有东西没跑完"）
            try:
                await self.runs.clear_running()
                await self.runs.purge_older_than(30)
            except Exception as exc:  # noqa: BLE001
                logger.warning("清理运行记录失败: %s", exc)

            try:
                # 用量流水的保留期比审计长：审计是"事后追责"，
                # 用量是"长期成本趋势"，删早了就没法做月度对比
                await self.usage_repo.purge_older_than(
                    self.config.settings.usage.retention_days
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("清理过期用量记录失败: %s", exc)

    def _register_builtin_skills(self) -> None:
        from ..skill.builtin import discover_builtin_skills
        from ..skill.custom import backfill_display_names, sync_custom_skills
        from ..skill.factory import seed_factory_skills

        count = 0
        for skill_cls in discover_builtin_skills():
            try:
                self.skills.register(skill_cls)
                count += 1
            except Exception as exc:  # noqa: BLE001 - 单个 Skill 出错不影响启动
                logger.error("注册 Skill 失败 %s: %s", skill_cls, exc)
        logger.info("已注册 %s 个内置 Skill", count)

        # 用户自定义技能：它们**不在**内置列表里，要单独同步。
        # 放在同一个方法里而不是另一处，是因为两者的注册结果都会进
        # self.skills，分开写的话"技能总共有多少个"就要看两个地方。
        self.custom_skills = self.config_store.load_custom_skills()

        # 出厂技能播种：随客户端分发的那几百个技能，在这里进用户技能目录。
        # 它是**每个资源版本只做一次**的（版本 marker 判据），所以正常启动只是一次字符串比较。
        # ⚠️ 顺序：必须排在 `load_custom_skills` 之后（要往这份配置里加）、
        # `sync_custom_skills` 之前（注册进管理器的是这份配置）。见 `skill/factory.py`。
        factory = seed_factory_skills(self)
        # ⚠️ **无条件打**这条日志（不是只在真播种时打）：排查"技能怎么没出现"时，
        # "没播种的原因"和"播种结果"同样重要 —— 只看得到"播了"的日志，
        # 遇到"以为它会播、其实它判断成已播过/无资源"时就会完全抓瞎。
        logger.info("出厂技能：%s", factory)

        # 显示名回填：先装好的那批技能，定义里存的是 frontmatter 的
        # **英文 slug**，而中文名在包内 SKILL.md 的**正文标题**上 —— 不回填的话，
        # 界面上就是"英文名 + 灰字英文名"两行一模一样的东西。
        # 只改显示名、**不动 id**（id 是落盘目录名与搭子勾选记录的值，见
        # `skill/custom.py::backfill_display_names` 的说明）。
        #
        # ⚠️ 必须排在 `sync_custom_skills` **之前**：注册进管理器的是这份定义，
        # 顺序反了就成了"先把英文名注册上去、再改定义"，得等下次重启才生效。
        # ⚠️ 只有真改过才写盘（回填函数会如实返回），否则每次开机都白重写一遍配置。
        # ⚠️ 也必须排在**播种之后**：出场技能里若有没落盘成中文名的，这一趟能顺手带上。
        if backfill_display_names(self.custom_skills, self.paths.skills_dir):
            self.custom_skills = self.config_store.save_custom_skills(self.custom_skills)
        custom = sync_custom_skills(self.skills, self.custom_skills)
        if custom:
            logger.info("已注册 %s 个自定义技能", custom)

        # 「助手自己装技能」的入口：它要能写配置，所以不属于内置列表，
        # 但必须常驻可用 —— 不注册的话，用户说"帮我做个技能"模型就没有工具可用。
        from ..skill.custom import CustomSkillInstallSkill, SkillPackageInstallSkill

        try:
            self.skills.register(CustomSkillInstallSkill)
        except Exception as exc:  # noqa: BLE001
            logger.error("注册自定义技能安装器失败: %s", exc)

        # 从链接安装技能包（产品要求）：让模型能按用户给的 URL 自己下载并安装
        try:
            self.skills.register(SkillPackageInstallSkill)
        except Exception as exc:  # noqa: BLE001
            logger.error("注册技能包安装器失败: %s", exc)

    def reload_custom_skills(self, config: Any) -> int:
        """自定义技能变更后立即生效，无需重启。

        ⚠️ 变更后**必须广播 `skills_changed`**：标题栏右上角那个「N 个工具」
        读的是 `/v1/health` 的快照（见 `routes/system.py` 的 `health`），
        只有握手和重启会重拉。少了这条广播，用户上传一个技能包之后数字纹丝不动
        —— 他会以为上传失败了，然后反复重传实测反馈正是这个）。

        放在这里而不是逐个路由里加：``reload_custom_skills`` 是自定义技能变动的
        **唯一**出口（新增 / 删除 / 上传技能包 / 导入搭子包四条路都走它），
        挂在这里就不会漏掉将来新加的那第五条。
        """
        from ..skill.custom import sync_custom_skills

        self.custom_skills = config
        total = sync_custom_skills(self.skills, config)
        self.events.publish("skills_changed", total=total)
        return total

    def scan_skill_inbox(self) -> dict[str, Any]:
        """扫描技能投放区（``skills/inbox``）并接入，返回逐条结果。

        见 ``skill/inbox.py``：幂等（内容没变的不动）、以投放区的文件为准。

        **不接 MCP**（包里那份 MCP 配置在返回值的 ``mcp_roots`` 里原样带出去）：
        真正的接入由 :meth:`_connect_inbox_mcp` 在启动后于后台完成，或由
        ``skill/inbox.scan_inbox_async`` 在 HTTP 那条路上完成。

        失败只记日志、不抛出：技能文件夹里有个坏包不该让客户端启动不了。
        """
        from ..skill.inbox import scan_inbox

        try:
            outcome = scan_inbox(self)
        except Exception as exc:  # noqa: BLE001 - 启动路径上的任何异常都不该致命
            logger.error("技能文件夹扫描失败：%s", exc)
            # 形状要和正常返回**一致**：界面的结果弹窗会读 results / skipped，
            # 缺字段会让渲染层直接崩 —— 而这是在"已经出过错"的时候，最不该再炸一次。
            return {
                "ok": False,
                "installed": [],
                "results": [],
                "unpacked": {},
                "unrecognized": [],
                "skipped": [],
                "total": len(getattr(self.custom_skills, "skills", []) or []),
                "scanned": 0,
                "counts": {"added": 0, "updated": 0, "skipped": 0, "failed": 0},
                "message": f"技能文件夹扫描失败：{exc}",
            }
        if outcome.get("scanned"):
            logger.info("技能文件夹扫描：%s", outcome.get("message"))
        return outcome

    async def _connect_inbox_mcp(self, roots: list[Any]) -> None:
        """把投放区里技能包带的 MCP 服务配置接进来（启动后的后台任务）。

        **为什么放在后台、而不是扫描里**：接入 MCP 会真的拉起子进程 / 建连接，
        放在启动路径上会拖住客户端打开；用户投放区里放了个起不来的服务，
        也不该让客户端开不了。

        **为什么必须有这一步**：界面上那个「重新扫描」按钮已于 移除，
        这里成了投放区 MCP 配置**唯一**还能被接上的途径（见 ``skill/inbox.py``）。

        逐条记日志（成功的也记）：用户下次打开「MCP 服务」页看到多出来的服务时，
        日志里能查到它是**哪个技能包**带进来的。
        """
        from ..skill.install import install_mcp_roots

        try:
            records = await install_mcp_roots(self, roots)
        except Exception as exc:  # noqa: BLE001 - 后台任务，绝不向外抛
            logger.warning("投放区 MCP 服务接入失败：%s", exc)
            return
        if not records:
            return
        ok = sum(1 for item in records if item.get("ok"))
        logger.info("投放区 MCP 服务接入：%s/%s 个成功", ok, len(records))
        for item in records:
            if item.get("ok"):
                continue
            # 失败要看得见："包里带了 MCP 却没接上"是用户最难自己排查的一类问题
            logger.warning(
                "投放区 MCP 服务未接入 · %s：%s", item.get("name"), item.get("message")
            )
        if not ok:
            return
        # 新接的 MCP 工具会以 source="mcp" 注册成技能，**技能列表变了**。
        # 这次接入发生在客户端已经启动之后，不推这一条的话，用户要等到
        # 下次重启才能在技能页看到它们（"明明接上了却看不见"）。
        self.events.publish("skills_changed", total=len(self.skills.list_metas(enabled_only=False)))

    def utility_llm(self, fallback: BaseLLM) -> BaseLLM:
        """解析"压缩 / 规划 / 自检"要用的模型（设置项 ``agent.utility_model_id``）。

        四条调用路径（对话 / 群聊 / 定时任务 / 命令行）都从这里取，保证行为一致；
        返回的实例**一定与 fallback 同属当前注册表**，整轮租约才保护得到它。
        没配、配置的模型不存在/已停用时返回 ``fallback``（见 resolve_utility_llm）。
        """
        from ..llm.factory import resolve_utility_llm

        return resolve_utility_llm(
            self.registry, self.config.settings.agent.utility_model_id, fallback
        )

    # ------------------------------------------------------------------ #
    # 配置热更新
    # ------------------------------------------------------------------ #
    def _reload_config(self) -> None:
        """从磁盘重读配置并**重新注入密钥**。

        磁盘上的 Key 是空的（由 Electron safeStorage 托管），所以任何
        `load(reload=True)` 之后都必须重新注入，否则会出现
        "改完设置之后模型突然用不了了"。
        """
        self.config = self.config_store.load(reload=True)
        if self.secrets is not None:
            apply_secrets(self.config, self.secrets)

    async def reload_models(self, models: ModelsConfig | None = None) -> None:
        """模型配置变更后重建注册表，无需重启客户端。

        分四段计时并记录耗时：``PUT /v1/models`` 是自动保存每一次都会走的路，
        历史上它的总耗时（实测约 0.5s，且偶发长时间卡住）被笼统归成"保存很慢"，
        没有分段数据时无法判断该优化哪一段。
        """
        marks: list[tuple[str, float]] = []
        started = time.perf_counter()

        def mark(label: str) -> None:
            marks.append((label, (time.perf_counter() - started) * 1000))

        if models is not None:
            # 刻意**不**在这里 load(reload=True)：save_models 已经把带真实 Key 的
            # 配置放进内存缓存，从磁盘重读只会拿到剥离后的空 Key，
            # 表现为"刚填完 Key 点保存，下一次对话还是认证失败"。
            # 新 Key 由前端同时交给 Electron 加密保存，重启后由启动注入补上。
            self.config_store.save_models(models)
            mark("write_config")
            self.config = self.config_store.load()
            mark("load_config")
        else:
            self._reload_config()
            mark("reload_config")

        old = self.registry
        self.registry = build_registry(
            self.config.models, on_fallback=self._on_model_fallback
        )
        mark("build_registry")
        # ⚠️ **不能直接 `await old.aclose()`**。
        #
        # 那会关掉旧注册表里所有适配器的 httpx 客户端，而此刻**可能正有一个流式
        # 请求在用它们** —— 客户端一关，那个请求当场断掉（httpx 报
        # RemoteProtocolError），适配器包成 "模型流式调用网络异常"。
        #
        # 而触发它的动作非常"无辜"：**用户切到设置页**就会触发一次自动保存
        # （PUT /v1/models → 这里）。于是现象是"搭子回答到一半，我切个页面它就被
        # 打断了"，看起来完全不像配置保存造成的。上一轮只修了"切搭子"那条路径。
        #
        # `retire()` 的语义：没有在途请求就立刻关（绝大多数情况，行为与以前一致），
        # 有在途请求就只做标记，等最后一个租约还回来再关。
        await old.retire()
        mark("retire_old")

        total = marks[-1][1] if marks else 0.0
        steps = " ".join(
            f"{label}={value - (marks[index - 1][1] if index else 0):.0f}ms"
            for index, (label, value) in enumerate(marks)
        )
        logger.info(
            "模型注册表已重建，默认: %s（总 %.0fms；%s）",
            self.registry.default_id,
            total,
            steps,
        )

    def _embedder_cache(self) -> tuple[Any, Any]:
        """按当前设置构建（并缓存）嵌入器对：``(embedder, query_embedder)``。

        所有 per-assistant 记忆实例**共享同一对嵌入器**——内置模型加载一次
        就要 1.5s + 585MB，每个搭子各加载一份会直接把内存打爆。
        """
        if self._embedder_pair is not None:
            return self._embedder_pair
        settings = self.config.settings.memory
        backend = self._resolve_embedding_backend(settings)
        if backend == "api":
            embedder = self._build_api_embedder(settings)
            query_embedder = None
        elif backend == "ollama":
            embedder = self._build_ollama_embedder(settings)
            query_embedder = None
        else:
            embedder, query_embedder = self._build_builtin_embedder()
        self._embedder_pair = (embedder, query_embedder)
        return self._embedder_pair

    def _build_long_term_memory(
        self, paths: Any, *, namespace: str = ""
    ) -> LongTermMemory:
        """按当前设置构建长期记忆实例（含嵌入后端的选择）。

        三条路：内置中文模型（默认）/ 自定义厂商接口 / 本机 Ollama。

        返回两个嵌入器：第二个是**查询专用**的。只有内置中文模型需要它
        （查询要带指令前缀，文档不带），其余后端两者相同 —— 传 None 表示
        "查询与文档用同一个"。

        ``namespace`` 非空时（per-assistant），collection 会拆成
        ``assistant_<id>``，让每个搭子的记忆互不串味。
        """
        embedder, query_embedder = self._embedder_cache()
        return LongTermMemory(
            paths.data_dir / "vectors",
            namespace=namespace,
            embedder=embedder,
            query_embedder=query_embedder,
            # 设置页的「默认检索条数」在这里生效。改完设置会重建实例
            # （见 apply_settings），所以不用重启客户端。
            default_top_k=self.config.settings.memory.vector_top_k,
            # 「这个库是用哪种嵌入方式建的」—— 换模型后靠它发现"向量维度对不上"，
            # 然后用库里的**原文**重建向量（见 LongTermMemory.rebuild）。
            embedding_signature=self._embedding_signature(),
            # 重建完成时推一条事件 —— 界面要亲口告诉用户"记忆没丢，已经整理好了"。
            # ⚠️ 这不是锦上添花：重建要跑几十秒到几分钟，这期间检索是**跳过**的。
            # 界面上一声不吭的话，用户看到的就是"我问它，它说没有相关记忆"，
            # 然后合理推断出"换个模型把我以前的记忆弄丢了" —— 而这恰恰是最不该
            # 让用户去猜的一件事。
            on_rebuilt=self._on_memory_rebuilt,
        )

    def _on_memory_rebuilt(self, count: int) -> None:
        """某个记忆库重建完成 → 推给前端弹一条提示。"""
        if count <= 0:
            return
        self.events.publish("memory_rebuilt", count=count)

    async def _publish_model_event(self, event_type: str, data: dict[str, Any]) -> None:
        """模型下载进度：**异步 → 同步**的桥（下载器 await 它，EventBus 是同步的）。

        事件名由下载器给（固定 ``model_download``），载荷用 ``**data`` 展开 ——
        这样下载器不必知道 EventBus 的调用形态，前端也只是多了一条
        与 ``memory_rebuilt`` 同路的事件。
        """
        self.events.publish(event_type, **data)

    def _embedding_signature(self) -> str:
        """当前嵌入方式的指纹 —— 用来判断记忆库里的向量还能不能接着用。

        ⚠️ 为什么用"后端 + 模型"当指纹，而不是算一次向量看维度：
        算维度得先加载嵌入模型（内置那个 585 MB），而这段代码在构建记忆实例时
        就会被调到；同一个模型名的维度是稳定的。真要遇到"同名模型换了维度"，
        检索时会抛维度错，那条路上有兜底重建（见 ``long_term.search``）。

        ⚠️ **绝不能把 api key 之类会变的东西算进来**：用户换一次 key 就被判成
        "换了模型"，白白重建一遍全部记忆。
        """
        settings = self.config.settings.memory
        backend = self._resolve_embedding_backend(settings)
        if backend == "builtin":
            return "builtin"
        if backend == "ollama":
            url = str(getattr(settings, "embedding_ollama_url", "") or "").strip()
            model = str(getattr(settings, "embedding_ollama_model", "") or "").strip()
            return f"ollama|{url}|{model}"
        url = str(getattr(settings, "embedding_base_url", "") or "").strip()
        model = str(getattr(settings, "embedding_model", "") or "").strip()
        return f"api|{url}|{model}"

    def memory_for(self, assistant_id: str | None) -> LongTermMemory:
        """取某个搭子**专属**的长期记忆实例（惰性构建 + 缓存）。

        ``assistant_id`` 为空时返回全局单例 ``self.long_term``。

        ⚠️ **那个全局单例现在没有任何正常路径往里写了**（关掉了
        唯一的口子）：以前"没绑搭子的会话"归档会落到它这儿，而每个搭子检索时都会
        读它 —— 那等于把几段无主对话塞给所有搭子看。保留它是因为"跨搭子的公共
        记忆区"是个合理的位置，将来要开放也是这儿。
        """
        return self._memory_by_key(assistant_id or "")

    def memory_for_group(self, group_id: str | None) -> LongTermMemory:
        """取某个群**专属**的长期记忆实例 —— **群内每个成员共享这一个库**。

        产品要求：群聊天记录要成为"群内每个参与搭子的共同记忆"。
        在此之前群聊**根本不进长期记忆**（只躺在 ``group_events`` 表里），
        所以群里既不会串台、也检索不到任何长期记忆。

        collection 名：namespace 传 ``group_<id>`` → ``assistant_group_<id>``
        （``_scoped_collection`` 只保留字母数字与 ``_-``）。刻意加 ``group_`` 前缀，
        是为了**不可能撞上某个搭子的库** —— 搭子那份用的键是裸 id。
        """
        return self._memory_by_key(f"group_{group_id}" if group_id else "")

    def groups_for_assistant(self, assistant_id: str | None) -> list[str]:
        """反查：这个搭子**参与了哪些群**（返回群 id 列表）。

        群记忆要在**单聊**里也读得到 —— 但单聊没有 group_id，
        所以得先知道"它参与过哪些群"，才能把那些群库并进检索来源。

        ⚠️ 返回 id 而不是群对象：调用方（记忆检索）只需要拿去取库，拿群对象
        反而会诱使人去读它别的字段，把"记忆检索"和"群设置"耦合在一起。
        """
        if not assistant_id:
            return []
        return [
            group.id
            for group in self.groups.groups
            if assistant_id in (getattr(group, "member_assistant_ids", None) or [])
        ]

    def _memory_by_key(self, key: str) -> LongTermMemory:
        """按库键取实例（惰性构建 + 缓存）。键有两种：搭子裸 id、``group_<群id>``。

        ⚠️ **所有长期记忆实例都必须经这里取**：``apply_settings`` 换嵌入模型时是
        遍历 ``_memory_by_assistant`` 逐个 dispose + clear 的 —— 绕开这个 dict
        自建一份实例，换完模型它还攥着旧嵌入器，维度对不上，检索直接报错。
        """
        if not key:
            return self.long_term
        instance = self._memory_by_assistant.get(key)
        if instance is None:
            instance = self._build_long_term_memory(self.paths, namespace=key)
            self._memory_by_assistant[key] = instance
        return instance

    async def archive_turn(
        self,
        *,
        assistant_id: str | None,
        session_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        """把一轮对话**完整落库**到该搭子的长期记忆（产品要求）。

        只在长期记忆开启、且本轮确有一问一答时写入；写入走 ``to_thread``，
        不阻塞 SSE。metadata 标记 ``source=chat`` 与 session_id，供检索区分。

        失败静默：记忆归档不该影响"对话已经成功"这件事。
        """
        if not self.config.settings.memory.long_term_enabled:
            return
        # ⚠️ 没有搭子，就没有"谁的记忆"可言 —— 一律不写（产品定下的）。
        # 以前这种情况会落到**全局库**（collection `knowledge`），而每个搭子检索时
        # 都会读那个库 —— 于是"没绑搭子时聊的几段话"会被**所有**搭子看到，
        # 这正是用户问的那个串台口子。
        if not assistant_id:
            logger.info("会话 %s 没有绑定搭子，本轮不写入长期记忆（避免串台）", session_id)
            return
        user = (user_text or "").strip()
        assistant = (assistant_text or "").strip()
        if not user or not assistant:
            return
        # 带上时间：这段记录会在向量库里长期留存，检索回来时**"这是什么时候的事"**
        # 是它有没有用的前提（产品要求记忆有时间维度，别把旧的当当下聊）。
        # metadata 里的 ts 由长期记忆自己在写入时兜底补上，这里让**文本**也可读 ——
        # 模型看到的是文本，不是 metadata。
        record = f"[{format_now(time.time())}] 用户：{user}\n助手：{assistant}"
        try:
            await self.memory_for(assistant_id).add(
                [record],
                metadatas=[{"source": "chat", "session_id": session_id}],
            )
        except Exception:  # noqa: BLE001 - 归档失败绝不拖垮对话
            logger.warning("对话落库失败 assistant=%s session=%s", assistant_id, session_id)

    async def archive_group_turn(
        self,
        *,
        group_id: str,
        speaker: str,
        text: str,
        thread_id: str = "",
    ) -> None:
        """把群里某位成员的一条发言落进**群记忆库**（群内成员共享）。

        群聊天记录要成为"群内每个参与搭子的共同记忆"。
        在此之前群聊**完全不进向量库**（消息只躺在 ``group_events`` 表里），
        所以群里既检索不到长期记忆、也无从谈"共同"。

        ⚠️ 粒度取**一条发言**而不是"一整轮讨论"：一轮里有多个成员交替说话，
        整段存成一条的话，检索回来的一大坨里只有一句是相关的。

        ⚠️ 与单聊归档一样**失败静默**：少存一条记忆，不该影响"这轮讨论已经成功"。
        """
        if not self.config.settings.memory.long_term_enabled:
            return
        body = (text or "").strip()
        if not group_id or not body:
            return
        who = (speaker or "成员").strip()
        record = f"[{format_now(time.time())}] {who}：{body}"
        try:
            await self.memory_for_group(group_id).add(
                [record],
                metadatas=[{"source": "group", "group_id": group_id, "thread_id": thread_id}],
            )
        except Exception:  # noqa: BLE001 - 归档失败绝不拖垮群聊
            logger.warning("群发言落库失败 group=%s speaker=%s", group_id, who)

    @staticmethod
    def _resolve_embedding_backend(settings: Any) -> str:
        """把设置解析成后端名，**顺带兼容旧版本留下的字段**。

        旧配置里只有 ``use_api_embedding`` 一个开关。不认它的话，用户升级后
        自己选过"走接口"会悄悄变回内置 —— 那种"改了没生效"最难被察觉，
        因为两边都能跑、只是结果不同。
        """
        backend = (getattr(settings, "embedding_backend", "builtin") or "builtin").strip()
        if backend != "builtin":
            return backend
        if getattr(settings, "use_api_embedding", False) and (
            getattr(settings, "embedding_model_id", "")
            or getattr(settings, "embedding_base_url", "")
        ):
            return "api"
        return "builtin"

    def _build_api_embedder(self, settings: Any) -> Any:
        """自定义厂商接口。**密钥优先复用已配置模型**。

        复用已有模型有两个好处：密钥继续走既有的 safeStorage 托管（不在这份
        配置里落明文），且端点/模型名可以直接带出来，用户不用再填一遍。
        只有在用户确实要为独立端点单独配 Key 时才用 ``embedding_api_key``。
        """
        reused = self.config.models.get(
            getattr(settings, "embedding_key_model_id", "")
            or getattr(settings, "embedding_model_id", "")
        )
        base_url = (getattr(settings, "embedding_base_url", "") or "").strip() or (
            reused.base_url if reused else ""
        )
        model = (getattr(settings, "embedding_model", "") or "").strip() or (
            reused.model_name if reused else ""
        )
        key = (getattr(settings, "embedding_api_key", "") or "").strip() or (
            reused.api_key if reused else ""
        )

        if not base_url:
            logger.warning("长期记忆已设为接口嵌入，但拿不到端点地址；已回落到内置模型")
            return None

        from ..memory.embedding import ApiEmbedder

        logger.info("长期记忆使用接口嵌入：%s", model or "(未指定模型)")
        return ApiEmbedder(base_url=base_url, api_key=key, model_name=model)

    def _build_ollama_embedder(self, settings: Any) -> Any:
        model = (getattr(settings, "embedding_ollama_model", "") or "").strip()
        if not model:
            logger.warning("长期记忆已设为 Ollama，但没有选模型；已回落到内置模型")
            return None

        from ..memory.embedding import OllamaEmbedder

        logger.info("长期记忆使用 Ollama：%s", model)
        return OllamaEmbedder(getattr(settings, "embedding_ollama_url", ""), model)

    @staticmethod
    def _build_builtin_embedder() -> tuple[Any, Any]:
        """内置中文模型；拿不到就回落（返回 (None, None)）。

        回落到 chromadb 自带模型而不是直接禁用记忆 —— 那是英文模型且首次要
        联网下载，但至少"能用"，比整个记忆功能消失要好。
        """
        from ..memory.local_embedding import build_local_embedder

        builtin = build_local_embedder()
        if builtin is None:
            logger.warning("内置中文嵌入模型不可用，已回落到自带模型（英文、首次需联网）")
            return None, None
        return builtin, builtin.embed_query

    def apply_settings(self, settings: AppSettings) -> AppSettings:
        previous = self.config.settings
        saved = self.config_store.save_settings(settings)
        self._reload_config()
        self.skills.guard.set_confirm_mode(saved.security.confirm_mode)
        # 白名单变更需要立即生效，否则用户改了设置还得重启
        self.path_policy = self._build_path_policy()
        # 长期记忆的嵌入后端变了就重建实例：旧实例还拿着旧的 embedder，
        # 不重建的话用户换了模型却毫无变化（而向量维度可能已经不同，
        # 继续用旧实例写入会直接报维度不匹配）。
        #
        # ⚠️ 重建时必须把**三样**都丢掉，少丢任何一样都会表现为"改了设置没反应"：
        # 1. ``long_term``：全局那份实例；
        # 2. ``_memory_by_assistant``：每搭子那份实例。**对话里检索记忆走的正是它**
        #    （``history._from_memory`` → ``memory_for(assistant_id)``），不丢的话
        #    「默认检索条数」改了、嵌入后端换了，对话里都毫无变化；
        # 3. ``_embedder_pair``：嵌入器是**缓存的**，不丢的话新建的实例拿到的还是
        #    旧嵌入器 —— 连向量维度都不会变，等于白换。
        if saved.memory != previous.memory:
            self.long_term.dispose()
            for instance in self._memory_by_assistant.values():
                instance.dispose()
            self._memory_by_assistant.clear()
            self._embedder_pair = None
            self.long_term = self._build_long_term_memory(self.paths)
            logger.info("长期记忆已按新设置重建（含每搭子实例与嵌入器缓存）")
        return saved

    # ------------------------------------------------------------------ #
    # 会话
    # ------------------------------------------------------------------ #
    def effective_context_tokens(self, model_id: str | None) -> int:
        """本会话实际可用的上下文预算 = ``min(模型窗口, 用户设的硬上限)``。

        **为什么不能用一个全局常量**：那样"模型支持 100 万 token"这件事会完全
        失效 —— 用户把上下文窗口改到 100 万，记忆却仍在 3.2 万处被裁掉，
        而且界面上看不出任何异常。这类"配置了但不起作用"比缺功能难查得多。

        硬上限（``max_context_tokens``）为 0 时表示不设上限，直接用模型窗口。
        它保留下来是给"我想控成本，别让它一次吃掉几十万 token"这种需求用的。
        """
        window = 0
        try:
            window = self.registry.get(model_id).token_limit
        except Exception:  # noqa: BLE001 - 模型不可用时退回硬上限，不阻断会话
            logger.debug("取不到模型 %s 的上下文窗口，按硬上限处理", model_id)

        cap = self.config.settings.agent.max_context_tokens
        if window <= 0:
            # 模型窗口都拿不到：有硬上限就用它，否则用一个保守值兜底。
            # 保守值取 32K 是因为它小于几乎所有现代模型的窗口，
            # 宁可少用一点上下文，也不要在请求阶段被厂商拒掉。
            return cap if cap > 0 else 32768
        return min(window, cap) if cap > 0 else window

    async def get_session(self, session_id: str | None, *, model_id: str | None = None) -> Session:
        from ..memory.spill import SPILL_DIRNAME

        session = await self.sessions.get_or_create(session_id, model_id=model_id)
        session.memory.configure(
            # 按**这个会话实际要用的模型**算，而不是全局常量：
            # 会话可能记着自己的模型，也可能是路由刚换过的那个
            max_context_tokens=self.effective_context_tokens(model_id or session.model_id),
            # 装不下的内容**无损外置**到这里。
            #
            # 放 artifacts 目录是因为它本来就在路径白名单的"永远放行"列表里，
            # 模型能用 read_tool_output（以及 file_read）原样读回来 ——
            # 不需要为这个目录再开一条豁免。
            #
            # ⚠️ 这里**没有**"工具结果字符上限"这个参数了，而且不该再加回来：
            # 那个 4000 字符的截断会把内容真的丢掉（注释却声称"已落产物目录"）。
            # 详见 memory/short_term.py 顶部与 memory/spill.py。
            spill_root=self.paths.artifacts_dir / SPILL_DIRNAME,
            spill_session=session.id,
        )
        return session

    async def persist_session(self, session: Session) -> None:
        """对话**增长路径**的落盘：只追加新增的消息（第 87 批 B 组，M-04）。

        调用点全在这里，且全都是"一轮跑完、往会话尾部又加了几条"：
        ``routes/chat.py`` 的收尾、``agent/scheduler.py``（正常结束 / 中断 / 失败三处）、
        ``agent/orchestrator.py``（群聊结论写回）、``server/cli.py``。

        ⚠️ 以前这里是 ``persist(include_messages=True)``（整体替换）：一次 500 条的会话
        每轮要 DELETE 500 行再 INSERT 501 行，写放大是 O(n²) —— 长会话越聊越卡，
        而且每轮都把整表重写一遍会让 WAL 迅速膨胀。

        ⚠️ 会**删消息**的路径（``clear_history`` / 改系统提示词 / 新建会话）**不走这里**，
        它们直接调 ``sessions.persist`` 并保持默认的 ``replace``。
        另外 ``save_session`` 里的前缀指纹校验是最后一道闸：万一某条增长路径其实
        减少了消息，它会自动退回整体替换，不会留下已被删除的历史。
        """
        await self.sessions.persist(session, include_messages=True, mode="append")

    # ------------------------------------------------------------------ #
    # 并发限流
    # ------------------------------------------------------------------ #
    def _ensure_slots(self) -> asyncio.Semaphore:
        """取当前配置对应的信号量，配置变了就换一个。

        **不保留被替换掉的信号量**：已经在跑的任务持有的是旧对象，
        它们释放时释放的也是旧对象（见 release_chat_slot 接收对象参数）。
        换一个新的只是让后续任务按新上限排队，不会出现"释放错了对象"
        导致计数永久偏移。
        """
        limit = self.config.settings.agent.max_concurrent_chats
        if self._chat_slots is None or self._chat_slots_limit != limit:
            self._chat_slots = asyncio.Semaphore(limit)
            self._chat_slots_limit = limit
            logger.info("对话并发上限已设为 %s", limit)
        return self._chat_slots

    async def acquire_chat_slot(self) -> asyncio.Semaphore | None:
        """尝试占用一个对话位。等不到返回 ``None``，由调用方给出明确反馈。"""
        semaphore = self._ensure_slots()
        timeout = self.config.settings.agent.queue_wait_seconds
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        except TimeoutError:
            return None
        return semaphore

    @staticmethod
    def release_chat_slot(semaphore: asyncio.Semaphore) -> None:
        semaphore.release()

    def _on_model_fallback(self, failed: str, taken_over: str, reason: str) -> None:
        """主模型失败、已切到备用模型时通知界面。

        不通知的话用户会**在完全不知情的情况下**用着另一个模型 ——
        输出风格、能力甚至计费方都变了，而界面看不出任何区别。
        这对"按用量付费"的场景尤其要紧：他以为在花 A 家的钱。

        会话 id 从 ContextVar 取（适配器内部拿不到请求信息，见 request_context 的说明）。
        """
        # ⚠️ 降级次数要进指标（第 88 批，L-14）：以前整份指标里**没有失败 / 降级计数**，
        # 于是"这个用户的备用链是不是天天在顶"只能靠翻日志看 ——
        # 而这恰恰是"回答风格突然变了 / 费用算到了另一家"的唯一线索。
        # 标签只用模型 id（低基数），不会把指标撑爆。
        METRICS.inc("llm_fallback_total", model=failed, to=taken_over or "none")
        self.events.publish(
            "model_fallback",
            session_id=current_session_id.get(),
            failed_model=failed,
            taken_over=taken_over,
            reason=reason,
            message=(
                f"模型 {failed} 调用失败，已切换到 {taken_over}。"
                if taken_over
                else f"模型 {failed} 调用失败，且没有可用的备用模型。"
            ),
        )

    def _on_session_persist_error(self, session: Session, error: Exception) -> None:
        """会话落盘失败时通知界面。

        走事件推送而不是只写日志：用户看不到日志，而这件事的后果是
        「重启后这一轮对话没了」。必须在使用过程中就告诉他，
        而不是等他下次打开发现历史少了一段才纳闷。
        """
        self.events.publish(
            "session_save_failed",
            session_id=session.id,
            message="这一轮对话未能保存到本机数据库，重启后可能丢失。请检查磁盘空间与日志。",
            detail=str(error),
        )

    # ------------------------------------------------------------------ #
    # 审计与用量：**已整块搬走**（第 98 / 101 / 102 批）
    # ------------------------------------------------------------------ #
    # 这里原先有 `record_audit` / `record_op` / `price_of` / `record_usage` 四个方法。
    # 实现与入口现在都在服务上，**请直接用**：
    #
    #   await runtime.audit.record(entry)                  # 技能/工具留痕（权限级别、参数、耗时）
    #   await runtime.audit.op(kind=…, action=…, …)        # 业务操作留痕（搭子/群/会话/任务）
    #   runtime.usage.price_of(model_id)                   # 单价（含高峰时段与退价规则）
    #   await runtime.usage.record(…)                      # token 用量与费用
    #
    # ⚠️ 那两个同名转发方法（`record_audit` / `record_op` / `price_of` / `record_usage`）
    # 已在第 102 批删除。当初留转发，是为了"一次只搬一个子系统"（搬实现与改调用点分开做，
    # 出问题能分清是谁引起的）；调用点全切过来之后，转发就只剩坏处 ——
    # 留着会有人继续走旧入口，于是服务里那份实现永远成不了唯一真相。
    #
    # ⚠️ 也别在这里加"顺手转发一下"的便捷方法：需要审计/用量的调用方，
    # 该拿的本来就是服务（`runtime.audit` / `runtime.usage`），而不是 runtime 这个上帝对象。

    # ------------------------------------------------------------------ #
    # MCP
    # ------------------------------------------------------------------ #
    def _on_mcp_status(self, status: Any) -> None:
        """把 MCP 状态变化推给客户端。

        界面需要**实时**反映服务状态（工具数、连接灯、断连后工具消失），
        轮询接口做不到"断连立刻变灰"，所以走事件推送。
        """
        self.events.publish("mcp_status", server=status.to_dict())

    # ------------------------------------------------------------------ #
    # 任务登记
    # ------------------------------------------------------------------ #
    def register_task(self, session_id: str, task: asyncio.Task) -> RunningTask:
        running = RunningTask(uuid.uuid4().hex[:8], session_id, task)
        self.tasks[running.id] = running
        return running

    def unregister_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    def cancel_task(self, task_id: str) -> bool:
        running = self.tasks.get(task_id)
        if running is None or running.task.done():
            return False
        running.task.cancel()
        return True

    def cancel_session_tasks(self, session_id: str) -> int:
        return sum(
            1
            for running in list(self.tasks.values())
            if running.session_id == session_id and self.cancel_task(running.id)
        )

    # ------------------------------------------------------------------ #
    # 人工确认
    # ------------------------------------------------------------------ #
    async def request_confirm(self, request: ConfirmRequest, emit, owner: str) -> bool:
        """挂起等待用户在客户端点击「允许 / 拒绝」。

        ``emit`` 是一个 ``async callable``，负责把确认请求推给前端。

        ## ⚠️ 刻意**不设超时**（产品要求）

        原先 120 秒没响应就自动按拒绝。那在"用户正在忙别的"时是**灾难性**的：
        他回来看到的是"操作被拒绝了"，还得重新让搭子做一遍，而且完全不知道为什么
        —— 屏幕上没有任何东西告诉他"是你没及时点"。

        用户的要求是：**放开超时约束、无限等待**。代价是"忘了就会一直挂着"，
        但那有别的机制收尾（见下），而"被静默拒绝"没有任何机制能挽回。

        ## 收尾靠三条路，而不是超时

        - 用户点「允许 / 拒绝」 → ``resolve_confirm``；
        - 用户点停止 / 关闭会话 / 前端断连 → ``reject_pending``
          （把挂起的确认按拒绝清掉，**并让上层知道这条任务是"被打断"的**）；
        - 进程重启 → ``pending_confirms`` 本来就在内存里，自然丢弃。

        最后一条对应文档第 10 章的"不确认即不执行"：重启之后没有任何人点过允许，
        所以那个操作**必须**作废。这里不需要额外代码，但值得写明 —— 它是"用内存
        而不是落盘来存挂起确认"的**理由**，不是为了省事。
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        holder = PendingConfirm(owner=owner, future=future)
        self.pending_confirms[request.request_id] = holder
        try:
            await emit(request)
            approved = await future
            if not approved and holder.interrupted:
                # 不是用户拒绝，而是任务被打断（停止 / 关会话 / 重启）而作废。
                # 记成 info 而不是 warning：这不是异常，是一条正常的收尾路径。
                logger.info("确认请求因任务被打断而作废: %s", request.skill_name)
            return approved
        finally:
            self.pending_confirms.pop(request.request_id, None)

    def resolve_confirm(self, request_id: str, approved: bool) -> bool:
        pending = self.pending_confirms.get(request_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result(approved)
        return True

    async def request_plan_decision(self, plan_id: str, owner: str) -> tuple[bool, str]:
        """挂起等待用户在计划卡片上点「开始执行 / 改一下 / 不用了」。

        这里**不负责推送计划**：计划事件由引擎在挂起前 yield（见
        ``Agent._plan_phase``），顺序天然有保证 —— 前端先拿到卡片，
        才有得点。runtime 只管"等一个决定"。

        ⚠️ **刻意不设超时**（与 ``request_confirm`` 相反）：

        - 工具确认问的是"要不要执行这个动作"，用户没看手机就该按拒绝；
        - 计划确认问的是"这份计划行不行"，读一份计划本来就要花时间。
          设了超时，认真读计划的用户会被判成"不用了"，回来时卡片已经变成
          已取消 —— 比不给这个按钮还糟。

        用户点停止、关闭会话或断开连接时，由 ``reject_pending`` 收尾。
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[bool, str]] = loop.create_future()
        self.pending_plans[plan_id] = PendingPlan(owner=owner, future=future)
        try:
            return await future
        finally:
            self.pending_plans.pop(plan_id, None)

    def resolve_plan(self, plan_id: str, approved: bool, feedback: str = "") -> bool:
        """用户对计划做出了决定；返回是否命中一个仍在等待的计划。"""
        pending = self.pending_plans.get(plan_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result((approved, feedback))
        return True

    async def request_interaction(
        self, request: Any, emit: Any, owner: str
    ) -> dict[str, Any]:
        """挂起等待用户在弹窗里作答（选择 / 敏感输入）。

        ``emit`` 是一个 ``async callable``，负责把请求推给前端（与
        ``request_confirm`` 同一个形态）。

        ## 与 ``request_confirm`` / ``request_plan_decision`` 的两处不同

        1. **不负责"先推再等"的顺序**，而是自己 ``await emit(request)`` ——
           计划那条由引擎先把卡片推出去（``Agent._plan_phase``），因为计划内容是
           引擎算出来的；而这里的请求**完全由技能自己构造**，技能手里就有内容，
           让 runtime 顺手推出去比"技能先推、再调 runtime"少一层时序约定。
        2. **返回任意结构**，不是一个布尔。

        ## ⚠️ 刻意**不设超时**

        与计划同族（见 ``request_plan_decision``）：问的是"你指的是哪个"
        "把东西给我"，用户可能正在翻钱包、正在想 —— 设了超时，
        认真回答的人会被判成"放弃"，回来时弹窗已经没了。这比不问还糟。

        收尾靠 ``reject_pending``（停止 / 关会话 / 断连 / 退出）。
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_interactions[request.request_id] = PendingInteraction(
            owner=owner, future=future
        )
        try:
            await emit(request)
            return await future
        finally:
            self.pending_interactions.pop(request.request_id, None)

    def resolve_interaction(self, request_id: str, answer: dict[str, Any]) -> bool:
        """用户作答了；返回是否命中一个仍在等待的请求（``False`` = 已经不在等了）。"""
        pending = self.pending_interactions.get(request_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result(answer)
        return True

    def apply_skill_secrets(self, secrets: SkillSecrets) -> int:
        """整体替换"用户给技能的密钥"，返回替换后的条数。

        ## 为什么需要它（而不是靠重启）

        启动时 Electron 把密钥写进临时文件、Python **读完即删**（见
        ``config/skill_secrets.py``）—— 所以运行时新增的密钥**没法靠重写那个文件**
        送达。用户在弹窗里刚粘贴的密钥要让 AI 立刻能用，就必须有这条通道：
        Electron 写完盘后调核心的接口，把整份内容推过来。

        ## 为什么是"整体替换"而不是"增量合并"

        主进程那份是**唯一真相来源**（它有删除入口），核心这份只是镜像。
        增量合并会让"用户在管理面板里删掉一个"永远同步不过来 ——
        镜像比正本多几条，而没有任何地方会报错。

        ⚠️ 这条路径上的内容**会进内存**，但**不会**进日志：记条数就够了。
        """
        self.skill_secrets = secrets
        logger.info("用户给技能的密钥已更新：%s 条", len(secrets.keys))
        return len(secrets.keys)

    def reject_pending(self, owner: str | None = None) -> int:
        """让挂起的确认作废；``owner`` 为空时处理全部（用于整体关闭）。

        ⚠️ 作废时要**同时标记 ``interrupted``**：结果虽然都是"不执行"，
        但"用户点了拒绝"和"我走开了一下它就没了"对用户是完全不同的两件事，
        而且现在**没有超时会再兜底**（见 ``request_confirm``）—— 这一条路径
        是挂起确认唯一的收尾方式，含糊掉会让"操作怎么没执行"无从解释。
        """
        count = 0
        for pending in list(self.pending_confirms.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.interrupted = True
                pending.future.set_result(False)
                count += 1
        # 挂起的计划一并作废（等同「不用了」）：会话被关掉 / 任务被停止后，
        # 再没有地方能回传决定，留着它只会让任务永远醒不过来。
        for pending in list(self.pending_plans.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.future.set_result((False, ""))
                count += 1
        # 挂起的交互请求同样要收尾（新增）。
        # ⚠️ 少了这一段，用户点停止之后那个技能会**永远挂在那里** ——
        # 它没有超时兜底（见 request_interaction），唯一的出路就是这里。
        # ``interrupted`` 与 confirm 那条同一个用处：让技能能区分
        # "用户说不要"和"我走开了一下它就没了"。
        for pending in list(self.pending_interactions.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.future.set_result({"cancelled": True, "interrupted": True})
                count += 1
        return count

    # ------------------------------------------------------------------ #
    # 模型可用性测试
    # ------------------------------------------------------------------ #
    async def test_model(self, spec: ModelSpec) -> dict[str, Any]:
        llm = build_llm(spec)
        started = time.perf_counter()
        try:
            models = await llm.list_models()
            return {
                "ok": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "models": models,
            }
        except LLMError as exc:
            return {"ok": False, "error": exc.message}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            await llm.aclose()

    # ------------------------------------------------------------------ #
    # 关闭
    # ------------------------------------------------------------------ #
    async def shutdown(self) -> None:
        self.reject_pending()
        # 进行中的模型下载要先收掉：它是一个长跑任务（几百 MB），
        # 不等它退出就关进程的话会留下半截 .part，下次续传还得先判它坏没坏。
        await self.model_downloader.shutdown()
        # 先停调度器再关其它资源：否则一个正在跑的任务会在数据库关闭之后
        # 尝试落盘，退出时冒出一串"数据库尚未连接"
        await self.task_scheduler.stop()
        # 后台群聊也收掉：它可能还要跑几分钟，等它跑完用户会以为应用卡住了
        await self.orchestrator.shutdown()
        await self.reminder_scheduler.stop()
        # MCP 子进程必须显式回收，否则关掉客户端后它们会变成孤儿进程
        await self.mcp.stop_all()
        await self.long_term.aclose()
        pending = [r.task for r in list(self.tasks.values()) if not r.task.done()]
        for task in pending:
            task.cancel()

        # 必须**等它们真正退出**再关资源。
        # 原先是 ``await asyncio.sleep(0)``：那只是让出一次调度，被取消的任务
        # 还没来得及跑完 CancelledError 分支（补写部分文本、补齐未回填的工具调用）
        # 就去关库了 —— 存在一个"关库之后仍然尝试写库"的窗口，
        # 表现是退出时冒出一串莫名其妙的数据库错误。
        if pending:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=SHUTDOWN_GRACE_SECONDS,
                )
        self.tasks.clear()

        await self.registry.aclose()
        if self.db_ready:
            await self.db.close()
        # 浏览器是懒加载的：这里若启动过，就把它一起关掉，避免退出后留下孤儿浏览器进程。
        from ..browser.session import browser

        await browser.close()
        logger.info("运行时已关闭")


def create_runtime(paths: AppPaths | None = None) -> AppRuntime:
    """按默认数据目录构建运行时（供 SDK / 测试使用）。

    注意：调用方需要自行 ``await runtime.initialize()``。
    """
    return AppRuntime(paths or AppPaths.resolve())


__all__ = ["AppRuntime", "PendingConfirm", "RunningTask", "create_runtime"]
