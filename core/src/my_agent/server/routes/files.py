"""工作区文件接口：附件上传、产物列表、下载与清理。

上传走 ``multipart/form-data``；下载用 ``FileResponse`` 直接回文件流，
前端可以用它做图片预览或"另存为"。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...storage.files import MAX_UPLOAD_BYTES, WorkspaceError
from ...storage.preview import build_preview
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["files"], prefix="/v1/files")

# 分块读取的大小。1MB 足够摊薄 await 的开销，又让超限检查能及时生效。
_UPLOAD_CHUNK = 1024 * 1024
# multipart 的边界、字段名等也要占字节，按 Content-Length 预检时留出余量，
# 免得一个正好 50MB 的文件因为少算了这几百字节而被误拒。
_MULTIPART_SLACK = 1024 * 1024


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"文件过大，单文件上限 {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
    )


class ClearRequest(BaseModel):
    kind: str | None = None


def _workspace(request: Request):
    runtime: AppRuntime = get_runtime(request)
    return runtime.workspace


@router.get("")
async def list_files(
    request: Request,
    kind: str | None = Query(None, description="upload / artifact，留空返回全部"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    workspace = _workspace(request)
    if kind not in (None, "upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")
    files = await workspace.list_files(kind=kind, limit=limit)
    return {"files": [item.to_dict() for item in files], "stats": await workspace.stats()}


@router.post("/upload")
async def upload_file(
    request: Request,
    # FastAPI 的依赖注入就是靠"在默认值位置调用工厂函数"实现的：这是框架要求的
    # 标准写法，不是"在默认参数里做函数调用"那个陷阱。真正危险的是可变默认值
    # （list/dict）被所有调用共享 —— 这里不存在。
    file: UploadFile = File(...),  # noqa: B008
    session_id: str | None = Query(None),
) -> dict[str, Any]:
    workspace = _workspace(request)

    # 第一道闸：Content-Length 超了就连 body 都不读。
    # 这是唯一能在数据进入进程**之前**拦住的时机。
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + _MULTIPART_SLACK:
        raise _too_large()

    # 第二道闸：分块读取并累计计数，超限立刻中断。
    #
    # 原先是 `await file.read()` 一次读完再校验大小 —— 一个 2GB 的上传会先把
    # 内存吃满才被拒绝，可能直接 OOM 掉整个核心进程（连带正在进行的对话一起丢）。
    # 改成有界累积后，内存占用上限就是 MAX_UPLOAD_BYTES。
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise _too_large()
        chunks.append(chunk)

    try:
        # ⚠️ 拼接丢进线程（第 87 批，M-12）：50MB 的 `join` 是一次同步 memcpy，
        # 放在事件循环上会让**所有会话**短暂停顿。峰值内存仍是约 2×上限
        #（chunks 列表 + 拼接结果），但那是有界的 —— 真正要修的是那一下停顿。
        content = await asyncio.to_thread(b"".join, chunks)
        record = await workspace.save_upload(
            filename=file.filename or "unnamed",
            content=content,
            session_id=session_id,
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_dict()


@router.get("/stats")
async def file_stats(request: Request) -> dict[str, Any]:
    return await _workspace(request).stats()


@router.post("/clear")
async def clear_files(payload: ClearRequest, request: Request) -> dict[str, Any]:
    workspace = _workspace(request)
    if payload.kind not in (None, "upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")
    removed = await workspace.clear(kind=payload.kind)  # type: ignore[arg-type]
    return {"ok": True, "removed": removed}


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: str,
    request: Request,
    kind: str = Query("artifact", description="upload / artifact"),
) -> dict[str, Any]:
    """把文件归一化成前端可直接渲染的结构（图表 / Markdown / 表格 / 图片）。

    返回 ``kind`` 字段告诉前端用哪个渲染器；解析失败时返回 ``kind=unsupported``
    并附上原因，而不是抛错——预览失败是很平常的事。
    """
    workspace = _workspace(request)
    if kind not in ("upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")

    record = await workspace.get(file_id, kind=kind)  # type: ignore[arg-type]
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    try:
        path = workspace.resolve(file_id, record.kind)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # 解析大表 / 大 PDF / 大 Word 是 CPU + IO 重活。同步跑会阻塞事件循环，
    # 期间**所有会话的 SSE 都会一起卡住**（用户会看到整个应用"假死"）。
    return await asyncio.to_thread(
        build_preview,
        Path(path),
        original_name=record.original_name,
        mime=record.mime,
        download_url=f"/v1/files/{file_id}?kind={record.kind}",
    )


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    request: Request,
    kind: str = Query("upload", description="upload / artifact"),
) -> FileResponse:
    workspace = _workspace(request)
    if kind not in ("upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")
    record = await workspace.get(file_id, kind=kind)  # type: ignore[arg-type]
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    try:
        path = workspace.resolve(file_id, record.kind)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=record.mime or "application/octet-stream",
        filename=record.original_name,
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    request: Request,
    kind: str = Query("upload", description="upload / artifact"),
) -> dict[str, Any]:
    workspace = _workspace(request)
    if kind not in ("upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")
    removed = await workspace.delete(file_id, kind=kind)  # type: ignore[arg-type]
    if not removed:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    return {"ok": True}


@router.get("/limits/info")
async def upload_limits() -> dict[str, Any]:
    """供前端展示上传限制，避免用户传了超大文件才报错。"""
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_upload_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
    }
