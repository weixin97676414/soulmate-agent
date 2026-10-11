"""自动化任务的读写门面。

## 为什么需要单独一层

自动化任务有**两条修改路径**：
1. 界面（``/v1/tasks`` 的增删改）；
2. 搭子自己（内置技能 ``task_create`` / ``task_update`` / ``task_delete``）。

两条路径各自拼配置、各自落盘的话迟早长歪：id 生成规则、字段归一化、
"保存后要重启调度"这三件事只要有一处漏掉，症状都是**静默的**
（任务看起来建好了，但永远不会跑）。所以读写只有这一份实现，
HTTP 路由与技能都走它。

## 运行期状态不在这里

条件基线（网页摘要 / 文件 mtime）在 ``TaskScheduler`` 的内存里，不落盘 ——
理由见 ``scheduler.py`` 的模块说明。这里只管**配置**那一半。

⚠️ 但 ``describe()`` 里的 ``last_run_at`` 现在来自**磁盘上的运行状态**
（``<data_dir>/scheduler_state.json``，由调度器自己写，不是配置）——
"关着的时候错过的那一次要不要补跑"必须能跨重启说清，见 ``scheduler.py``
的"重启后补跑一次"。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from ..assistants import locked_builtins
from ..config.schemas import ScheduledTaskSpec
from ..errors import ScheduledTaskNotFoundError

logger = logging.getLogger(__name__)


def locked_for_user(spec: ScheduledTaskSpec) -> bool:
    """这条任务能不能被**用户**在界面上改 / 关 / 删（产品约定）。

    锁的是两类：

    - **我们预置的**（``origin="builtin"``，四条「全员进化中 X」）；
    - **这四个内置搭子自己建的**（``origin="agent"`` 且执行者是它们）。

    不锁的：用户自己手工建的（``origin="user"``，哪怕指定内置搭子跑）、
    以及任何属于**其他搭子**的任务（自建搭子的任务一律不锁）。

    ## ⚠️ 这个函数只许在 HTTP 路由层调用

    搭子改任务走的是 ``ScheduledTaskStore.update/delete``（技能直连，**不经过路由**）。
    把这条判断塞进 update/delete 的话，"用户不能改、搭子能改"这条设计会整个废掉 ——
    搭子自己也会被拒，而症状只是"它说改了其实没改"，几乎查不出来。
    **这是故意的分工，不是漏写。**
    """
    return spec.origin != "user" and spec.assistant_id in locked_builtins.LOCKED_ASSISTANT_IDS


_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def new_task_id() -> str:
    """生成任务 id。

    用随机短 id 而不是"按名字生成"：名字是用户随时会改的显示字段，
    拿它当主键会让"改个名字"变成"换了一个任务"（计时清零、条件基线丢失）。
    """
    return f"task-{uuid.uuid4().hex[:8]}"


def human_start_at(raw: str) -> str:
    """"2026-09-30T09:00" → "2026年9月30日 09:00"（读不出来就返回空串）。

    起始时间的显示口径与 ``describe_schedule`` 一样只有这一份：界面、技能、
    日志三处各自格式化的话，同一件事会写出三种样子。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        moment = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        return ""
    return f"{moment.year}年{moment.month}月{moment.day}日 {moment.hour:02d}:{moment.minute:02d}"


