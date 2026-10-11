"""权限守卫。

对应《智能体框架开发文档》10.2 节。设计要点：
``confirm`` 级 Skill 在无交互环境（如无确认通道）**默认拒绝执行**，
绝不静默执行。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from ..errors import SkillPermissionError
from ..llm.base import ToolSpec
from .confirm import ConfirmRequest

if TYPE_CHECKING:  # 仅类型标注需要，避免与 skill 包形成循环导入
    from ..skill.base import SkillContext, SkillMeta

logger = logging.getLogger(__name__)

VALID_LEVELS = {"safe", "confirm", "admin"}
VALID_MODES = {"interactive", "deny", "auto_approve"}


class PermissionGuard:
    def __init__(
        self,
        *,
        confirm_mode: str = "interactive",
        overrides: dict[str, str] | None = None,
        allow_admin: bool = False,
    ) -> None:
        self._confirm_mode = confirm_mode if confirm_mode in VALID_MODES else "interactive"
        self._overrides = overrides or {}
        self._allow_admin = allow_admin

    @property
    def confirm_mode(self) -> str:
        return self._confirm_mode

    def set_confirm_mode(self, mode: str) -> None:
        if mode in VALID_MODES:
            self._confirm_mode = mode

    def set_overrides(self, overrides: dict[str, str]) -> None:
        self._overrides = {
            k: v for k, v in overrides.items() if v in VALID_LEVELS
        }

    # ------------------------------------------------------------------ #
    # 权限级别解析：配置覆盖 > 元数据默认
    # ------------------------------------------------------------------ #
    def resolve_level(self, meta: SkillMeta) -> str:
        level = self._overrides.get(meta.name, meta.permission_level)
        return level if level in VALID_LEVELS else "safe"

    def needs_confirm(self, meta: SkillMeta) -> bool:
        return self.resolve_level(meta) in ("confirm", "admin")

    def effective_mode(self, ctx: SkillContext | None = None) -> str:
        """当前生效的确认模式。

        助手预设可以给单个会话指定专属策略，优先级高于全局设置。
        这种覆盖**必须放在 ctx 上**而不是改 guard 自身：guard 是全局共享的，
        按会话改它会让并发会话互相串味（A 会话设成"一律拒绝"，
        B 会话的高危操作也跟着被拒）。

        ``ctx.confirm_mode`` 允许是**惰性提供者**（``Callable[[], str | None]``）：
        调用方传"按 id 重读当前配置"的闭包，于是任务跑到一半时用户改了搭子的
        权限策略，**后续工具调用立刻按新策略走**，而不是等下一次任务
        （用户反馈：改完要等下一个任务才生效）。

        合法性校验只留在这里一处 —— 闭包给回什么值，都由这里收敛。
        """
        override = getattr(ctx, "confirm_mode", None)
        if callable(override):
            try:
                override = override()
            except Exception as exc:  # noqa: BLE001
                # 读配置失败不该让工具调用直接崩：退回全局策略，并把原因留在日志里
                logger.warning("读取会话级权限模式失败，按全局策略处理: %s", exc)
                override = None
        return override if override in VALID_MODES else self._confirm_mode

    def allow_admin(self, ctx: SkillContext | None = None) -> bool:
        """本次调用是否放开 admin（高危）级。

        放开有**两个**互不相干的来源：

        - ``self._allow_admin``：**进程级**。建守卫时定死（生产里写死 ``False``，
          表示"前台不放开"）。生效范围是全部会话，所以它只用于整体受信的环境。
        - ``ctx.allow_admin``：**按次**。给"这一次调用"开绿灯 —— 目前只有定时任务
          在用（无人值守的后台任务没人能点「允许」，见 ``agent/scheduler.py``）。

        按次开绿灯必须放在 ctx 上，理由与 ``effective_mode`` 的会话级覆盖完全一样：
        guard 是全局共享的，在那上面按任务改开关会让并发会话互相串味。
        """
        return self._allow_admin or bool(getattr(ctx, "allow_admin", False))

    # ------------------------------------------------------------------ #
    # 校验
    # ------------------------------------------------------------------ #
    @staticmethod
    def _with_command_preview(meta: SkillMeta, params: dict) -> dict:
        """给确认卡补一行"实际会执行的那条命令"（只有命令型自定义技能有）。

        ⚠️ 这件事**必须**在这里做：命令是模板 + 模型给的参数渲染出来的，确认卡原本
        只列参数值，用户根本看不出 ``{host}`` 被填成了什么 —— 而"让用户看清将要发生
        什么"正是确认卡存在的全部理由（见 ``skill/custom.py`` 的 `command_preview`）。

        预览失败**绝不能**挡掉确认流程本身：拿不到预览就照原样确认，
        总好过让一个纯展示性问题把技能彻底锁死。
        """
        preview = getattr(meta, "command_preview", None)
        if not callable(preview):
            return params
        try:
            rendered = str(preview(dict(params)))
        except Exception:  # noqa: BLE001 - 见 docstring
            logger.warning("生成命令预览失败，确认卡将只显示参数：%s", meta.name)
            return params
        if not rendered.strip():
            return params
        return {**params, "将执行的命令": rendered}

    async def check(self, meta: SkillMeta, params: dict, ctx: SkillContext) -> None:
        level = self.resolve_level(meta)

        if level == "safe":
            return

        allow_admin = self.allow_admin(ctx)

        if level == "admin" and not allow_admin:
            raise SkillPermissionError(
                f"Skill「{meta.name}」属于高危操作（admin），当前未开启该级别能力，已拒绝执行。"
            )

        mode = self.effective_mode(ctx)

        if mode == "deny":
            raise SkillPermissionError(
                f"Skill「{meta.name}」需要人工确认，但当前确认模式为「一律拒绝」。"
            )

        # admin 级只在**本次调用显式放开**时才跟着自动批准。前台没放开 admin 时
        # 早已被上面那一步拦下，所以这条不会变成"高危操作的后门"；而没人能点确认的
        # 场合（定时任务）必须真能跑起来，否则"不管什么技能都自动批准"就落不了地。
        if mode == "auto_approve" and (level == "confirm" or allow_admin):
            logger.warning("自动批准执行 %s 级 Skill: %s", level, meta.name)
            return

        # 无确认通道时必须明确报"没有通道"而不是"用户拒绝了"，
        # 否则用户会以为是自己的操作被拒，排查方向完全错误。
        if not getattr(ctx, "has_confirm_channel", False):
            raise SkillPermissionError(
                f"Skill「{meta.name}」需要人工确认，但当前没有可用的确认通道，已拒绝执行。"
            )

        request = ConfirmRequest(
            request_id=uuid.uuid4().hex[:12],
            skill_name=meta.name,
            display_name=meta.display_name or meta.name,
            description=meta.description,
            permission_level=level,
            params=self._with_command_preview(meta, params),
            prompt=f"即将执行「{meta.display_name or meta.name}」，是否继续？",
        )
        approved = await ctx.ask_confirm(request)
        if not approved:
            raise SkillPermissionError(f"用户拒绝了「{meta.name}」的执行请求。")

    # ------------------------------------------------------------------ #
    # 过滤工具列表
    # ------------------------------------------------------------------ #
    def filter_specs(self, metas: list[SkillMeta]) -> list[ToolSpec]:
        """把已启用的 Skill 元数据转成模型工具定义。

        注意：``confirm`` 级 Skill **仍然要暴露给模型**，否则模型无法提出
        需要确认的操作。拦截发生在执行时的 ``check()``。
        """
        return [
            ToolSpec(
                name=m.name,
                description=m.description,
                parameters=m.parameters or {"type": "object", "properties": {}},
            )
            for m in metas
        ]
