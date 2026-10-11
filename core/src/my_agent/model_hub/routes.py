"""本地模型下载的 HTTP 接口：状态 / 下载 / 取消 / 校验。

## 为什么这四个端点住在这个包里，而不是 ``server/routes/``

它们与 ``catalog``（要下什么、从哪下）和 ``downloader``（怎么下）是一个整体 ——
"清单 + 落盘 + 校验"三件事必须放一起才读得懂；拆到两个包反而要来回跳。
**装配方式与其它路由完全一致**：``server/routes/__init__.py`` 里登记名字、
``server/app.py`` 里 ``include_router``。

## 线路不由前端指定

前端拿不到主进程算出来的线路（那是主进程按系统语言 + 探测定下来的），
所以默认取 ``runtime.line``（主进程经 ``PUT /v1/client/line`` 同步进来的）。
请求体里的 ``line`` 只是给测试与"将来手动换源"留的口子，**不算主路径**。

## 为什么 ``verify`` 走线程池

它是**真加载模型**（识别链路 / 嵌入器各跑一遍），是同步阻塞的 CPU 活。
写在事件循环里会把同一进程的 SSE 流与其它请求一起卡住（最长几秒），
所以 ``downloader.verify`` 内部已经 ``asyncio.to_thread`` 了，这里只要 ``await``。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config.lines import DEFAULT_LINE
from ..server.deps import get_runtime
from . import catalog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["model-hub"])


class DownloadPayload(BaseModel):
    """开始下载。``line`` 留空 = 用当前线路（正常路径）。"""

    key: str
    line: str | None = None


class KeyPayload(BaseModel):
    """取消 / 校验（都只需要模型 id）。"""

    key: str


def _downloader(request: Request) -> Any:
    """取运行时装配的下载器（``AppRuntime.model_downloader``）。"""
    runtime = get_runtime(request)
    downloader = getattr(runtime, "model_downloader", None)
    if downloader is None:  # pragma: no cover - 运行时装配保证它存在
        raise HTTPException(status_code=503, detail="模型下载器尚未就绪")
    return downloader


def _require_key(key: str) -> None:
    """id 不认识就 404（``catalog.get`` 本来就返回 ``None``，不抛异常穿透）。"""
    if catalog.get(key) is None:
        raise HTTPException(status_code=404, detail=f"未知模型：{key}")


def _resolve_line(request: Request, override: str | None) -> str:
    """定下这次下载走哪条线路。

    校验放在这里而不是交给下载器：线路是**用户可见的选择**，
    给一个不认识的线路应当当场 422，而不是静默按国外源去下几百 MB。
    """
    runtime = get_runtime(request)
    line = (override or "").strip().lower() or (runtime.line or DEFAULT_LINE)
    if line not in catalog.LINE_TITLES:
        raise HTTPException(status_code=422, detail=f"未知线路：{override}")
    return line


@router.get("/v1/models/status")
async def model_status(request: Request) -> dict[str, Any]:
    """两个模型的当前状态（首屏渲染 + 断流时的兜底轮询都读它）。"""
    downloader = _downloader(request)
    runtime = get_runtime(request)
    line = runtime.line or DEFAULT_LINE
    return {
        "ok": True,
        "line": line,
        "line_title": catalog.line_title(line),
        "models": downloader.all_status(),
    }


@router.post("/v1/models/download")
async def model_download(payload: DownloadPayload, request: Request) -> dict[str, Any]:
    """开始下载（已在跑就原样返回，不重复起任务）。"""
    _require_key(payload.key)
    downloader = _downloader(request)
    line = _resolve_line(request, payload.line)
    return await downloader.start(payload.key, line)


@router.post("/v1/models/cancel")
async def model_cancel(payload: KeyPayload, request: Request) -> dict[str, Any]:
    """取消下载（幂等：没在跑就返回 ``not-running``，不算错误）。"""
    _require_key(payload.key)
    downloader = _downloader(request)
    return await downloader.cancel(payload.key)


@router.post("/v1/models/verify")
async def model_verify(payload: KeyPayload, request: Request) -> dict[str, Any]:
    """下载完的"自动检测"，也是设置页那个「验证一下」。

    ⚠️ **真的把模型加载起来用一次**，而不是看文件在不在（理由见
    ``downloader.verify`` 的说明）。失败不是服务端错误，所以返回 200 +
    ``ok=False`` —— 让界面拿得到具体原因，而不是一句 500。
    """
    _require_key(payload.key)
    downloader = _downloader(request)
    return await downloader.verify(payload.key)
