"""Skill 系统的抽象基类与上下文。

对应《智能体框架开发文档》5.2 节。Skill 是本框架的**核心抽象**：
内置函数、MCP 工具、HTTP API 全部收敛为 Skill，Agent 层无感知底层实现。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import SkillExecutionError
from ..security.audit import AuditCallback
from ..security.confirm import ConfirmCallback, ConfirmRequest
from ..security.interaction import InteractionCallback, InteractionRequest
from ..security.paths import PathPolicy

if TYPE_CHECKING:
    from ..config.schemas import AppSettings
    from ..observability.tracer import Tracer

PermissionLevel = str  # safe / confirm / admin

# --------------------------------------------------------------------------- #
# 终止标记
# --------------------------------------------------------------------------- #
# 工具结果里带上它时，引擎会立刻结束本轮任务，不再让模型多跑一轮。
#
# 用途：有些工具本身就是任务的**终点**（"算完就好"、"已提交，等人工处理"）。
# 不加标记的话，模型拿到结果还要再生成一段总结，再判断一次要不要继续 ——
# 白白多花一轮 token，而且可能自作主张继续调用别的工具。
#
# 用内容标记而不是 Skill 返回值里的结构化字段：工具结果是**字符串**回填给模型的，
# 结构化字段到不了模型那一侧，也就无法参与"让模型也知道任务结束了"这个目的。
TERMINATION_MARKER = "⟪stop⟫"


def mark_terminate(text: str) -> str:
    """给工具结果打上终止标记。"""
    return f"{text}\n{TERMINATION_MARKER}"


def wants_terminate(text: str) -> bool:
    """工具结果是否要求结束本轮任务。"""
    return TERMINATION_MARKER in text


@dataclass
class SkillMeta:
    """Skill 元数据。``description`` 直接进入工具 Schema，是模型决定是否调用的唯一依据。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    # 分类取值由各技能自己声明，前端 `SkillSettings.CATEGORY_META` 必须与之对应，
    # 否则那一类会回退显示成「通用」（多栏同名的由来）。当前在用：
    # office / life / system / memory / knowledge / thinking / persona / general / custom / mcp
    category: str = "general"
    permission_level: PermissionLevel = "safe"
    timeout: float = 30.0
    requires: list[str] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    source: str = "builtin"  # builtin / mcp
    display_name: str = ""
    # 永久开启 + 免批准（见 skill/locked.py）。由 SkillManager 在**注册时**按名单推导，
    # 不写在装饰器里：名单是唯一的真相来源，散落在各技能里迟早会漏一个。
    locked: bool = False
    #: 技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）。
    #: ⚠️ 与 `category` 是**两个维度**：`category` 说"这技能干什么"（10 个固定值），
    #: `domain` 说"它属于哪个行业 / 领域"（电商 / 金融 / 医疗…）。
    #: 第三方技能包导入时随包带进来；客户端自带的通用技能由 `groups.BUILTIN_DOMAINS` 补。
    #: 空 = 没归类（界面归到「其它」）。
    domain: str = ""
    #: **仅命令型自定义技能**会填：把本轮参数渲染成"实际会执行的那条命令"，
    #: 供确认卡如实展示 —— 确认卡本来只列参数值，用户看不出 ``{host}`` 被填成了什么。
    #: 见 ``skill/custom.py``（写入）与 ``security/permission.py::check``（消费）。
    #:
    #: ⚠️ 它是个**函数**，绝不能进 ``to_dict()``（不可 JSON 序列化，会炸掉 `/v1/skills`）。
    command_preview: Callable[[dict[str, Any]], str] | None = None

    def to_dict(self) -> dict[str, Any]:
        # 四分类（我的 / 通用 / 内置 / 专属）的唯一真相来源是 `skill/groups.py`，
        # 这里只负责下发 —— 前端技能页那四个子页按它分栏、**不重算**：
        # 两边各有一套归类规则的话，改一处必然对不上。
        from . import groups  # 函数内导入：base 是地基模块，别牵进业务模块的导入顺序

        owners = groups.owners_of(self.name)
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "permission_level": self.permission_level,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "tags": list(self.tags),
            "source": self.source,
            # ⚠️ 与 `category`（细类：办公 / 生活 / 系统…）是**两个维度**，别混用。
            # 小分类（domain）要一起传下去：带它归「通用技能」、不带归「我的技能」
            # （产品约定，见 groups.bucket_of）。
            "bucket": groups.bucket_of(
                self.name,
                self.source,
                self.domain or groups.BUILTIN_DOMAINS.get(self.name, ""),
            ),
            # 专属技能才有归属，前端据此显示「仅 XX 可用」
            "owners": list(owners),
            "owner_label": groups.owner_label(owners),
            # 界面据此**不渲染**开关与权限下拉框。老核心的响应里没有这个字段，
            # 前端按 undefined 处理 = 未锁定，不会误把开关藏起来。
            "locked": self.locked,
            # 技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）。
            # 第三方技能包导入时随包带进来；客户端自带的通用技能从 groups 的映射补 ——
            # 两处在**这里**合成，前端不重算（两边各一套规则必然对不上）。
            "domain": self.domain or groups.domain_of(self.name),
        }


