

























from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from ..utils.http import async_client



ALLOWED_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})

_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


class ImageSourceError(ValueError):
    pass






def guess_image_mime(filename: str) -> str:




    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_MIME.get(suffix, "image/png")


def sniff_image_mime(raw: bytes) -> str | None:






    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _bytes_from_url(url: str, *, limit: int, timeout: float = 20.0) -> bytes:





















    try:
        async with async_client(
            timeout=timeout, follow_redirects=True, trust_env=False
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ImageSourceError(f"下载图片失败（HTTP {response.status_code}）：{url}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ImageSourceError(
                            f"这个链接的图片超过 {limit / 1024:.0f}KB，没有下完就停了：{url}"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
    except ImageSourceError:
        raise
    except httpx.HTTPError as exc:
        
        raise ImageSourceError(f"下载图片失败：{str(exc)[:200]}") from exc


def _bytes_from_path(path_text: str) -> bytes:
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise ImageSourceError(f"找不到这个文件：{path_text}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ImageSourceError(f"读不了这个文件（{path_text}）：{exc}") from exc


async def load_image_bytes(source: str, *, limit: int, workspace: Any = None) -> tuple[bytes, str]:








    text = (source or "").strip()
    if not text:
        raise ImageSourceError("没有给图片来源。")

    if text.lower().startswith(("http://", "https://")):
        return await _bytes_from_url(text, limit=limit), "链接"

    if workspace is not None:
        try:
            record = await workspace.get(text)
        except Exception:  
            record = None
        if record is not None:
            try:
                path = workspace.resolve(record.id, record.kind)
            except Exception as exc:  
                raise ImageSourceError(
                    f"上传的图片「{record.original_name}」已经不在磁盘上了。"
                ) from exc
            return path.read_bytes(), f"上传的图片「{record.original_name}」"

    try:
        return _bytes_from_path(text), "本机文件"
    except ImageSourceError as exc:
        raise ImageSourceError(
            f"{exc} 它既不是本机的一个文件，也不是工作区里上传件的 id。"
            "请确认路径写对了，或改用图片链接。"
        ) from exc


def encode_data_url(raw: bytes, *, max_bytes: int, label: str) -> tuple[str, str]:

    if not raw:
        raise ImageSourceError(f"{label}是空文件。")
    if len(raw) > max_bytes:
        raise ImageSourceError(
            f"{label}有 {len(raw) / 1024 / 1024:.1f}MB，超过 {max_bytes / 1024:.0f}KB 的上限。"
            "这个大小是要**存进配置里**的，太大没法用 —— 请换一张小一点的图，"
            "或先把它压缩一下再试。"
        )
    mime = sniff_image_mime(raw)
    if mime is None or mime not in ALLOWED_IMAGE_MIMES:
        raise ImageSourceError(
            f"{label}不是能识别的图片格式（只支持 PNG / JPEG / WebP / GIF）。"
        )
    return mime, f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


async def to_data_url(source: str, *, max_bytes: int, workspace: Any = None) -> tuple[str, str]:

    raw, label = await load_image_bytes(source, limit=max_bytes, workspace=workspace)
    return encode_data_url(raw, max_bytes=max_bytes, label=label)


__all__ = [
    "ALLOWED_IMAGE_MIMES",
    "ImageSourceError",
    "encode_data_url",
    "guess_image_mime",
    "load_image_bytes",
    "sniff_image_mime",
    "to_data_url",
]
