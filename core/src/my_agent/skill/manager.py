





from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from pydantic import ValidationError

from ..errors import (
    SkillError,
    SkillExecutionError,
    SkillNotFoundError,
    SkillPermissionError,
    SkillTimeoutError,
    SkillValidationError,
)
from ..llm.base import ToolSpec
from ..observability.metrics import METRICS
from ..security.audit import AuditEntry
from ..security.permission import PermissionGuard
from .base import BaseSkill, SkillContext, SkillMeta
from .locked import locked_message

logger = logging.getLogger(__name__)


def stringify_result(result: Any) -> str:





    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def _forbidden_for(assistant_id: str | None, names: Iterable[str]) -> frozenset[str]:












    from . import groups

    return groups.forbidden_names(names, assistant_id)


class SkillManager:
    def __init__(
        self,
        guard: PermissionGuard | None = None,
        on_permission_change: Callable[[BaseSkill, str], None] | None = None,
    ) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._guard = guard or PermissionGuard()
        
        
        
        self._on_permission_change = on_permission_change

    def set_permission_listener(
        self, callback: Callable[[BaseSkill, str], None] | None
    ) -> None:

        self._on_permission_change = callback

    
    
    
    def register(self, target: type[BaseSkill] | BaseSkill) -> BaseSkill:
        instance = target() if isinstance(target, type) else target
        class_meta = getattr(type(instance), "meta", None)
        if class_meta is None:
            raise ValueError(
                f"{type(instance).__name__} 缺少 meta，请确认已加 @skill 装饰器。"
            )
        
        
        
        instance.meta = copy.deepcopy(class_meta)

        name = instance.meta.name
        
        
        
        
        
        
        
        
        
        
        
        
        from . import groups as skill_groups  

        if skill_groups.is_locked(name, instance.meta.source):
            instance.meta.locked = True
            
            
            instance.meta.enabled = True

        if name in self._skills:
            logger.warning("Skill 名称冲突，已覆盖: %s", name)
        self._skills[name] = instance
        return instance

    def unregister(self, name: str) -> bool:
        return self._skills.pop(name, None) is not None

    def clear(self, *, source: str | None = None) -> None:
        if source is None:
            self._skills.clear()
            return
        for name in [n for n, s in self._skills.items() if s.meta.source == source]:
            del self._skills[name]

    
    
    
    def get(self, name: str) -> BaseSkill:
        skill = self._skills.get(name)
        if skill is None:
            available = ", ".join(sorted(self._skills)) or "(无)"
            raise SkillNotFoundError(f"工具 {name} 不存在。当前可用工具：{available}")
        return skill

    def has(self, name: str) -> bool:
        return name in self._skills

    def list_metas(self, *, enabled_only: bool = True) -> list[SkillMeta]:
        metas = [s.meta for s in self._skills.values()]
        if enabled_only:
            metas = [m for m in metas if m.enabled]
        return sorted(metas, key=lambda m: (m.category, m.name))

    def all_names(self) -> list[str]:
        return sorted(self._skills)

    def source_map(self) -> dict[str, str]:

        return {name: skill.meta.source for name, skill in self._skills.items()}

    def allowed_names(
        self,
        *,
        assistant_id: str | None,
        enabled_skills: Iterable[str] | None,
    ) -> set[str]:













        from ..assistants.locked_builtins import is_locked_assistant
        from . import groups

        allowed = groups.allowed_skill_names(
            self.source_map(),
            assistant_id=assistant_id,
            enabled_skills=enabled_skills,
            builtin_assistant=is_locked_assistant(assistant_id),
        )
        return self.requires_closure(allowed)

    def requires_closure(self, names: set[str]) -> set[str]:







        result = set(names)
        pending = list(names)
        while pending:
            name = pending.pop()
            skill = self._skills.get(name)
            if skill is None:
                continue
            for dependency in skill.meta.requires:
                if dependency in result:
                    continue
                if dependency not in self._skills:
                    logger.warning("技能 %s 依赖的 %s 不存在，已跳过", name, dependency)
                    continue
                result.add(dependency)
                pending.append(dependency)
        return result

    def to_tool_specs(
        self,
        *,
        filter_names: set[str] | None = None,
        for_assistant: str | None = None,
    ) -> list[ToolSpec]:











        metas = self.list_metas()
        excluded = _forbidden_for(for_assistant, self._skills)
        if excluded:
            metas = [m for m in metas if m.name not in excluded]
        if filter_names is not None:
            
            
            allowed = self.requires_closure(filter_names)
            metas = [m for m in metas if m.name in allowed]
        return self._guard.filter_specs(metas)

    def set_enabled(self, name: str, enabled: bool) -> SkillMeta:





        skill = self.get(name)
        if skill.meta.locked:
            if enabled:
                skill.meta.enabled = True
                return skill.meta
            logger.warning("拒绝停用永久开启的技能：%s", name)
            raise SkillPermissionError(locked_message(skill.meta.display_name or name))
        skill.meta.enabled = enabled
        return skill.meta

    def set_permission(self, name: str, level: str) -> SkillMeta:

        skill = self.get(name)
        if skill.meta.locked:
            logger.warning("拒绝修改永久开启技能的权限：%s → %s", name, level)
            raise SkillPermissionError(locked_message(skill.meta.display_name or name))
        skill.meta.permission_level = level
        if self._on_permission_change is not None:
            
            
            with contextlib.suppress(Exception):
                self._on_permission_change(skill, level)
        return skill.meta

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        self._guard.set_overrides(overrides)

    @property
    def guard(self) -> PermissionGuard:
        return self._guard

    def __len__(self) -> int:
        return len(self._skills)

    
    
    
    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        ctx: SkillContext,
        *,
        within: set[str] | None = None,
        for_assistant: str | None = None,
    ) -> str:

















        skill = self.get(name)
        meta = skill.meta

        if not meta.enabled:
            message = f"工具 {name} 已被禁用，无法执行。"
            await self._audit(ctx, meta, params or {}, "denied", time.perf_counter(), message)
            raise SkillPermissionError(message)
        if name in _forbidden_for(for_assistant, self._skills):
            message = f"工具 {name} 不适用于当前搭子，无法执行。"
            await self._audit(ctx, meta, params or {}, "denied", time.perf_counter(), message)
            raise SkillPermissionError(message)
        if within is not None and name not in within:
            message = f"工具 {name} 不在当前会话启用的技能范围内，无法执行。"
            await self._audit(ctx, meta, params or {}, "denied", time.perf_counter(), message)
            raise SkillPermissionError(message)

        validated = self._validate(skill, params)
        started = time.perf_counter()

        
        try:
            await self._guard.check(meta, validated, ctx)
        except SkillPermissionError as exc:
            await self._audit(ctx, meta, validated, "denied", started, str(exc))
            raise

        
        span_cm = ctx.tracer.span(f"skill:{name}", category=meta.category) if ctx.tracer else None
        try:
            if span_cm is not None:
                with span_cm as span:
                    span.event("start", params=validated)
                    result = await self._run_with_timeout(skill, ctx, validated)
                    span.event("finish")
            else:
                result = await self._run_with_timeout(skill, ctx, validated)
        except asyncio.CancelledError:
            await self._audit(ctx, meta, validated, "error", started, "任务被中断")
            raise
        except SkillPermissionError as exc:
            
            await self._audit(ctx, meta, validated, "denied", started, str(exc))
            raise
        except SkillTimeoutError as exc:
            await self._audit(ctx, meta, validated, "timeout", started, exc.message)
            raise
        except SkillError as exc:
            
            
            
            
            status = "error"
            await self._audit(ctx, meta, validated, status, started, exc.message)
            raise
        except Exception as exc:  
            logger.exception("Skill %s 执行失败", name)
            message = f"工具 {name} 执行出错：{type(exc).__name__}: {exc}"
            await self._audit(ctx, meta, validated, "error", started, message)
            raise SkillExecutionError(message) from exc

        await self._audit(ctx, meta, validated, "ok", started, None)
        return stringify_result(result)

    async def _audit(
        self,
        ctx: SkillContext,
        meta: SkillMeta,
        params: dict[str, Any],
        status: str,
        started: float,
        detail: str | None,
    ) -> None:

        
        
        
        
        METRICS.inc(
            "skill_calls_total",
            skill=meta.name,
            status=status,
            category=meta.category,
        )
        METRICS.observe(
            "skill_duration_ms",
            (time.perf_counter() - started) * 1000,
            skill=meta.name,
        )

        if ctx.audit is None:
            return
        try:
            await ctx.audit(
                AuditEntry(
                    skill_name=meta.name,
                    status=status,
                    permission_level=self._guard.resolve_level(meta),
                    session_id=ctx.session_id,
                    params=params or None,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    detail=detail,
                )
            )
        except Exception:  
            logger.exception("审计写入失败: %s", meta.name)

    async def _run_with_timeout(
        self, skill: BaseSkill, ctx: SkillContext, params: dict[str, Any]
    ) -> Any:
        await skill.before_run(ctx, **params)
        try:
            result = await asyncio.wait_for(skill.run(ctx, **params), timeout=skill.meta.timeout)
        except TimeoutError as exc:
            raise SkillTimeoutError(
                f"工具 {skill.meta.name} 执行超时（>{skill.meta.timeout}s）。"
            ) from exc
        await skill.after_run(ctx, result)
        return result

    @staticmethod
    def _validate(skill: BaseSkill, params: dict[str, Any]) -> dict[str, Any]:
        model = getattr(skill, "params_model", None)
        if model is None:
            return params or {}
        try:
            return model.model_validate(params or {}).model_dump()
        except ValidationError as exc:
            issues = "；".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise SkillValidationError(
                f"工具 {skill.meta.name} 的参数不合法 —— {issues}。请修正参数后重试。"
            ) from exc
