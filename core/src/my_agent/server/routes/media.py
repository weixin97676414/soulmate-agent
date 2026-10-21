





















from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ...errors import PathNotAllowedError
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["media"], prefix="/v1/media")



IMAGE_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
}



MAX_LOCAL_IMAGE_BYTES = 30 * 1024 * 1024

_FORMATS = "、".join(sorted(IMAGE_TYPES))


def _is_network_path(raw: str) -> bool:

    return raw.startswith("\\\\") or raw.startswith("//")


def _checked_path(runtime: AppRuntime, raw: str) -> Path:





    if not Path(raw).is_absolute():
        raise HTTPException(
            status_code=400,
            detail=f"需要一个完整的绝对路径（例如 D:\\图片\\a.png），收到的是：{raw}",
        )
    try:
        return runtime.path_policy.check(raw, mode="read")
    except PathNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc


def _image_mime(path: Path) -> str:
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime is None:
        raise HTTPException(
            status_code=415,
            detail=f"不是支持的图片格式（支持 {_FORMATS}）：{path.name}",
        )
    return mime


def _decoded_path(raw: str) -> str | None:







    if "%" not in raw:
        return None
    decoded = unquote(raw)
    return decoded if decoded != raw else None


@router.get("/local-image")
async def local_image(
    request: Request,
    path: str = Query(..., description="本机图片的绝对路径（由对话内容提供）"),
) -> Response:

    raw = (path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="没有提供图片路径。")

    if _is_network_path(raw):
        raise HTTPException(
            status_code=403,
            detail=(
                "不支持网络路径（\\\\服务器\\共享）：访问它会让本机向那台机器发起"
                "Windows 身份认证，可能泄露你的凭据。请先把图片复制到本机磁盘再引用。"
            ),
        )

    runtime: AppRuntime = get_runtime(request)
    resolved = _checked_path(runtime, raw)
    mime = _image_mime(resolved)

    if not resolved.exists():
        
        
        retry = _decoded_path(raw)
        if retry is not None:
            resolved = _checked_path(runtime, retry)
            mime = _image_mime(resolved)

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"图片不存在：{resolved}")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"这是一个文件夹，不是图片：{resolved}")

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"读取图片失败：{exc}") from exc
    if size > MAX_LOCAL_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"图片过大（{size // 1024 // 1024} MB），"
                f"上限 {MAX_LOCAL_IMAGE_BYTES // 1024 // 1024} MB：{resolved.name}"
            ),
        )

    try:
        
        data = await asyncio.to_thread(resolved.read_bytes)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"读取图片失败：{exc}") from exc

    
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})
