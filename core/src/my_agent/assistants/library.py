"""官网搭子库的门面：查清单、把包拉下来导入。

## 为什么单独一层

技能**拿不到 runtime**（设计如此：技能通过 ``ctx.service("xxx")`` 拿门面，
"这个技能到底改了什么"才始终有界）。而"从官网导入一个搭子"既要联网、又要落盘，
所以照 ``team`` / ``tasks`` 的老样子抽一层门面出来，由 runtime 注入。

## 用户定的流程（2026-09-28）

> AI 要新建搭子 / 建群之前，**先看官网有没有合适的**：有就下载导入并装技能包；
> 没有才自己建。

所以 ``list_available()`` 除了返回清单，还会把 ``checked`` 置位 —— 建搭子/建群的
闸门看的就是它（见 ``agent/orchestrator.py``）。**这一步绕不过去**，
但"查不到/连不上"不阻断建：只要求 AI 如实说出"官网没查到，我自己建"。

## 清单是怎么拿到的（2026-09-28 二次改版口径）

官网页面（``/buddy.html``）的卡片结构是规则的 **`<h4>搭子名</h4>` +
`<p>简介</p>` + `<a href="….zip">`** 三段式（页面为纯静态 HTML，无 JS 渲染）。
2026-09-28 页面改版后**只剩 .zip 搭子包/群包链接、没有任何 .json**，旧的
"逐个拉 .json 读元数据"口径直接匹配为空 —— 用户看到的正是 ``count: 0``。

新口径（用户原话："抓取的时候不能读网页上搭子/群的简介吗？有合适的才拉包"）：

- **列清单只解析页面**：名字与简介直接取自卡片（页面上是什么就列什么），
  **全程不下载任何包** —— AI 挑中合适的才在导入时拉包，省流量也更快；
- 搭子包与**群包**按链接路径（``/downloads/group/``）区分，群包单独放在
  ``groups`` 里并如实说明，不混进 ``buddies``（两者的导入语义不同）；
- **导入时才以包为准**：``buddy_import`` 拉下 zip/json 后按包内字段落盘，
  页面文案与包内容万一不一致，导入的结果仍然是准确的。

解析刻意写得**宽进**（不依赖 class 名，只认 h4/p/a 的相对位置）：页面换皮
（改样式类名）不影响解析；连结构都变了时，回退用文件名 stem 当名字，
绝不让整份清单因为一张卡解析不动而失败。
"""

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

