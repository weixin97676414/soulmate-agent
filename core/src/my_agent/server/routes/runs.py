
















from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["runs"], prefix="/v1/runs")


def _stop_reason(run: Any) -> str:





    if run.error:
        
        return str(run.error)[:200]
    return {
        "cancelled": "被中断",
        "incomplete": "用完了一次任务的执行步数",
    }.get(run.status, "原因未知")


def _run_payload(run: Any) -> dict[str, Any]:
    data = run.to_dict()
    
    what = {"task": "自动化任务", "group": "群讨论", "chat": "这一轮对话"}.get(
        run.kind, "这次执行"
    )
    if run.status == "cancelled":
        data["summary"] = f"{what}没跑完就被中断了"
    elif run.status == "incomplete":
        
        
        
        data["summary"] = f"{what}没做完就停下来了" + (
            f"：{run.error}" if run.error else ""
        )
    else:
        data["summary"] = f"{what}执行失败：{run.error or '原因未知'}"
    if run.last_action:
        data["summary"] += f"（最后在做：{run.last_action}）"
    return data


@router.get("")
async def list_runs(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    runs = await runtime.runs.list_pending()
    return {"total": len(runs), "runs": [_run_payload(run) for run in runs]}


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    run = await runtime.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="这条记录已经不存在（可能已经续跑过了）")

    if run.kind == "task":
        started = await runtime.task_scheduler.resume(run)
        if not started:
            raise HTTPException(
                status_code=409,
                detail="续跑失败：任务不存在，或者它正在执行中。",
            )
        
        return {"ok": True, "kind": "task", "session_id": run.session_id}

    if run.kind == "group":
        
        
        await runtime.runs.finish(run_id)
        topic = (
            f"[续跑] 上一次这场讨论到第 {run.step} 轮时中断"
            f"（{run.error or '被中断'}），最后是「{run.last_action or '有人'}」。"
            "请接着把它讨论完；**已经定下来的结论不要再重新讨论**，"
            "需要前文时按本群的对话记录继续。"
        )
        return {"ok": True, "kind": "group", "group_id": run.ref_id, "topic": topic}

    
    
    
    
    
    
    await runtime.runs.finish(run_id)
    topic = (
        f"[续跑] 上一轮对话到第 {run.step} 步时停下来了"
        f"（{_stop_reason(run)}），最后在做的是「{run.last_action or '不确定'}」。"
        "请接着把没做完的部分做完；**已经完成、已经确认过的部分不要重做**，"
        "需要前面的结果时按这个会话里已有的记录继续。"
    )
    return {
        "ok": True,
        "kind": "chat",
        "session_id": run.session_id,
        "topic": topic,
    }


@router.delete("/{run_id}")
async def dismiss_run(run_id: str, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    run = await runtime.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="这条记录已经不存在")
    await runtime.runs.finish(run_id)
    return {"ok": True}
