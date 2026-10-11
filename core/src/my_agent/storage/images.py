"""图片 → data URL：**全项目唯一一份**实现（消息附图与搭子头像共用）。

## 为什么一律转成 data URL

``AssistantProfile.avatar`` 从第一天起就是这个契约（见 ``config/schemas.py`` 的注释：
"用 data URL 而不是文件路径"），消息附图也一样（``llm/base.ImagePart``）。
换成文件路径不行：渲染层那张 ``<img>`` 发不出带鉴权的请求，界面上直接是个破图。

## 为什么不做缩放（以及超限了怎么办）

核心**故意不引入 Pillow**（见 ``pyproject.toml``：PyInstaller 打包体积与启动时间是
交付预算里的大头，当初连 pandas / matplotlib 都为此剔掉了），也**不从这个进程里去
拉 PowerShell / 系统绘图 API** —— 那等于让核心去启动一个外部解释器，对杀软的启发式
来说是极差的信号（本项目刚为一次误判排查了很久，不值得再添一个）。

所以这里只做四件事：**读 → 校验格式 → 限大小 → base64**。超限**明确报错并说清上限**，
由调用方原样转告用户（用户口径："最不能接受静默降级"）。悄悄截断或降质会让
"为什么这个头像这么糊"变成永远查不出来的悬案。

## 绝不打日志

data URL 动辄几 MB，一句 ``logger.debug("...%s", data_url)`` 就能把日志撑爆
—— ``llm/base.ImagePart`` 已经为同一个坑把自己的字段设成了 ``repr=False``。
这里所有异常信息只说"来源 + 原因"，**绝不带 base64**。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from ..utils.http import async_client

# 支持的格式。与消息附图共用同一份清单：两处能收的格式不一致的话，
# "这张图能发给模型、却不能当头像"会变成一个没人能解释的行为差异。
ALLOWED_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})

_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


class ImageSourceError(ValueError):
    """取图 / 校验失败。

    ``str(exc)`` 就是**能直接给用户看**的中文原因（调用方几乎都是原样转出去，
    所以这里写文案时按"用户会读"的标准写，别写开发注释）。
    """


def guess_image_mime(filename: str) -> str:
    """按后缀猜 mime；猜不出按 png。

    ⚠️ 这只是**兜底**。判断真实格式请用 :func:`sniff_image_mime`。
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_MIME.get(suffix, "image/png")


def sniff_image_mime(raw: bytes) -> str | None:
    """按**魔数**判真实格式；认不出来返回 ``None``。

    为什么不看后缀或上传时声明的 mime：模型给的图片链接常常没有后缀，而上传件的
    mime 是客户端说了算的。拿一个其实是 webp、名字却叫 .png 的文件当 png 用，
    界面上就是破图，而且**谁都不会想到去查这个**。
    """
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
    """下载图片，**边下边数**，一超上限立刻断开。

    不先整份读进内存再判断：那样一个指向大文件的链接就能把内存和等待时间都吃掉
    （而对手方往往只是个写错的链接）。

    ## 走 ``utils.http`` 的统一入口

    不要直接写 ``httpx.AsyncClient(...)``：Windows 上每建一个都要重新加载系统证书库
    （实测每次约 500ms，见 ``utils/http.py`` 的模块说明），项目已明文禁止。

    ## 取图**不走系统代理**（``trust_env=False``）

    与模型适配器同一取舍，理由也在那边写着：Windows 上 httpx 会通过
    ``urllib.request.getproxies()`` 读**注册表**里的系统代理（不只是环境变量），
    且对 127.0.0.1 不做豁免 —— 企业网络里配了代理很常见（很多科学上网工具也会留下
    一条），结果是"贴一个图片链接当头像"直接失败，报错还是代理返回的 502，
    排查方向完全错（本机实测就是 502）。

    这里没有"按用户配置决定要不要代理"的入口（头像只是一次性取一张小图），
    所以取更稳的那一侧：**默认直连**。
    """
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
        # 异常原文可能是很长的底层报文，截断一下但仍保留关键信息
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
    """把三种来源统一读成字节，返回 ``(字节, 来源说明)``。

    三种来源就是用户能给的三种：**http(s) 链接 / 本机路径 / 上传件的 id**。

    上传件与本地文件**怎么区分**：先按上传件查（``workspace.get``），查到就用；
    查不到当本地路径处理。两者可能同名（都叫 ``头像.png``），所以查不到时给出的
    报错会**把两种可能都说出来** —— 只报一种的话，用户拿着另一条路会反复试。
    """
    text = (source or "").strip()
    if not text:
        raise ImageSourceError("没有给图片来源。")

    if text.lower().startswith(("http://", "https://")):
        return await _bytes_from_url(text, limit=limit), "链接"

    if workspace is not None:
        try:
            record = await workspace.get(text)
        except Exception:  # noqa: BLE001 - 查询失败按"不是上传件"继续
            record = None
        if record is not None:
            try:
                path = workspace.resolve(record.id, record.kind)
            except Exception as exc:  # noqa: BLE001
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
    """校验并编码，返回 ``(mime, data_url)``。"""
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
    """一站式：来源 → ``(mime, data_url)``。失败抛 :class:`ImageSourceError`。"""
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
