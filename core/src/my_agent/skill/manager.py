"""SkillManager：统一的注册、查找与执行入口。

对应《智能体框架开发文档》5.3 节。Agent 层只面对 ``SkillManager``，
不感知某个能力是内置函数、MCP 工具还是 HTTP 接口。
"""

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
    """把 Skill 返回值转成可回填给模型的文本。

    dict / list 用 JSON 序列化（模型对 JSON 的解析最稳定）；
    字符串原样返回；其余走 ``str()``。
    """
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def _forbidden_for(assistant_id: str | None, names: Iterable[str]) -> frozenset[str]:
    """该搭子**不该看见**的技能名（专属技能隔离）。

    判定集中在 ``skill/groups.py``，它把两处来源合并成一句：
    ① 心鉴学那两个配套工具（既有的按归属隔离）；
    ② **归属别人的专属技能**（搭子总管的团队管理与电脑操作那批）。
    两者对非归属搭子都该"压根不存在"——不是"调了会报错"。

    ``names`` 传当前注册表的全部技能名（专属判定得先知道有哪些技能）。
    **刻意用函数内导入**：``skill.manager`` 在启动早期就被导入
    （``server/runtime.py``），把它依赖的模块提到顶层会让两边的导入顺序
    互相牵制，将来谁加一行 import 都可能成环。
    """
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
        # 权限变更的外部通知。MCP 技能靠它把新权限**写回配置**：
        # 配置是权限的唯一真相来源，不落盘的话下一次 sync_skills 会拿旧值覆盖回来，
        # 用户看到的是"改完生效了，过一会儿又变回来"。
        self._on_permission_change = on_permission_change

    def set_permission_listener(
        self, callback: Callable[[BaseSkill, str], None] | None
    ) -> None:
        """注册权限变更回调（运行时在 MCP 管理器就绪后调用）。"""
        self._on_permission_change = callback

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #
    def register(self, target: type[BaseSkill] | BaseSkill) -> BaseSkill:
        instance = target() if isinstance(target, type) else target
        class_meta = getattr(type(instance), "meta", None)
        if class_meta is None:
            raise ValueError(
                f"{type(instance).__name__} 缺少 meta，请确认已加 @skill 装饰器。"
            )
        # 元数据定义在类上（供 discover_builtin_skills 识别），但启用状态与权限
        # 是**实例级**的可变状态。直接复用类属性会让"禁用一个 Skill"污染所有实例，
        # 因此在这里做一次深拷贝，把可变状态钉在实例上。
        instance.meta = copy.deepcopy(class_meta)

        name = instance.meta.name
        # 永久开启 + 免批准：在**注册时**按分组盖章，而不是让每个技能自己在
        # 装饰器里写一遍 —— 判定是唯一真相来源，漏写一个的后果是
        # "这一个偷偷能被关掉"，而且没人会发现。
        #
        # 现在锁的是三类（见 `skill/groups.py::is_locked`）：
        #   ① 内置技能（每个搭子创建即自带的基础能力）
        #   ② 专属技能（只有归属搭子能用，用户与 AI 都不该关掉它）
        #   ③ 原有硬锁名单（`skill/locked.py::ALWAYS_ON_SKILLS`，含心鉴学配套工具）
        #
        # 只对内置来源生效：MCP 工具的权限本来就由用户在 MCP 页里管，
        # 万一有个同名工具（`namespaced_name` 会加前缀，实际很难撞上），
        # 也不该被这份名单锁住。
        from . import groups as skill_groups  # 函数内导入，理由见 _forbidden_for

        if skill_groups.is_locked(name, instance.meta.source):
            instance.meta.locked = True
            # 顺手把启用状态与权限**拉回**默认：万一将来有人给锁定技能加了
            # `enabled=False` 的默认值，这里也兜得住
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

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
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
        """``{技能名: source}`` —— 四分类判定与装配都要它。"""
        return {name: skill.meta.source for name, skill in self._skills.items()}

    def allowed_names(
        self,
        *,
        assistant_id: str | None,
        enabled_skills: Iterable[str] | None,
    ) -> set[str]:
        """这个搭子**实际可用**的技能名集合（**永不为空、永不返回 None**）。

        语义见 ``skill/groups.py``：

        - **内置搭子**（id 在 `LOCKED_ASSISTANT_IDS` 里）= 全部内置技能 ∪ 自己的专属技能，
          并**忽略** ``enabled_skills``（那个字段同时被 locked_builtins 锁着，
          用户与 AI 都改不了）；
        - **自定义搭子** = 全部内置技能 ∪ 勾选的「通用技能 + 我的技能」；
          不勾就只有内置技能。

        ⚠️ 顺手补上 ``requires`` 依赖闭包：旧实现是"暴露时补依赖、执行时不补"，
        于是声明了依赖的技能会被暴露、却在执行时被拒（用户看到的是"这功能坏了"）。
        """
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
        """把 ``requires`` 声明的依赖补进名字集合。

        ``requires`` 在此之前只是个没人读的字段。不补齐依赖的后果不是启动报错，
        而是**工具在调用时才失败**——用户看到"这个功能用不了"却完全不知道为什么。

        用 ``result`` 做已访问集合，所以技能之间互相依赖也不会死循环。
        """
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
        """给模型看的工具清单。

        ``for_assistant`` 是"这份清单要交给哪个搭子"。有些技能是**某个搭子的
        专属能力**（心鉴学那套，见 ``skill/builtin/xjx.py``），对别的搭子应当
        压根不存在 —— 不是"调了会报错"，而是"看不见"：模型把"看得见"直接理解
        成"可以用"，留一个多余的工具只会诱导它去调。

        ⚠️ 这道排除必须在 ``filter_names``（搭子档案里的白名单）**之前**做。
        反过来先按白名单捞一遍，一个白名单非空、但没写专属技能的搭子里，
        照样会混进别人的专属工具 —— 而"顺序反了"这种错不会有任何报错提示。
        """
        metas = self.list_metas()
        excluded = _forbidden_for(for_assistant, self._skills)
        if excluded:
            metas = [m for m in metas if m.name not in excluded]
        if filter_names is not None:
            # 先把依赖补齐再过滤：只把"用户勾选的功能"给模型、却不给它的依赖，
            # 等于给模型一个调用必失败的工具
            allowed = self.requires_closure(filter_names)
            metas = [m for m in metas if m.name in allowed]
        return self._guard.filter_specs(metas)

    def set_enabled(self, name: str, enabled: bool) -> SkillMeta:
        """启用 / 停用技能。**被硬锁的技能关不掉**（见 locked.py）。

        `set_enabled(name, True)` 对锁定技能是放行的（幂等），
        只有"关掉"才拒绝 —— 否则任何一次"全量重建技能列表"都会在这里炸掉。
        """
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
        """设置权限级别。**被硬锁的技能改不了权限**（它们固定为免批准）。"""
        skill = self.get(name)
        if skill.meta.locked:
            logger.warning("拒绝修改永久开启技能的权限：%s → %s", name, level)
            raise SkillPermissionError(locked_message(skill.meta.display_name or name))
        skill.meta.permission_level = level
        if self._on_permission_change is not None:
            # 回调不该有能力把"设置权限"这个操作弄失败 —— 内存里的值已经改好了，
            # 落盘是附加动作，它出问题最多是这次改动不持久，不该抛给调用方
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

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        ctx: SkillContext,
        *,
        within: set[str] | None = None,
        for_assistant: str | None = None,
    ) -> str:
        """执行 Skill 并返回可回填给模型的文本。

        异常策略（对齐文档 7.3 节）：执行类异常由上层 Agent 捕获并回填给模型；
        仅 ``SkillPermissionError`` 需要用类型区分，因为 Agent 要在卡片上标记
        「被拒绝」而不是「失败」。

        每次执行（无论成功、失败还是被拒）都会写一条审计记录，
        对应开发文档 10.5 节「高危操作审计必须完整」的要求。

        ``within`` 是"本次会话允许使用的技能集合"。**必须在这里真正拦住**：
        "没暴露给模型"和"不能执行"是两件事 —— 模型完全可能凭历史消息或
        幻觉发出一个对已禁用工具的调用，而工具照样会被执行。

        ``for_assistant`` 是同一件事的另一半（专属技能隔离）：清单里没用这个
        参数滤掉、这里也没拦的话，模型凭历史消息里见过的名字照样能调别人的
        专属工具。"没给它看"和"用不了"缺一不可。
        """
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

        # ---- 1) 权限校验（可能触发人工确认，耗时较长） ---------------- #
        try:
            await self._guard.check(meta, validated, ctx)
        except SkillPermissionError as exc:
            await self._audit(ctx, meta, validated, "denied", started, str(exc))
            raise

        # ---- 2) 执行，带超时与追踪 ----------------------------------- #
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
            # 确认环节在 _run_with_timeout 之外，正常不会到这里；保险起见仍处理
            await self._audit(ctx, meta, validated, "denied", started, str(exc))
            raise
        except SkillTimeoutError as exc:
            await self._audit(ctx, meta, validated, "timeout", started, exc.message)
            raise
        except SkillError as exc:
            # PathNotAllowedError 这类**预期内的业务异常**原样抛出：
            # 它们已经带有清晰的用户可读信息（例如"不允许访问白名单之外的路径"），
            # 再包一层 SkillExecutionError 只会把错误类型信息丢掉，
            # 让上层无法区分"权限问题"和"代码 bug"。
            status = "error"
            await self._audit(ctx, meta, validated, status, started, exc.message)
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包成业务异常
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
        """写审计记录。审计失败绝不能影响工具本身的结果。"""
        # 埋点放在这里而不是各分支：``_audit`` 是**所有结局**
        # （ok / denied / timeout / error）唯一的汇合点，漏掉某个分支的可能性最小。
        # 它必须在 ctx.audit 的提前返回**之前** —— 没接审计通道时（例如
        # SDK 直接调用）指标同样应该正常统计。
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
        except Exception:  # noqa: BLE001
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
