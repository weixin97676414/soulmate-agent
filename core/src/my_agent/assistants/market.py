








































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



MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 15.0
CONNECT_TIMEOUT = 8.0


class MarketError(ConfigError):






    code = "market_error"
    http_status = 400


@dataclass(frozen=True)
class MarketEntry:


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

    validate_endpoint(url, field=field)

    async with async_client(
        timeout=httpx.Timeout(TIMEOUT, connect=CONNECT_TIMEOUT)
    ) as client:
        try:
            
            
            
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

    return parse_index(await _read_json(source, field="集市地址"))


async def fetch_pack(url: str) -> dict[str, Any]:

    raw = await _read_json(url, field="助手包地址")
    if not isinstance(raw, dict):
        raise MarketError("助手包顶层必须是对象。")
    if not isinstance(raw.get("assistants"), list):
        raise MarketError(
            "助手包里没有 assistants 列表。请确认这个地址指向的是从本应用导出的助手文件。"
        )
    return raw
