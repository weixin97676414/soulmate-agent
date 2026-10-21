
















from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ...errors import ScheduledTaskNotFoundError, SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill



_PROMPT_ECHO = 200


class TaskListParams(BaseModel):
    include_disabled: bool = Field(True, description="是否把已停用的任务也列出来")


@skill(
    name="scheduled_task_list",
    display_name="查看自动化任务",
    description=(
        "列出已创建的自动化任务（含触发时间与条件、上次执行时间、是否在用）。"
        "当用户问「我设了哪些自动化任务」「那个每天的任务还在吗」时使用。"
    ),
    params_model=TaskListParams,
    category="system",
    permission_level="safe",
    tags=["自动化任务", "自动化"],
)
class ScheduledTaskListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TaskListParams(**params)
        store = ctx.service("tasks")

        items = []
        for spec in store.list():
            if not spec.enabled and not args.include_disabled:
                continue
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "enabled": spec.enabled,
                    "schedule": store.describe(spec),
                    "trigger": spec.trigger,
                    "interval_minutes": spec.interval_minutes,
                    "at_time": spec.at_time,
                    "weekday": spec.weekday,
                    "condition": spec.condition,
                    "condition_target": spec.condition_target,
                    "assistant_id": spec.assistant_id,
                    "prompt": spec.prompt,
                    "prompt_preview": spec.prompt[:_PROMPT_ECHO],
                }
            )
        return {
            "count": len(items),
            "tasks": items,
            "message": "还没有自动化任务。" if not items else None,
        }


class TaskCreateParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=48, description="任务名，例如「早报」")
    prompt: str = Field(
        ..., min_length=1, description="每次执行时交给搭子的完整指令（要写具体、可独立完成）"
    )
    trigger: Literal["interval", "daily", "weekly"] = Field(
        "daily",
        description="interval=每隔一段时间；daily=每天；weekly=每周",
    )
    interval_minutes: int = Field(
        60, ge=1, le=43200, description="trigger=interval 时用：间隔分钟数（上限 30 天）"
    )
    at_time: str = Field("09:00", description="trigger=daily/weekly 时用：HH:MM，例如 09:00")
    weekday: int = Field(0, ge=0, le=6, description="trigger=weekly 时用：0=周一 … 6=周日")
    start_at: str = Field(
        "",
        description=(
            "trigger=interval 时用：起始时间，格式 YYYY-MM-DDTHH:MM（本机时间，例如 "
            "2026-09-30T09:03）。从这一刻起每 interval_minutes 分钟跑一次，"
            "到这一刻之前一次都不跑；留空=从现在起算"
        ),
    )
    condition: Literal["none", "url_changed", "file_changed"] = Field(
        "none",
        description=(
            "none=到点就执行；url_changed=网页内容有变化才执行；"
            "file_changed=文件有更新才执行。选了条件就必须填 condition_target"
        ),
    )
    condition_target: str = Field(
        "", description="条件的目标：网页地址（http/https）或本地文件路径"
    )
    assistant_id: str = Field("", description="用哪个搭子跑；留空用当前搭子")
    enabled: bool = Field(True, description="是否立刻启用（默认启用，建好即生效）")


@skill(
    name="scheduled_task_create",
    display_name="新建自动化任务",
    description=(
        "创建一个自动化任务：到点后搭子会自动执行 prompt 里的指令，并在新会话里产出结果。"
        "当用户说「每天早上九点帮我做…」「每小时看一下这个网页有没有变化」"
        "「这个文件更新了就提醒我处理」时使用。"
        "**执行会消耗 token**，所以创建前要把触发时间与条件复述给用户确认。"
    ),
    params_model=TaskCreateParams,
    category="system",
    permission_level="confirm",
    tags=["自动化任务", "自动化"],
)
class ScheduledTaskCreateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TaskCreateParams(**params)
        store = ctx.service("tasks")

        fields = args.model_dump()
        
        if not fields.get("assistant_id"):
            fields["assistant_id"] = ctx.assistant_id or ""
        
        
        
        fields["origin"] = "agent"

        try:
            spec = await store.create(**fields)
        except ValidationError as exc:
            raise SkillExecutionError(f"任务参数不合法：{_first_error(exc)}") from exc

        return {
            "id": spec.id,
            "name": spec.name,
            "enabled": spec.enabled,
            "schedule": store.describe(spec),
            "message": (
                f"已创建自动化任务「{spec.name}」：{store.describe(spec)}。"
                + ("（已启用）" if spec.enabled else "（当前是停用状态，需要时可在自动化任务页打开）")
            ),
        }


