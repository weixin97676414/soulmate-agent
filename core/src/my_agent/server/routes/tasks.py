










from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...agent.task_store import locked_for_user
from ...config.schemas import ScheduledTaskDraft
from ...errors import ScheduledTaskNotFoundError
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["tasks"], prefix="/v1/tasks")


def _reject_locked(spec: Any) -> None:






    if locked_for_user(spec):
        raise HTTPException(
            status_code=409,
            detail=(
                f"「{spec.name}」是内置搭子的自动化任务，不支持手动修改。"
                "你可以通过与搭子协商进行调整。"
            ),
        )


@router.get("")
async def list_tasks(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    items = runtime.task_scheduler.describe()
    return {
        "total": len(items),
        "enabled": sum(1 for item in items if item.get("enabled")),
        "scheduler_running": runtime.task_scheduler.running,
        "items": items,
    }


@router.post("")
async def create_task(payload: ScheduledTaskDraft, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    
    
    
    payload = payload.model_copy(update={"origin": "user", "silent": False})
    spec = await runtime.task_store.create(**payload.model_dump())
    
    await runtime.audit.op(
        kind="task",
        action="create",
        actor_id=spec.assistant_id or None,
        target=spec.id,
        detail=f"新建自动化任务「{spec.name}」",
    )
    return {"ok": True, "task": spec.model_dump()}


@router.put("/{task_id}")
async def update_task(
    task_id: str, payload: ScheduledTaskDraft, request: Request
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    try:
        current = runtime.task_store.get(task_id)
    except ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    _reject_locked(current)
    
    
    payload = payload.model_copy(update={"origin": current.origin, "silent": current.silent})
    try:
        spec = await runtime.task_store.update(task_id, **payload.model_dump())
    except ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    await runtime.audit.op(
        kind="task",
        action="update",
        actor_id=spec.assistant_id or None,
        target=spec.id,
        detail=f"修改自动化任务「{spec.name}」",
    )
    return {"ok": True, "task": spec.model_dump()}


@router.delete("/{task_id}")
async def delete_task(task_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    try:
        current = runtime.task_store.get(task_id)
    except ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    _reject_locked(current)
    try:
        spec = await runtime.task_store.delete(task_id)
    except ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    await runtime.audit.op(
        kind="task",
        action="delete",
        actor_id=spec.assistant_id or None,
        target=spec.id,
        detail=f"删除自动化任务「{spec.name}」",
    )
    return {"ok": True, "deleted": spec.id}


@router.post("/{task_id}/run")
async def run_task_now(task_id: str, request: Request) -> dict[str, Any]:









    runtime: AppRuntime = get_runtime(request)
    if not await runtime.task_scheduler.run_now(task_id):
        raise HTTPException(
            status_code=409,
            detail=f"任务 {task_id} 不存在，或者它正在执行中。",
        )
    await runtime.audit.op(
        kind="task",
        action="run_now",
        target=task_id,
        detail="用户手动立即执行了一次",
    )
    return {"ok": True, "task_id": task_id}
