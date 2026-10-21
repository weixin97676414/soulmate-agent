





















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


    key: str
    line: str | None = None


class KeyPayload(BaseModel):


    key: str


def _downloader(request: Request) -> Any:

    runtime = get_runtime(request)
    downloader = getattr(runtime, "model_downloader", None)
    if downloader is None:  
        raise HTTPException(status_code=503, detail="模型下载器尚未就绪")
    return downloader


def _require_key(key: str) -> None:

    if catalog.get(key) is None:
        raise HTTPException(status_code=404, detail=f"未知模型：{key}")


def _resolve_line(request: Request, override: str | None) -> str:





    runtime = get_runtime(request)
    line = (override or "").strip().lower() or (runtime.line or DEFAULT_LINE)
    if line not in catalog.LINE_TITLES:
        raise HTTPException(status_code=422, detail=f"未知线路：{override}")
    return line


@router.get("/v1/models/status")
async def model_status(request: Request) -> dict[str, Any]:

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

    _require_key(payload.key)
    downloader = _downloader(request)
    line = _resolve_line(request, payload.line)
    return await downloader.start(payload.key, line)


@router.post("/v1/models/cancel")
async def model_cancel(payload: KeyPayload, request: Request) -> dict[str, Any]:

    _require_key(payload.key)
    downloader = _downloader(request)
    return await downloader.cancel(payload.key)


@router.post("/v1/models/verify")
async def model_verify(payload: KeyPayload, request: Request) -> dict[str, Any]:






    _require_key(payload.key)
    downloader = _downloader(request)
    return await downloader.verify(payload.key)
