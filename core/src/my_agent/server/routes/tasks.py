"""自动化任务接口。

任务**同时是配置**（随 settings.json 落盘），所以在这里读写的是配置本身；
而"上次执行时间""是否正在跑""条件基线"这些只活在内存里，由调度器提供。

之前这里只有"列出 + 立即执行"两个接口，增删改要让界面去改整份 settings ——
那意味着前端要读-改-写整个 ``agent`` 段，任何一次并发保存都会把对方的改动吞掉。
现在增删改各有自己的接口，落到 ``ScheduledTaskStore`` 这一份实现上
（搭子自建任务的内置技能也走它，两条路径不会长歪）。
"""

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
    """内置搭子相关的任务：用户不能改 / 关 / 删，只能让搭子改。

    ⚠️ 判在**路由层**是刻意的：搭子改任务走的是存储层（技能直连），
    把这道闸下沉到存储层，"搭子能改"这条路会被自己堵死。详见
    ``task_store.locked_for_user()``。
    """
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
    """列出自动化任务及其运行状态。"""
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
    """新建任务。新建后**立刻**纳入调度，无需重启客户端。"""
    runtime: AppRuntime = get_runtime(request)
    # 「来源」与「静默」都由**服务端**写死，不信前端传什么：前者决定"能不能改"，
    # 让界面自己声明等于把锁的钥匙交出去；后者决定"跑完打不打扰"，界面本来也只建
    # 用户任务 —— 而"静默"是那四条预置任务专用的形态，用户任务没有这一档
    payload = payload.model_copy(update={"origin": "user", "silent": False})
    spec = await runtime.task_store.create(**payload.model_dump())
    # 留痕：任务的增删改也要能回溯（产品要求"哪个搭子在什么时候做了什么"）
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
    """整条更新任务（界面提交的是它自己拿到的那份完整配置）。"""
    runtime: AppRuntime = get_runtime(request)
    try:
        current = runtime.task_store.get(task_id)
    except ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    _reject_locked(current)
    # 「来源」与「静默」都不是界面能改的字段：来源被改成 user 等于把锁摘掉，
    # 静默被界面回传的默认值洗掉则会让"跑完不打扰"悄悄失效 —— 一律以现存值为准
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
    """立刻执行一次（不等下一个周期）。

    返回 409 而不是排队：用户点这个按钮的意图是"**现在**就看结果"，
    排队成"跑完再跑一遍"不是他要的。而且自动化任务会真的花钱，
    悄悄多跑一次比明确拒绝糟糕得多。

    与自动执行的一点差别：这里**不检查触发条件** —— 用户是明知内容没变化
    也要跑一遍（多半是在试任务配好没有），拦着他反而莫名其妙。
    """
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
