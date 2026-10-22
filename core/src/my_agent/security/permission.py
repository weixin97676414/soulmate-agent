






from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from ..errors import SkillPermissionError
from ..llm.base import ToolSpec
from .confirm import ConfirmRequest

if TYPE_CHECKING:  
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

    
    
    
    def resolve_level(self, meta: SkillMeta) -> str:
        level = self._overrides.get(meta.name, meta.permission_level)
        return level if level in VALID_LEVELS else "safe"

    def needs_confirm(self, meta: SkillMeta) -> bool:
        return self.resolve_level(meta) in ("confirm", "admin")

    def effective_mode(self, ctx: SkillContext | None = None) -> str:














        override = getattr(ctx, "confirm_mode", None)
        if callable(override):
            try:
                override = override()
            except Exception as exc:  
                
                logger.warning("读取会话级权限模式失败，按全局策略处理: %s", exc)
                override = None
        return override if override in VALID_MODES else self._confirm_mode

    def allow_admin(self, ctx: SkillContext | None = None) -> bool:












        return self._allow_admin or bool(getattr(ctx, "allow_admin", False))

    
    
    
    @staticmethod
    def _with_command_preview(meta: SkillMeta, params: dict) -> dict:









        preview = getattr(meta, "command_preview", None)
        if not callable(preview):
            return params
        try:
            rendered = str(preview(dict(params)))
        except Exception:  
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

        
        
        
        if mode == "auto_approve" and (level == "confirm" or allow_admin):
            logger.warning("自动批准执行 %s 级 Skill: %s", level, meta.name)
            return

        
        
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

    
    
    
    def filter_specs(self, metas: list[SkillMeta]) -> list[ToolSpec]:





        return [
            ToolSpec(
                name=m.name,
                description=m.description,
                parameters=m.parameters or {"type": "object", "properties": {}},
            )
            for m in metas
        ]
