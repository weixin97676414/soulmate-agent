"""断点续跑：列出没跑完的运行，并接着跑。

## 接口的两种形态（因为两种"续跑"本质不同）

- **定时任务**：跑在后台，没有界面要订阅 —— 所以 ``POST /v1/runs/{id}/resume``
  直接把它重新排进调度器，接口立即返回。
- **群讨论 / 单聊**：它们是**流式**的，续跑意味着界面要重新订阅那条 SSE 流。所以
  这里只返回"接着说要用的话题文本"（群讨论还带上群 id），由界面去调**既有的**入口 ——
  群讨论走 ``/v1/groups/{id}/discuss``、单聊走 ``/v1/chat`` —— 复用同一条渲染路径，
  不另造一套"从断点恢复"的流。

## 为什么话题文本由后端给

"[续跑] 上一次在第 3 轮中断……"这句话决定了模型会不会重头再来一遍，它是**协议**
的一部分，不该散落在前端文案里。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["runs"], prefix="/v1/runs")


def _stop_reason(run: Any) -> str:
    """一句"为什么停下来"（给**模型**看的那份续跑提示用）。

    空着不说原因，模型会以为上一轮是自己想停下来想想，然后重头再来一遍 ——
    白花钱，还可能把已经改好的东西又改一次。
    """
    if run.error:
        # 引擎那句"步数用尽"的解释有一百多字，截断只是别把提示词撑得太长
        return str(run.error)[:200]
    return {
        "cancelled": "被中断",
        "incomplete": "用完了一次任务的执行步数",
    }.get(run.status, "原因未知")


def _run_payload(run: Any) -> dict[str, Any]:
    data = run.to_dict()
    # 顺带给一句人话，界面不用自己拼（也就不会出现两种说法）
    what = {"task": "自动化任务", "group": "群讨论", "chat": "这一轮对话"}.get(
        run.kind, "这次执行"
    )
    if run.status == "cancelled":
        data["summary"] = f"{what}没跑完就被中断了"
    elif run.status == "incomplete":
        # 「没做完」不等于「失败」：前者还能接着做，后者得去修配置。
        # 混成一句话，用户点进来才发现方向不对（引擎的解释本身就是干净的，
        # 直接接在冒号后面即可）。
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
    """列出**待续跑**的运行（跑完的不会在这里 —— 进度行在正常结束时就删掉了）。"""
    runtime: AppRuntime = get_runtime(request)
    runs = await runtime.runs.list_pending()
    return {"total": len(runs), "runs": [_run_payload(run) for run in runs]}


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, request: Request) -> dict[str, Any]:
    """接着上次中断的地方继续。"""
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
        # 进度行的最终去向由执行本身负责（跑完删掉、再挂就更新）
        return {"ok": True, "kind": "task", "session_id": run.session_id}

    if run.kind == "group":
        # 群讨论：这条进度行先清掉，接着由界面发起的那次讨论重新记（它会自己建新行）。
        # 不清的话，"继续"按钮会一直挂着，用户会以为点了没反应。
        await runtime.runs.finish(run_id)
        topic = (
            f"[续跑] 上一次这场讨论到第 {run.step} 轮时中断"
            f"（{run.error or '被中断'}），最后是「{run.last_action or '有人'}」。"
            "请接着把它讨论完；**已经定下来的结论不要再重新讨论**，"
            "需要前文时按本群的对话记录继续。"
        )
        return {"ok": True, "kind": "group", "group_id": run.ref_id, "topic": topic}

    # 单聊：**做**「继续」按钮 —— 这里反转了上次的结论。
    #
    # 上次的判断是"中断后用户自己补一句『继续』就够了"。那对熟悉这类工具的人
    # 成立，但这个产品面向零基础用户：回答停在半路时他们的第一反应是"是不是坏了"，
    # 而不是"我该补一句话"。所以接着要说的那句由**后端**给，界面只负责把它发出去，
    # 与群讨论同一套协议（后端给文本、界面走既有链路，不另造恢复流）。
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
    """不再续跑这条（用户自己放弃）。"""
    runtime: AppRuntime = get_runtime(request)
    run = await runtime.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="这条记录已经不存在")
    await runtime.runs.finish(run_id)
    return {"ok": True}