def describe_schedule(spec: ScheduledTaskSpec) -> str:
    """把触发方式与条件渲染成一句人话。

    界面与技能都要用同一句话术：两边各写一份的话，用户看到的和模型转述的
    会对不上（"界面写每天 9 点、它却说每小时一次"），那种不一致极难排查。
    """
    if spec.trigger == "daily":
        base = f"每天 {spec.at_time}"
    elif spec.trigger == "weekly":
        base = f"每{_WEEKDAYS[spec.weekday]} {spec.at_time}"
    elif spec.interval_minutes < 60:
        base = f"每 {spec.interval_minutes} 分钟"
    elif spec.interval_minutes % 60 == 0:
        base = f"每 {spec.interval_minutes // 60} 小时"
    else:
        base = f"每 {spec.interval_minutes} 分钟"

    # 间隔型的起始时间：不写出来的话，"为什么现在还不跑"在界面上完全没有线索 ——
    # 用户只会看到一条"每 2 小时"的任务安安静静地不动
    if spec.trigger == "interval":
        start = human_start_at(spec.start_at)
        if start:
            base = f"自 {start} 起，{base}"

    if spec.condition == "url_changed":
        base += f"（仅当 {spec.condition_target} 的内容有变化时执行）"
    elif spec.condition == "file_changed":
        base += f"（仅当 {spec.condition_target} 有更新时执行）"
    return base


class ScheduledTaskStore:
    """自动化任务配置的增删改查。"""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    # ------------------------------------------------------------------ #
    # 读
    # ------------------------------------------------------------------ #
    def list(self) -> list[ScheduledTaskSpec]:
        return list(self._runtime.config.settings.agent.scheduled_tasks or [])

    def describe(self, spec: ScheduledTaskSpec) -> str:
        """把触发方式渲染成人话。

        技能是通过 ``ctx.service("tasks")`` 拿到这个门面的，所以这里再包一层 ——
        技能若自己去 import 这个函数，就等于让"界面话术与模型话术"有了两条来路。
        """
        return describe_schedule(spec)

    def get(self, task_id: str) -> ScheduledTaskSpec:
        found = next((item for item in self.list() if item.id == task_id), None)
        if found is None:
            raise ScheduledTaskNotFoundError(
                f"没有找到自动化任务「{task_id}」。", detail=task_id
            )
        return found

    # ------------------------------------------------------------------ #
    # 写
    # ------------------------------------------------------------------ #
    async def create(self, **fields: Any) -> ScheduledTaskSpec:
        """新建任务。``fields`` 与 ``ScheduledTaskSpec`` 的字段同名。"""
        raw = {"id": fields.pop("id", "") or new_task_id(), **fields}
        spec = ScheduledTaskSpec.model_validate(raw)
        await self._save([*self.list(), spec])
        logger.info("已新建自动化任务 %s（%s）", spec.id, spec.name)
        return spec

    async def update(self, task_id: str, **changes: Any) -> ScheduledTaskSpec:
        """局部更新：只覆盖传进来的字段，其余保持原值。

        局部而不是整体替换，是因为技能那边的调用者只想改一件事
        （"把时间改成早上八点"），让它先把整份配置读出来再写回去，
        中间任何一次并发修改都会被它覆盖掉。
        """
        current = self.get(task_id)
        payload = {**current.model_dump(), **{k: v for k, v in changes.items() if v is not None}}
        # id 不允许被改：它是"这个任务"的身份，也是计时与基线的键
        payload["id"] = current.id
        spec = ScheduledTaskSpec.model_validate(payload)
        await self._save(
            [spec if item.id == task_id else item for item in self.list()]
        )
        logger.info("已更新自动化任务 %s（%s）", spec.id, spec.name)
        return spec

    async def delete(self, task_id: str) -> ScheduledTaskSpec:
        current = self.get(task_id)
        remaining = [item for item in self.list() if item.id != task_id]
        await self._save(remaining)
        logger.info("已删除自动化任务 %s（%s）", current.id, current.name)
        return current

    async def set_enabled(self, task_id: str, enabled: bool) -> ScheduledTaskSpec:
        return await self.update(task_id, enabled=enabled)

    async def run_now(self, task_id: str) -> bool:
        """立刻跑一次（转发给调度器：是否已在执行只有它知道）。"""
        return await self._runtime.task_scheduler.run_now(task_id)

    async def _save(self, specs: list[ScheduledTaskSpec]) -> None:
        await self._runtime.save_scheduled_tasks(specs)
