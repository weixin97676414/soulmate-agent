"""用量与费用统计接口。

对应《智能体框架开发文档》FR-13 / 16.2。这是自研客户端相对 Web 版最实在的
一个优势：**数据在本地**，可以给出"这个月花了多少、哪个模型最烧钱、缓存省了多少"
这类厂商控制台里看不到（或看得很费劲）的东西。

⚠️ 这一层现在只剩"收参数 → 交给 `runtime.usage` → 返回"（审计 L-01）：
取数、可用性判定、以及"用户到底填没填单价"都在 `services/usage.py` 里。
**那三条刻意的口径**（不知道 ≠ 免费、不可用时不返回一堆 0、缓存命中率要留着）
写在该模块的 docstring 里 —— 改行为前先读它。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ..deps import get_runtime

router = APIRouter(tags=["usage"], prefix="/v1/usage")


@router.get("/summary")
async def summary(request: Request, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return await get_runtime(request).usage.summary(days)


@router.get("/session/{session_id}")
async def session_usage(session_id: str, request: Request) -> dict[str, Any]:
    """单个会话的累计用量（Trace 抽屉 / 会话详情用）。"""
    return await get_runtime(request).usage.session(session_id)


@router.delete("")
async def clear_usage(request: Request) -> dict[str, Any]:
    """清空用量流水。只删统计，不动会话与消息。"""
    return {"ok": True, "removed": await get_runtime(request).usage.clear()}
