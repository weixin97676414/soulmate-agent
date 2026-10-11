"""指标端点。

对应《智能体框架开发文档》11.4 节（一期：内存计数 + 端点）。

默认输出 **Prometheus 文本格式** —— 它是这类端点的既成约定，用户想接
现有的监控工具时不需要我们再改一次。同时也提供 ``?format=json``：
桌面客户端的场景里，用户更可能是在设置界面里直接看，而不是接一个抓取器，
JSON 对前端更省事。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ...observability.metrics import METRICS

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def read_metrics(request: Request, format: str = "prometheus") -> Any:
    """读取进程内指标。

    注意它是**进程内累积值**，重启即清零 —— 桌面客户端没有持久化指标的
    必要，跨重启的长期趋势由 `usage_log` 那张表负责（见 /v1/usage）。
    """
    if format == "json":
        return METRICS.snapshot()
    return PlainTextResponse(
        METRICS.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
