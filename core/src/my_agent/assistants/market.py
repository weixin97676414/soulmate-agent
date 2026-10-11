"""助手集市：从一个**可自托管**的索引地址浏览并安装助手。

## 为什么不做成"官方集市"

那意味着要长期运行一个服务，还要处理内容审核、可用性与版本兼容。而助手的本质
是**一小段 JSON**（系统提示词 + 技能白名单 + 模型偏好），用户完全可以把它放在
自己的 Gist、对象存储或内网静态服务上，分享给同事也只需要发个链接。

所以这里做的是「**索引地址可配置**」：官方的、团队的、自己的，填谁的都行。
默认留空 —— **不配置就不请求任何外部地址**。

## 索引与助手包的格式

索引（用户填的那个地址）::

    {
      "version": 1,
      "assistants": [
        {"id": "writer-pro", "name": "公文写作", "description": "...",
         "author": "某人", "url": "https://.../writer-pro.json"}
      ]
    }

助手包就是 ``/v1/assistants/export`` 导出的内容，格式完全一致 ——
这样"我自己导出一份、放到网上分享"和"从集市安装"用的是同一套东西。

## 安全

索引地址和每个助手包的 URL 都是**用户提供的外部地址**，所以走和模型端点
同一套校验（``security/urls.py``）：只允许 http/https、拒绝云元数据与链路本地
地址。另加两道：

1. **响应体大小上限** —— 一个被指向的地址可以无限吐数据，不设上限就是内存放大器；
2. **重定向后的地址也要校验** —— 允许 http→https 这类正常跳转，但跳转目标
   同样得过一遍。只校验初始地址的话，一个公开可访问的地址就能把我们跳到内网。

**残留风险**：``validate_endpoint`` 只能判断字面 IP，挡不住 DNS rebinding
（域名在解析时才指向内网）。这与模型端点的既有策略保持一致 —— 不在这里
另立一套标准，否则"两处防护强度不同"本身就是新的坑。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import ConfigError
from ..security.urls import validate_endpoint
from ..utils.http import async_client

logger = logging.getLogger(__name__)

# 索引与助手包都是小文件（几 KB 量级）。给 2 MB 已经很宽松了 ——
# 真超了说明要么源坏了，要么是故意在喂内存。
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 15.0
CONNECT_TIMEOUT = 8.0


class MarketError(ConfigError):
    """集市相关错误。继承 ConfigError 以便路由层统一转成 4xx。

    这些事情都是"用户填的地址/对方服务的问题"，不是本机故障 ——
    按 500 返回会让用户去查日志，而他要做的其实是改地址。
    """

    code = "market_error"
    http_status = 400


@dataclass(frozen=True)
class MarketEntry:
    """索引里的一条可安装项。"""

    id: str
    name: str
    url: str
    description: str = ""
    author: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "author": self.author,
        }


async def _read_json(url: str, *, field: str) -> Any:
    """取一个外部 JSON。校验、限时、限体积。"""
    validate_endpoint(url, field=field)

    async with async_client(
        timeout=httpx.Timeout(TIMEOUT, connect=CONNECT_TIMEOUT)
    ) as client:
        try:
            # httpx 的 timeout **不覆盖 DNS 解析**：一个解析极慢（或 DNS 黑洞）的
            # 域名会卡在这里几十秒，表现为「浏览」按钮一直转圈。用 wait_for
            # 把整段（含 DNS）都纳入超时，确保 15s 内一定返回。
            response = await asyncio.wait_for(
                client.get(url, follow_redirects=True), timeout=TIMEOUT
            )
        except TimeoutError as exc:
            raise MarketError(f"拉取 {field} 超时（{TIMEOUT} 秒）：{url}") from exc
        except httpx.HTTPError as exc:
            raise MarketError(f"无法访问 {field}：{exc}") from exc

        if response.status_code >= 400:
            raise MarketError(
                f"拉取 {field} 失败（HTTP {response.status_code}）：{url}"
            )

        # 重定向**之后**的地址也要过一遍校验。只验初始地址的话，
        # 一个公开可访问的地址就能把我们跳到内网去。
        final_url = str(response.url)
        if final_url != url:
            validate_endpoint(final_url, field=f"{field}（重定向后）")

        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise MarketError(f"{field} 体积过大（{declared} 字节），已拒绝。")

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_BYTES:
                # 不能只信 Content-Length：那个头可以撒谎，也可以缺失
                raise MarketError(f"{field} 体积超过 {MAX_BYTES // 1024 // 1024}MB 上限，已中断。")
            chunks.append(chunk)

    text = b"".join(chunks).decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MarketError(
            f"{field} 返回的不是合法 JSON。请确认填的是集市的索引地址，而不是网页地址。"
        ) from exc


def parse_index(raw: Any) -> list[MarketEntry]:
    """把索引内容收敛成条目列表。

    **逐条跳过坏的，而不是整批失败** —— 集市是别人维护的，里面偶尔有个
    URL 写错很正常。为一条坏数据让整个集市打不开，用户就没有别的办法了。
    """
    if not isinstance(raw, dict):
        raise MarketError("索引内容顶层必须是对象（含 assistants 列表）。")

    items = raw.get("assistants")
    if not isinstance(items, list):
        raise MarketError("索引里没有 assistants 列表。请确认填的是集市索引地址。")

    entries: list[MarketEntry] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "").strip()
        url = str(item.get("url") or "").strip()
        if not entry_id or not url or entry_id in seen:
            continue
        try:
            validate_endpoint(url, field=f"助手「{entry_id}」的地址")
        except ConfigError as exc:
            logger.warning("集市条目 %s 的地址不合法，已跳过: %s", entry_id, exc)
            continue
        seen.add(entry_id)
        entries.append(
            MarketEntry(
                id=entry_id,
                name=str(item.get("name") or entry_id).strip(),
                url=url,
                description=str(item.get("description") or "").strip(),
                author=str(item.get("author") or "").strip(),
            )
        )
    return entries


async def fetch_index(source: str) -> list[MarketEntry]:
    """拉取并解析集市索引。"""
    return parse_index(await _read_json(source, field="集市地址"))


async def fetch_pack(url: str) -> dict[str, Any]:
    """拉取一个助手包（内容与 ``/export`` 的输出同构）。"""
    raw = await _read_json(url, field="助手包地址")
    if not isinstance(raw, dict):
        raise MarketError("助手包顶层必须是对象。")
    if not isinstance(raw.get("assistants"), list):
        raise MarketError(
            "助手包里没有 assistants 列表。请确认这个地址指向的是从本应用导出的助手文件。"
        )
    return raw