class TaskUpdateParams(BaseModel):
    task_id: str = Field(..., min_length=1, description="要修改的任务 id（先用 scheduled_task_list 查）")
    name: str | None = Field(None, max_length=48, description="新名字；不填则不改")
    prompt: str | None = Field(None, description="新的执行指令；不填则不改")
    trigger: Literal["interval", "daily", "weekly"] | None = Field(None, description="新的触发方式")
    interval_minutes: int | None = Field(None, ge=1, le=43200, description="新的间隔分钟数（上限 30 天）")
    at_time: str | None = Field(None, description="新的执行时刻 HH:MM")
    weekday: int | None = Field(None, ge=0, le=6, description="新的星期几（0=周一）")
    start_at: str | None = Field(
        None,
        description="新的起始时间 YYYY-MM-DDTHH:MM（trigger=interval 时用）；传空串表示取消起始时间",
    )
    condition: Literal["none", "url_changed", "file_changed"] | None = Field(
        None, description="新的触发条件"
    )
    condition_target: str | None = Field(None, description="新的条件目标（网址或文件路径）")
    assistant_id: str | None = Field(None, description="换成别的搭子来跑")
    enabled: bool | None = Field(None, description="启用 / 停用")


@skill(
    name="scheduled_task_update",
    display_name="修改自动化任务",
    description=(
        "修改已有自动化任务的名字、时间、条件或开关；**只改传进来的字段**，其余保持不变。"
        "当用户说「把那个任务改到早上八点」「先停掉那个任务」「改成网页变了才跑」时使用。"
        "需要先用 scheduled_task_list 拿到任务 id。"
    ),
    params_model=TaskUpdateParams,
    category="system",
    permission_level="confirm",
    tags=["自动化任务", "自动化"],
)
class ScheduledTaskUpdateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TaskUpdateParams(**params)
        store = ctx.service("tasks")

        changes = {key: value for key, value in args.model_dump().items() if value is not None}
        task_id = changes.pop("task_id")
        if not changes:
            raise SkillExecutionError("没有要修改的内容：请至少给一个要改的字段。")

        try:
            spec = await store.update(task_id, **changes)
        except ScheduledTaskNotFoundError as exc:
            raise SkillExecutionError(exc.message) from exc
        except ValidationError as exc:
            raise SkillExecutionError(f"修改后的参数不合法：{_first_error(exc)}") from exc

        return {
            "id": spec.id,
            "name": spec.name,
            "enabled": spec.enabled,
            "schedule": store.describe(spec),
            "changed": sorted(changes),
            "message": f"已更新任务「{spec.name}」，现在是：{store.describe(spec)}。",
        }


class TaskDeleteParams(BaseModel):
    task_id: str = Field(..., min_length=1, description="要删除的任务 id（先用 scheduled_task_list 查）")


@skill(
    name="scheduled_task_delete",
    display_name="删除自动化任务",
    description=(
        "删除一个自动化任务。当用户说「把那个自动化任务删掉」「不要每天跑了」时使用。"
        "删除前请向用户复述任务名，避免删错 —— 删掉后触发时间与条件基线都会丢失。"
    ),
    params_model=TaskDeleteParams,
    category="system",
    permission_level="confirm",
    tags=["自动化任务", "自动化"],
)
class ScheduledTaskDeleteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TaskDeleteParams(**params)
        store = ctx.service("tasks")

        try:
            spec = await store.delete(args.task_id)
        except ScheduledTaskNotFoundError as exc:
            raise SkillExecutionError(exc.message) from exc

        return {"id": spec.id, "message": f"已删除自动化任务「{spec.name}」。"}


class TaskRunParams(BaseModel):
    task_id: str = Field(..., min_length=1, description="要立刻执行的任务 id")


@skill(
    name="scheduled_task_run",
    display_name="立刻执行自动化任务",
    description=(
        "马上执行一次自动化任务（不等下一个时间点），用于验证任务配得对不对。"
        "当用户说「现在先跑一次看看」「马上执行那个任务」时使用。"
        "它**会立刻消耗 token**，所以只在用户明确要求时调用。"
    ),
    params_model=TaskRunParams,
    category="system",
    permission_level="confirm",
    tags=["自动化任务", "自动化"],
)
class ScheduledTaskRunSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TaskRunParams(**params)
        store = ctx.service("tasks")

        try:
            spec = store.get(args.task_id)
        except ScheduledTaskNotFoundError as exc:
            raise SkillExecutionError(exc.message) from exc

        
        if not await store.run_now(args.task_id):
            raise SkillExecutionError(
                f"任务「{spec.name}」正在执行中，等它跑完再试。"
            )
        return {
            "id": spec.id,
            "message": (
                f"已开始执行「{spec.name}」。它会在一个新会话里跑完，"
                "完成后界面会弹出通知。"
            ),
        }


def _first_error(exc: ValidationError) -> str:





    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    field = ".".join(str(part) for part in first.get("loc", ())) or "参数"
    return f"{field}：{first.get('msg', '不合法')}"
