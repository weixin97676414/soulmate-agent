









from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ...observability.metrics import METRICS

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def read_metrics(request: Request, format: str = "prometheus") -> Any:





    if format == "json":
        return METRICS.snapshot()
    return PlainTextResponse(
        METRICS.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
