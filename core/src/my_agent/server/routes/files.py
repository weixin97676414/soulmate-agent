





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


_UPLOAD_CHUNK = 1024 * 1024


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
    
    
    
    file: UploadFile = File(...),  
    session_id: str | None = Query(None),
) -> dict[str, Any]:
    workspace = _workspace(request)

    
    
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + _MULTIPART_SLACK:
        raise _too_large()

    
    
    
    
    
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
    removed = await workspace.clear(kind=payload.kind)  
    return {"ok": True, "removed": removed}


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: str,
    request: Request,
    kind: str = Query("artifact", description="upload / artifact"),
) -> dict[str, Any]:





    workspace = _workspace(request)
    if kind not in ("upload", "artifact"):
        raise HTTPException(status_code=422, detail="kind 只能是 upload 或 artifact")

    record = await workspace.get(file_id, kind=kind)  
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    try:
        path = workspace.resolve(file_id, record.kind)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    
    
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
    record = await workspace.get(file_id, kind=kind)  
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
    removed = await workspace.delete(file_id, kind=kind)  
    if not removed:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    return {"ok": True}


@router.get("/limits/info")
async def upload_limits() -> dict[str, Any]:

    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_upload_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
    }
