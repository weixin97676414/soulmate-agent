





































from __future__ import annotations

import html as _html
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..config.lines import library_url
from .transfer import (
    BuddyPackage,
    TransferError,
    apply_buddy,
    apply_buddy_group,
    parse_buddy_json,
    parse_buddy_package,
    parse_group_package,
)

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 20.0


_LINK = re.compile(r"""<a\s[^>]*href\s*=\s*["']([^"'#?]+\.(?:zip|json))["']""", re.IGNORECASE)

_H4 = re.compile(r"<h4[^>]*>(.*?)</h4>", re.IGNORECASE | re.DOTALL)
_P = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def _fetch(url: str) -> bytes:

    request = urllib.request.Request(
        url,
        headers={
            
            "User-Agent": "SoulmateAgent/1.0 (+buddy-library)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT) as response:  
            return response.read()
    except urllib.error.HTTPError as exc:
        raise TransferError(f"下载失败（HTTP {exc.code}）：{url}") from exc
    except urllib.error.URLError as exc:
        raise TransferError(f"连不上 {url}：{exc.reason}") from exc
    except TimeoutError as exc:
        raise TransferError(f"下载超时（{_FETCH_TIMEOUT:.0f} 秒）：{url}") from exc


def _text(fragment: str) -> str:

    return " ".join(_TAG.sub(" ", _html.unescape(fragment)).split())


def _card_meta(segment: str, fallback: str) -> tuple[str, str]:






    name = fallback
    description = ""
    heads = list(_H4.finditer(segment))
    if heads:
        name = _text(heads[-1].group(1)) or fallback
        after = [item for item in _P.finditer(segment) if item.start() > heads[-1].start()]
        if after:
            description = _text(after[0].group(1))
    else:
        
        paragraphs = list(_P.finditer(segment))
        if paragraphs:
            description = _text(paragraphs[-1].group(1))
    return name, description


def _is_group(url: str) -> bool:

    return "/group/" in urlparse(url).path


class BuddyLibrary:


    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        
        self.checked = False
        
        self.last_error = ""

    
    
    
    @property
    def line(self) -> str:
        return str(getattr(self._runtime, "line", "") or "cn")

    def url(self) -> str:
        return library_url(self.line)

    def list_available(self) -> dict[str, Any]:

        page_url = self.url()
        try:
            page = _fetch(page_url).decode("utf-8", errors="replace")
        except TransferError as exc:
            self.checked = True
            self.last_error = str(exc)
            return {
                "ok": False,
                "line": self.line,
                "url": page_url,
                "buddies": [],
                "groups": [],
                "message": (
                    f"读取官网搭子库失败：{exc}。"
                    "**你可以继续用 team_create_assistant 自己建**，"
                    "但要在回复里说明「官网未查到（失败原因），将自行创建」，不要假装查过。"
                ),
            }

        
        
        buddies: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        seen: set[str] = set()
        cursor = 0
        for match in _LINK.finditer(page):
            url = urljoin(page_url, match.group(1))
            if url in seen:
                continue
            seen.add(url)
            stem = Path(urlparse(url).path).stem
            name, description = _card_meta(page[cursor : match.start()], stem)
            entry = {"package_url": url, "name": name, "description": description}
            (groups if _is_group(url) else buddies).append(entry)
            cursor = match.end()

        self.checked = True
        self.last_error = ""
        message = (
            "这是官网搭子库当前可导入的清单（名字与简介取自页面，导入时以包内文件为准）。"
            "**先看有没有合适的**：有就用 buddy_import 传它的 package_url 导入"
            "（人设、人格、技能会一起落好）；一个都没有合适的，再用 "
            "team_create_assistant 自己建。"
            if buddies
            else "官网页面上没找到可导入的搭子（可能页面结构变了）。"
            "可以继续自己建，但要说清「官网没有」，不要假装查过。"
        )
        if groups:
            message += (
                f" 另有 {len(groups)} 个**搭子群包**（几个人一个包），"
                "要用群就用 buddy_group_import 传它的 package_url。"
            )
        return {
            "ok": True,
            "line": self.line,
            "url": page_url,
            "count": len(buddies),
            "buddies": buddies,
            "groups": groups,
            "message": message,
        }

    
    
    
    def _read(self, source: str) -> bytes:
        if source.startswith(("http://", "https://")):
            return _fetch(source)
        path = Path(source)
        if not path.is_file():
            raise TransferError(f"找不到这个文件或地址：{source}")
        return path.read_bytes()

    def load_buddy(self, source: str) -> BuddyPackage:








        raw = self._read(source)
        if raw.lstrip()[:1] != b"{":
            return parse_buddy_package(raw, Path(urlparse(source).path).stem or "buddy")

        payload = parse_buddy_json(raw)
        packs: list[tuple[str, bytes]] = []
        if payload.skill_pack and source.startswith(("http://", "https://")):
            pack_url = urljoin(source, payload.skill_pack)
            try:
                packs.append((Path(payload.skill_pack).stem, _fetch(pack_url)))
            except TransferError as exc:
                
                logger.warning("搭子「%s」的技能包下载失败：%s", payload.name, exc)
        return BuddyPackage(buddy=payload, skill_packs=packs)

    def load_group(self, source: str) -> Any:
        return parse_group_package(self._read(source), "group")

    async def import_buddy(self, source: str, *, actor_id: str | None = None) -> dict[str, Any]:

        package = self.load_buddy(source)
        return await apply_buddy(self._runtime, package, actor_id=actor_id)

    async def import_group(self, source: str, *, actor_id: str | None = None) -> dict[str, Any]:

        package = self.load_group(source)
        return await apply_buddy_group(self._runtime, package, actor_id=actor_id)


__all__ = ["BuddyLibrary"]
