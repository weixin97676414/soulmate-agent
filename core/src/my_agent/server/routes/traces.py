





from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["traces"])


@router.get("/v1/traces")
async def list_traces(request: Request, limit: int = 20) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    items = runtime.traces.recent(limit=limit)
    return {"total": len(runtime.traces), "items": items}


@router.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, Any]:





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
