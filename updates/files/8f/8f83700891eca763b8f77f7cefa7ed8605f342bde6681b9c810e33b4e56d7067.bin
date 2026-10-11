# -*- coding: utf-8 -*-
"""目标解析：把「链接 / 短链 / 24位ID / 昵称」统一解析成 uid + xsec_token + 昵称。

小红书主页 URL 必须带 `xsec_token`（一次性访问凭证）才能正常打开，
解析阶段会尽量从原始链接、笔记详情页、搜索结果页里把它一起捞出来。

**为什么这里有这么多兜底**：搜索页是小红书最重的页面（图片/视频瀑布流），
加载超时是常态；一旦超时又把异常抛出去，整个抓取就崩了。所以：

- 解析**不抛异常**，失败返回 `resolved_by="xxx_timeout/empty"`，交给上层降级；
- 提供多条路径（正则 → 缓存 → 笔记页反查 → 搜索页），搜索页是最后手段；
- 搜索页加载前先屏蔽图片/媒体，页面体积砍掉大半。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from xhs_common import BASE, SKILL_DIR, log

UID_RE = re.compile(r"^[0-9a-fA-F]{24}$")
PROFILE_RE = re.compile(r"xiaohongshu\.com/user/profile/([0-9a-zA-Z]{16,32})")
TOKEN_RE = re.compile(r"xsec_token=([^&\s]+)")

#: 解析结果缓存。**放在技能目录下，不放 .runtime**（后者每次运行都会被清空）。
CACHE_FILE = SKILL_DIR / ".targets_cache.json"

#: 卡片选择器：搜索结果页与笔记详情页都能用
_PROFILE_ANCHOR = "a[href*='/user/profile/']"

#: 加载这类重页面时屏蔽的资源类型（图片/视频是大头）
_HEAVY_RESOURCES = ("image", "media", "font")


@dataclass
class Target:
    uid: str = ""
    nickname: str = ""
    xsec_token: str = ""
    profile_url: str = ""
    raw: str = ""
    resolved_by: str = ""
    note: str = field(default="")     # 解析备注（如"缓存命中""刷新后成功"）

    @property
    def ok(self) -> bool:
        return bool(self.uid)

    def url(self) -> str:
        if not self.uid:
            return ""
        if self.xsec_token:
            return f"{BASE}/user/profile/{self.uid}?xsec_token={self.xsec_token}&type=51"
        return f"{BASE}/user/profile/{self.uid}?type=51"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["profile_url"] = self.url()
        return data


# --------------------------------------------------------------------------- #
# 解析结果缓存（跳过搜索页的最省事办法）
# --------------------------------------------------------------------------- #
def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def load_cached(key: str) -> Target | None:
    """按原始输入（昵称/链接）取上次解析成功的 uid。

    `xsec_token` 是一次性短时效凭证，只在缓存**当天**才复用，
    隔天仅复用 uid（登录态下无 token 通常也能打开主页，靠通道降级兜底）。
    """
    item = _load_cache().get((key or "").strip())
    if not isinstance(item, dict) or not item.get("uid"):
        return None
    target = Target(uid=item.get("uid", ""), nickname=item.get("nickname", ""),
                    raw=key, resolved_by="cache")
    stamp = item.get("resolved_at", "")
    fresh = False
    try:
        fresh = (time.time() - time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))) < 86400
    except Exception:  # noqa: BLE001
        fresh = False
    if fresh:
        token = TOKEN_RE.search(item.get("profile_url", "") or "")
        if token:
            target.xsec_token = urllib.parse.unquote(token.group(1))
    target.note = f"缓存于 {stamp or '未知时间'}" + ("（含当日 token）" if fresh else "（仅 uid）")
    return target


def save_cached(key: str, target: Target) -> None:
    if not target.ok:
        return
    data = _load_cache()
    data[(key or "").strip()] = {
        "uid": target.uid,
        "nickname": target.nickname,
        "profile_url": target.profile_url or target.url(),
        "resolved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception as err:  # noqa: BLE001
        log.warning("目标缓存写入失败（不影响本次抓取）：%s", err)


def clear_cache() -> int:
    """清空解析缓存，返回被删除的条数。"""
    count = len(_load_cache())
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:  # noqa: BLE001
        pass
    return count


# --------------------------------------------------------------------------- #
# 分类与主入口
# --------------------------------------------------------------------------- #
def classify(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "empty"
    if "xiaohongshu.com" in raw or "xhslink" in raw:
        if "/user/profile/" in raw:
            return "profile_url"
        if "/explore/" in raw or "/discovery/item/" in raw:
            return "note_url"
        return "short_url"
    if UID_RE.match(raw):
        return "uid"
    return "nickname"


def _expand_short_url(url: str) -> str:
    """短链跳转还原（优先 curl_cffi 走真实 TLS 指纹，失败回退 requests）。"""
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome124", allow_redirects=True, timeout=20)
        return str(resp.url)
    except Exception:  # noqa: BLE001
        pass
    try:
        import requests
        resp = requests.get(url, allow_redirects=True, timeout=20,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                   "Chrome/131.0.0.0 Safari/537.36"})
        return str(resp.url)
    except Exception:  # noqa: BLE001
        return url


def resolve(raw: str, browser=None, use_cache: bool = True) -> Target:
    """主解析入口。

    路径按成本从低到高：
    正则/短链/uid → 本地缓存 → 笔记详情页反查作者 → 搜索页（最重，最后手段）。
    `browser` 为可选的 BrowserSession，昵称与笔记链接反查需要它。
    """
    raw = (raw or "").strip()
    kind = classify(raw)
    log.info("目标类型：%s  (%s)", kind, raw[:60])

    if kind == "empty":
        return Target(raw=raw, resolved_by="empty")

    if kind in ("profile_url", "note_url"):
        uid = PROFILE_RE.search(raw)
        token = TOKEN_RE.search(raw)
        if uid:
            return Target(uid=uid.group(1), xsec_token=token.group(1) if token else "",
                          raw=raw, resolved_by="regex")
        if kind == "note_url":
            # 笔记链接里没有 uid（/explore/<note_id>），但详情页有作者入口，
            # 反查作者比走搜索页轻得多
            if browser is None:
                return Target(raw=raw, resolved_by="unresolved_note_url")
            log.info("笔记链接不含 uid，改从详情页反查作者（比搜索页轻）")
            return _author_from_note(browser.page, raw)
        return Target(raw=raw, resolved_by="unresolved_profile_url")

    if kind == "short_url":
        expanded = _expand_short_url(raw)
        log.info("短链展开：%s", expanded[:100])
        uid = PROFILE_RE.search(expanded)
        token = TOKEN_RE.search(expanded)
        if uid:
            return Target(uid=uid.group(1), xsec_token=token.group(1) if token else "",
                          raw=raw, resolved_by="short_url_expand")
        if browser is not None:
            return _author_from_note(browser.page, expanded)
        return Target(raw=raw, resolved_by="short_url_no_profile")

    if kind == "uid":
        return Target(uid=raw, raw=raw, resolved_by="uid")

    # 昵称：先看缓存，再走搜索页
    if use_cache:
        cached = load_cached(raw)
        if cached is not None:
            log.info("命中解析缓存：%s -> %s（跳过搜索页）", raw, cached.uid)
            return cached

    if browser is None:
        from xhs_browser import BrowserSession
        with BrowserSession(mode="persistent", headless=False) as session:
            return _search_user(session.page, raw)
    return _search_user(browser.page, raw)


# --------------------------------------------------------------------------- #
# 浏览器路径：搜索页 / 笔记页
# --------------------------------------------------------------------------- #
def _reload(page, timeout_ms: int) -> bool:
    """刷新页面，失败返回 False（不抛）。"""
    try:
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1200)
        return True
    except Exception as err:  # noqa: BLE001
        log.warning("刷新页面失败：%s", str(err)[:100])
        return False


def _collect_profile_anchors(page, keyword: str) -> list[Target]:
    """从当前页面里抓所有指向个人主页的链接，包装成候选 Target。"""
    try:
        anchors = page.query_selector_all(_PROFILE_ANCHOR)
    except Exception:  # noqa: BLE001
        return []

    candidates: list[Target] = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
        except Exception:  # noqa: BLE001
            continue
        m = PROFILE_RE.search(href)
        if not m:
            continue
        t = TOKEN_RE.search(href)
        full = href if href.startswith("http") else BASE + href
        try:
            name = (a.inner_text() or "").strip().split("\n")[0]
        except Exception:  # noqa: BLE001
            name = ""
        candidates.append(Target(uid=m.group(1), nickname=name,
                                 xsec_token=urllib.parse.unquote(t.group(1)) if t else "",
                                 profile_url=full, raw=keyword, resolved_by="search"))
    return candidates


def _pick(candidates: list[Target], keyword: str) -> Target:
    exact = [c for c in candidates
             if c.nickname and c.nickname.strip().lower() == keyword.strip().lower()]
    picked = exact[0] if exact else candidates[0]
    if not picked.nickname:
        picked.nickname = keyword
    log.info("命中：%s -> %s（%s）", keyword, picked.uid,
             "昵称精确匹配" if exact else "取首个结果，请核对")
    return picked


def _search_user(page, keyword: str, timeout_ms: int = 30000, retries: int = 1) -> Target:
    """在搜索页按昵称找人，优先取用户 tab（type=51）的卡片。

    四道保险，专门对付「搜索页极重、加载超时」：

    1. **屏蔽图片/媒体/字体** —— 瀑布流的大头就是这些，屏蔽后加载快很多；
    2. **不等整页** —— `domcontentloaded` + 显式等用户卡片出现，各自带超时；
    3. **超时/无结果 → 刷新重试** `retries` 次；
    4. **不抛异常** —— 失败返回 `search_timeout` / `search_empty`，由上层降级。
    """
    import urllib.parse as up
    from xhs_browser import human_scroll, is_password_protected

    url = (f"{BASE}/search_result?keyword={up.quote(keyword)}"
           f"&type=51&source=web_search_result_notes")

    def _block(route):
        try:
            if route.request.resource_type in _HEAVY_RESOURCES:
                return route.abort()
        except Exception:  # noqa: BLE001
            pass
        return route.continue_()

    routed = False
    try:
        page.route("**/*", _block)
        routed = True
        log.info("已屏蔽图片/媒体资源，为搜索页减负")
    except Exception as err:  # noqa: BLE001
        log.warning("无法设置资源屏蔽（忽略）：%s", str(err)[:80])

    candidates: list[Target] = []
    try:
        for attempt in range(1, retries + 2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as err:  # noqa: BLE001
                log.warning("搜索页加载超时（第 %s/%s 次）：%s",
                            attempt, retries + 1, str(err)[:100])
                if attempt <= retries:
                    _reload(page, timeout_ms)
                    continue
                return Target(raw=keyword, resolved_by="search_timeout")

            # 搜索页水合慢：给用户卡片 15 秒，拿不到也继续（可能是真的没结果）
            try:
                page.wait_for_selector(_PROFILE_ANCHOR, timeout=15000)
            except Exception:  # noqa: BLE001
                log.warning("搜索结果未渲染出用户卡片（第 %s 次）", attempt)

            if is_password_protected(page):
                log.warning("搜索页撞到登录墙，结果可能不完整")
            human_scroll(page, times=1)

            candidates = _collect_profile_anchors(page, keyword)
            if candidates:
                break
            if attempt <= retries:
                log.info("搜索无结果，刷新页面重试（%s/%s）", attempt, retries)
                _reload(page, timeout_ms)
    finally:
        if routed:
            try:
                page.unroute("**/*", _block)
            except Exception:  # noqa: BLE001
                pass

    if not candidates:
        return Target(raw=keyword, resolved_by="search_empty")
    return _pick(candidates, keyword)


def _author_from_note(page, note_url: str, timeout_ms: int = 30000) -> Target:
    """从笔记详情页反查作者 —— 搜索页超时的**首选替代路径**，页面轻得多。"""
    try:
        page.goto(note_url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as err:  # noqa: BLE001
        log.warning("笔记页加载超时：%s", str(err)[:100])
        return Target(raw=note_url, resolved_by="note_timeout")

    try:
        page.wait_for_selector(_PROFILE_ANCHOR, timeout=12000)
    except Exception:  # noqa: BLE001
        pass

    hits = _collect_profile_anchors(page, note_url)
    if not hits:
        return Target(raw=note_url, resolved_by="note_no_author")
    picked = hits[0]
    picked.resolved_by = "note_author"
    log.info("从笔记详情反查到作者：%s（%s）", picked.uid, picked.nickname or "未知昵称")
    return picked
