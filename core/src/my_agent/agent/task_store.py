























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

















    return spec.origin != "user" and spec.assistant_id in locked_builtins.LOCKED_ASSISTANT_IDS


_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def new_task_id() -> str:





    return f"task-{uuid.uuid4().hex[:8]}"


def human_start_at(raw: str) -> str:





    text = (raw or "").strip()
    if not text:
        return ""
    try:
        moment = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        return ""
    return f"{moment.year}年{moment.month}月{moment.day}日 {moment.hour:02d}:{moment.minute:02d}"


def describe_schedule(spec: ScheduledTaskSpec) -> str:





    if spec.trigger == "daily":
        base = f"每天 {spec.at_time}"
    elif spec.trigger == "weekly":
        base = f"每{_WEEKDAYS[spec.weekday]} {spec.at_time}"
    elif spec.interval_minutes < 60:
        base = f"每 {spec.interval_minutes} 分钟"
    elif spec.interval_minutes % (60 * 24) == 0:
        
        
        base = f"每 {spec.interval_minutes // (60 * 24)} 天"
    elif spec.interval_minutes % 60 == 0:
        base = f"每 {spec.interval_minutes // 60} 小时"
    else:
        base = f"每 {spec.interval_minutes} 分钟"

    
    
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


    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    
    
    
    def list(self) -> list[ScheduledTaskSpec]:
        return list(self._runtime.config.settings.agent.scheduled_tasks or [])

    def describe(self, spec: ScheduledTaskSpec) -> str:





        return describe_schedule(spec)

    def get(self, task_id: str) -> ScheduledTaskSpec:
        found = next((item for item in self.list() if item.id == task_id), None)
        if found is None:
            raise ScheduledTaskNotFoundError(
                f"没有找到自动化任务「{task_id}」。", detail=task_id
            )
        return found

    
    
    
    async def create(self, **fields: Any) -> ScheduledTaskSpec:

        raw = {"id": fields.pop("id", "") or new_task_id(), **fields}
        spec = ScheduledTaskSpec.model_validate(raw)
        await self._save([*self.list(), spec])
        logger.info("已新建自动化任务 %s（%s）", spec.id, spec.name)
        return spec

    async def update(self, task_id: str, **changes: Any) -> ScheduledTaskSpec:






        current = self.get(task_id)
        payload = {**current.model_dump(), **{k: v for k, v in changes.items() if v is not None}}
        
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

        return await self._runtime.task_scheduler.run_now(task_id)

    async def _save(self, specs: list[ScheduledTaskSpec]) -> None:
        await self._runtime.save_scheduled_tasks(specs)
