"""本机图片代理：把对话里出现的**本地图片路径**变成渲染层能显示的字节。

## 为什么需要这个接口

模型在回答里贴图片时会写成 ``![说明](D:\\tmp\\chart.png)``，渲染层拿到的是一个**本机路径**，
而浏览器加载不了它：``D:\\tmp\\chart.png`` 根本不是合法 URL（``d:`` 会被当成协议名），
``file:///D:/...`` 在开发态（页面在 ``http://localhost``）也拿不到，生产态的 CSP 也不放行 ``file:``。

所以由核心读文件、按图片类型回字节，前端用带鉴权的 fetch 取成 Blob 再交给 ``<img>``。
好处不只是"能显示"：文件不存在 / 不是图片 / 超出白名单时，前端能拿到**一句人话**并显示出来 ——
而不是一个静默的破图（用户明确说过"静默失败"是他最不能接受的）。

## 安全边界（这个接口接受客户端传来的**任意路径**，所以要收紧）

- 只认**图片扩展名白名单**，不做"通用读盘"接口；
- 复用 ``PathPolicy.check``：畸形语法（NTFS 数据流、空字节、控制字符）与**文件访问白名单**
  一并生效（用户配了白名单就按白名单来；没配则不限制目录，与技能那边的口径一致）；
- 明确拒绝 **UNC / 网络路径**（``\\\\server\\share\\x.png``）：Windows 访问它会向那台机器
  发起 SMB 认证，可能把本机的 NTLM 凭据送出去 —— "显示一张图"绝不该带来这种后果；
- 大小上限：超了直接拒绝，不把几十 MB 读进内存。
"""

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

# 扩展名 → 媒体类型。刻意用**白名单**而不是 ``mimetypes.guess_type``：
# 后者会把 ``.txt`` 之类也认出来，于是这个接口就悄悄变成了"读任意文件"。
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

# 单张图上限。和附件上传（50MB）分开：图片是**渲染**用的，再大也没有意义，
# 而它要整个进内存再回给前端。
MAX_LOCAL_IMAGE_BYTES = 30 * 1024 * 1024

_FORMATS = "、".join(sorted(IMAGE_TYPES))


def _is_network_path(raw: str) -> bool:
    """UNC（``\\\\server\\share``）或前向斜杠写法（``//server/share``）。"""
    return raw.startswith("\\\\") or raw.startswith("//")


def _checked_path(runtime: AppRuntime, raw: str) -> Path:
    """解析路径并过安全校验；不通过时抛 ``HTTPException``。

    **畸形语法**（NTFS 数据流、空字节、控制字符）与**文件访问白名单**都在
    ``PathPolicy.check`` 里收口 —— 与技能读文件走的是同一套规则，不另造一份。
    """
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
    """给百分号编码的写法再一次机会。

    模型是按"链接"的思路写图片地址的，带空格的路径常写成 ``D:\\my%20dir\\a.png``
    （URL 里的规矩）—— 这个字符串**字面不是真实文件名**，直接找必然不存在。
    所以原样查不到、且含 ``%`` 时才解码重试；"文件名里真的带 %" 不会被猜错，
    因为判断依据是**文件是否真的存在**，而不是猜。
    """
    if "%" not in raw:
        return None
    decoded = unquote(raw)
    return decoded if decoded != raw else None


@router.get("/local-image")
async def local_image(
    request: Request,
    path: str = Query(..., description="本机图片的绝对路径（由对话内容提供）"),
) -> Response:
    """读一张本机图片并回字节。失败时回**可读的原因**（前端会展示给用户）。"""
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
        # 顺序很重要：先按**原样**查一次，查不到才解码重试。
        # 别拿解码后的路径当第一选择 —— 那会把"文件名里真的带 %"的文件找错。
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
        # 读盘是同步调用，直接跑会卡住事件循环（**所有会话的 SSE 一起停**）。
        data = await asyncio.to_thread(resolved.read_bytes)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"读取图片失败：{exc}") from exc

    # no-store：图片内容会变（用户重新生成图表），而缓存一份旧图比多读一次磁盘糟糕得多。
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})