class SkillContext:
    """一次 Skill 执行的环境：注入配置、日志、追踪、确认通道、审计与路径。"""

    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        logger: logging.Logger | None = None,
        tracer: Tracer | None = None,
        paths: Any = None,
        confirm: ConfirmCallback | None = None,
        interaction: InteractionCallback | None = None,
        audit: AuditCallback | None = None,
        session_id: str | None = None,
        assistant_id: str | None = None,
        group_id: str | None = None,
        workspace: Any = None,
        path_policy: PathPolicy | None = None,
        extra: dict[str, Any] | None = None,
        confirm_mode: str | None | Callable[[], str | None] = None,
        allow_admin: bool = False,
    ) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger("my_agent.skill")
        self.tracer = tracer
        self.paths = paths
        self.confirm = confirm
        # 交互通道（向用户发起选择 / 敏感输入弹窗）。与 ``confirm`` 并列但语义不同：
        # ``confirm`` 问"允不允许"，答案是布尔；这个问"你指的是哪个 / 把东西给我"，
        # 答案是任意结构，而且**不设超时**（见 ``ask_interaction``）。
        self.interaction = interaction
        self.audit = audit
        self.session_id = session_id
        # 当前助手。技能需要它才能读写"这个助手自己的"人格与记忆文件 ——
        # 靠模型在参数里传助手 id 是不可靠的（它会猜，猜错就写到别人身上）。
        self.assistant_id = assistant_id
        # 当前所在的**群**（只有群聊才有）。产品要求群记录成为群内成员的
        # 共同记忆：记忆检索要靠它把"这个群的库"并进来，群里说"记住这件事"也要落进
        # 群库（否则只有当前发言那位搭子自己记得）。
        # ⚠️ 单聊时为空 —— 单聊读不到群记忆，这是刻意的（群是群、单聊是单聊）。
        # 单独一个字段而不是靠解析 session_id：群聊时 session_id 是 ``group:<id>``
        # 这种字符串约定，让技能去拆它，迟早被某个别处的改动悄悄弄坏。
        self.group_id = group_id or ""
        # 本会话的权限策略覆盖（来自助手预设）。放在 ctx 而不是改 PermissionGuard，
        # 是因为 guard 是全局共享的——按会话改它会在并发会话间串味。
        #
        # 也可以传**惰性提供者**（``Callable[[], str | None]``）：搭子在任务跑到
        # 一半时改了权限策略，应当**立刻**生效而不是等下一次任务。传死值就是
        # 任务开始那一刻的快照，所以单聊 / 群聊都传闭包，由
        # ``PermissionGuard.effective_mode`` 在每次工具调用时现场解析。
        # （定时任务例外：它写死 ``auto_approve``，见 ``agent/scheduler.py``。）
        self.confirm_mode = confirm_mode
        # 本次调用是否放开 admin（高危）级。默认 False —— 前台单聊与群聊都不碰它。
        # 只有定时任务传 True：后台无人值守，没人能点「允许」，不放开就等于
        # "高危技能在定时任务里永远跑不了"。为什么放在 ctx 而不是守卫上，
        # 见 ``PermissionGuard.allow_admin``。
        self.allow_admin = allow_admin
        # 工作区仓储（WorkspaceStore），供文件类 Skill 读写与登记产物
        self.workspace = workspace
        self.path_policy = path_policy or PathPolicy()
        self.extra = extra or {}

    @property
    def has_confirm_channel(self) -> bool:
        """是否存在可用的人工确认通道（HTTP 服务层会注入确认回调）。"""
        return self.confirm is not None

    async def ask_confirm(self, request: ConfirmRequest) -> bool:
        """向用户请求确认；无确认通道时**默认拒绝**（对齐文档 5.6 节）。"""
        if self.confirm is None:
            self.logger.warning("Skill %s 需要确认但无确认通道，已拒绝", request.skill_name)
            return False
        return await self.confirm(request)

    @property
    def has_interaction_channel(self) -> bool:
        """是否存在可用的交互通道（HTTP 服务层的单聊 / 群聊会注入）。

        ⚠️ **定时任务与 CLI 故意没有这个通道**（见 ``agent/scheduler.py`` 与
        ``server/cli.py``）：它们无人值守，挂起等于永远卡住。技能要靠这个属性
        决定"能不能问"，而不是假定总能问。
        """
        return self.interaction is not None

    async def ask_interaction(self, request: InteractionRequest) -> dict[str, Any]:
        """向用户发起一次交互（选择 / 敏感输入）并等回答。

        ## ⚠️ 无通道时返回"没答"，而**不是**抛错

        与 ``ask_confirm`` 的"无通道即拒绝"不同，这里返回
        ``{"cancelled": True, "reason": "no_channel"}`` —— 让技能能**优雅降级**：
        无人值守时不该把整轮任务炸掉，而该"按最可能的理解往下做，并说明这是假设"。
        两种做法的差别是"任务失败"和"任务降级完成"，后者明显更有用。

        ## ⚠️ 它**不受技能超时保护**（实现这两个技能时必须知道）

        ``manager._run_with_timeout`` 把整个 ``skill.run()`` 包在
        ``asyncio.wait_for(timeout=meta.timeout)`` 里，而这个方法是在技能自己的
        ``run()`` 内部被调用的 —— 也就是说**超时是生效的**（与 ``ask_confirm``
        不同，那个在等待包装之外）。默认 30 秒会把"用户还没想好"判成超时。

        ⇒ 用这条通道的技能必须把 ``timeout`` 设得足够大
        （这两个技能设的是 24 小时，那只是兜底，不是业务超时）。
        这一点已由 ``core/_chk_timeout.py`` 实证过：短 timeout 会在 1.00s 精确掐断，
        大 timeout 下挂起 3 秒正常返回。
        """
        if self.interaction is None:
            self.logger.warning(
                "Skill %s 需要用户交互但无交互通道（无人值守？），已按「未作答」降级",
                request.skill_name,
            )
            return {"cancelled": True, "reason": "no_channel"}
        return await self.interaction(request)

    # ---- 常用路径快捷访问 ------------------------------------------------ #
    @property
    def workspace_dir(self) -> Path:
        if self.paths is None:
            return Path.cwd()
        return Path(self.paths.workspace_dir)

    @property
    def artifacts_dir(self) -> Path:
        if self.paths is None:
            return Path.cwd() / "artifacts"
        return Path(self.paths.artifacts_dir)

    # ---- 文件路径安全访问 ------------------------------------------------ #
    def resolve_path(self, path: str, *, mode: str = "read") -> Path:
        """校验用户/模型给出的路径是否在白名单内。

        **所有涉及文件读写的 Skill 都必须走这里**，不要直接用 ``Path(...)``，
        否则白名单形同虚设。
        """
        return self.path_policy.check(path, mode=mode)

    def resolve_input_file(self, path: str) -> Path:
        """校验并确认输入文件存在。

        注意区分两类错误：**越权**（``PathNotAllowedError``）与**文件缺失**
        （``SkillExecutionError``）。把"文件不存在"报成权限问题会误导用户
        去翻白名单设置，方向完全错了。
        """
        resolved = self.resolve_path(path, mode="read")
        if not resolved.is_file():
            raise SkillExecutionError(f"文件不存在：{resolved}")
        return resolved

    def artifact_output(self, filename: str) -> Path:
        """为产物生成一个安全的、不冲突的输出路径。

        只取文件名部分（丢弃模型可能给出的任何目录），并在重名时追加序号，
        避免后一次生成的图表把前一次覆盖掉。
        """
        safe_name = Path(filename).name.strip() or "output"
        # 去掉 Windows 保留字符
        for char in '<>:"/\\|?*':
            safe_name = safe_name.replace(char, "_")
        if not safe_name.strip("._"):
            safe_name = "output"

        target = self.artifacts_dir / safe_name
        stem, suffix = target.stem, target.suffix
        index = 1
        while target.exists():
            target = self.artifacts_dir / f"{stem}({index}){suffix}"
            index += 1
        return target

    def service(self, name: str) -> Any:
        """取出注入的服务（仓储等）。

        取不到时给出明确原因，而不是让技能抛出 ``'NoneType' has no attribute``
        这种让人摸不着头脑的错误——最常见的原因是数据库没就绪。
        """
        value = self.extra.get(name)
        if value is None:
            raise SkillExecutionError(
                f"技能依赖的服务「{name}」当前不可用。可能原因是数据库未就绪（当前为内存模式），"
                f"请检查应用日志。"
            )
        return value

    async def register_artifact(self, path: Path, note: str | None = None) -> dict[str, Any]:
        """把产物登记进工作区（供前端「工作区与产物」页签展示与预览）。"""
        if self.workspace is None:
            return {"id": path.name, "path": str(path)}
        try:
            record = await self.workspace.register_artifact(
                path, note=note, session_id=self.session_id
            )
            return record.to_dict()
        except Exception as exc:  # noqa: BLE001 - 登记失败不该让产物丢失
            self.logger.warning("产物登记失败 %s: %s", path, exc)
            return {"id": path.name, "path": str(path)}


class BaseSkill:
    """所有 Skill 的基类。"""

    meta: SkillMeta

    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        raise NotImplementedError

    # 可选钩子
    async def before_run(self, ctx: SkillContext, **params: Any) -> None:
        return None

    async def after_run(self, ctx: SkillContext, result: Any) -> None:
        return None


# 便利再导出：Skill 作者通常从本模块导入，无需关心这些类型的物理位置
__all__ = [
    "TERMINATION_MARKER",
    "AuditCallback",
    "BaseSkill",
    "ConfirmCallback",
    "ConfirmRequest",
    "InteractionCallback",
    "InteractionRequest",
    "SkillContext",
    "SkillMeta",
    "mark_terminate",
    "wants_terminate",
]