# 页面上的下载链接（相对或绝对）：搭子包 / 群包是 .zip，旧版页面是 .json
_LINK = re.compile(r"""<a\s[^>]*href\s*=\s*["']([^"'#?]+\.(?:zip|json))["']""", re.IGNORECASE)
# 卡片三段式里的名字与简介（结构见模块说明；用 DOTALL 容忍属性换行）
_H4 = re.compile(r"<h4[^>]*>(.*?)</h4>", re.IGNORECASE | re.DOTALL)
_P = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def _fetch(url: str) -> bytes:
    """拉一个地址的字节。失败时抛出**能看懂**的原因（不是 URLError 堆栈）。"""
    request = urllib.request.Request(
        url,
        headers={
            # 默认的 python-urllib UA 会被一些站点直接拒掉
            "User-Agent": "SoulmateAgent/1.0 (+buddy-library)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as exc:
        raise TransferError(f"下载失败（HTTP {exc.code}）：{url}") from exc
    except urllib.error.URLError as exc:
        raise TransferError(f"连不上 {url}：{exc.reason}") from exc
    except TimeoutError as exc:
        raise TransferError(f"下载超时（{_FETCH_TIMEOUT:.0f} 秒）：{url}") from exc


def _text(fragment: str) -> str:
    """剥掉标签 + 还原实体 + 压掉多余空白，得到给模型/用户看的纯文本。"""
    return " ".join(_TAG.sub(" ", _html.unescape(fragment)).split())


def _card_meta(segment: str, fallback: str) -> tuple[str, str]:
    """从一个卡片段落里取（名字，简介）。

    ``segment`` 是"上一个下载链接之后、当前下载链接之前"的那段 HTML ——
    页面结构是 h4 → p → a，所以段内**最后一个 h4** 是这张卡的名字，
    h4 之后**最近的 p** 是简介。取不到时回退文件名 stem / 空串。
    """
    name = fallback
    description = ""
    heads = list(_H4.finditer(segment))
    if heads:
        name = _text(heads[-1].group(1)) or fallback
        after = [item for item in _P.finditer(segment) if item.start() > heads[-1].start()]
        if after:
            description = _text(after[0].group(1))
    else:
        # 老式页面没有 h4：能捞到一个 p 就当简介，名字退回文件名
        paragraphs = list(_P.finditer(segment))
        if paragraphs:
            description = _text(paragraphs[-1].group(1))
    return name, description


def _is_group(url: str) -> bool:
    """群包与搭子包按链接路径区分（官网把群包放在 /downloads/group/ 下）。"""
    return "/group/" in urlparse(url).path


class BuddyLibrary:
    """官网搭子库。由 runtime 构造并注入给技能（``ctx.service("buddy")``）。"""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        # 本轮有没有查过官网 —— 建搭子/建群的闸门看它（见模块说明）
        self.checked = False
        # 上次查询的真实结果（查失败时闸门要让 AI 说明原因，而不是假装查过）
        self.last_error = ""

    # ------------------------------------------------------------------ #
    # 查
    # ------------------------------------------------------------------ #
    @property
    def line(self) -> str:
        return str(getattr(self._runtime, "line", "") or "cn")

    def url(self) -> str:
        return library_url(self.line)

    def list_available(self) -> dict[str, Any]:
        """查官网搭子库里有哪些搭子。**同步、且只抓一次页面、不下载任何包**。"""
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

        # 逐个下载链接向前回看一张卡（h4 名字 + p 简介）；全程**零包下载** ——
        # 页面上是什么就列什么，包内容等导入时再以包为准（见模块说明）。
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

    # ------------------------------------------------------------------ #
    # 导
    # ------------------------------------------------------------------ #
    def _read(self, source: str) -> bytes:
        if source.startswith(("http://", "https://")):
            return _fetch(source)
        path = Path(source)
        if not path.is_file():
            raise TransferError(f"找不到这个文件或地址：{source}")
        return path.read_bytes()

    def load_buddy(self, source: str) -> BuddyPackage:
        """把"一个来源"读成搭子包：既支持 URL，也支持本地路径。

        官网清单里给的是 **zip 包地址**（页面改版后不再有裸 json）；zip 里自带
        人设与技能包，``parse_buddy_package`` 直接解。裸 json（旧版官网/用户手头
        的导入文件）仍兼容：会顺手把它的 ``skill_pack`` 也拉下来 —— 官网上
        json 与技能包是两个文件，用户/AI 只给一个 json 时，技能包要能自动跟上
        （否则导入完搭子一个技能都没有）。
        """
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
                # 技能包拉不到不该让搭子也导不进来：如实记一笔，日志与返回体里都有
                logger.warning("搭子「%s」的技能包下载失败：%s", payload.name, exc)
        return BuddyPackage(buddy=payload, skill_packs=packs)

    def load_group(self, source: str) -> Any:
        return parse_group_package(self._read(source), "group")

    async def import_buddy(self, source: str, *, actor_id: str | None = None) -> dict[str, Any]:
        """导入一个搭子（URL 或本地路径）。落盘复用 ``transfer``，前端导入共用同一套。"""
        package = self.load_buddy(source)
        return await apply_buddy(self._runtime, package, actor_id=actor_id)

    async def import_group(self, source: str, *, actor_id: str | None = None) -> dict[str, Any]:
        """导入一个搭子群（URL 或本地路径）。"""
        package = self.load_group(source)
        return await apply_buddy_group(self._runtime, package, actor_id=actor_id)


__all__ = ["BuddyLibrary"]
