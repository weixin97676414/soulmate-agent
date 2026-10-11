"""Trace 查询接口。

对应《智能体框架开发文档》12.2 节。此前 Tracer 一直在产出 span，
但**没有任何接口能把它们取回来** —— 界面上显示了 trace_id，用户照着查却是 404。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["traces"])


@router.get("/v1/traces")
async def list_traces(request: Request, limit: int = 20) -> dict[str, Any]:
    """最近若干次执行的摘要。"""
    runtime: AppRuntime = get_runtime(request)
    items = runtime.traces.recent(limit=limit)
    return {"total": len(runtime.traces), "items": items}


@router.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, Any]:
    """按 id 取一次完整 Trace（含全部 span）。

    只保留最近若干次，所以查不到是**正常情况**，不是错误 —— 提示里要说清楚
    是"已被淘汰"而不是"不存在"，否则用户会以为是数据坏了。
    """
    runtime: AppRuntime = get_runtime(request)
    payload = runtime.traces.get(trace_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Trace {trace_id} 不在最近 {len(runtime.traces)} 条记录中"
                "（只保留最近若干次，更早的已淘汰）。"
            ),
        )
    return payload
