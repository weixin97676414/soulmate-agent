# -*- coding: utf-8 -*-












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


CACHE_FILE = SKILL_DIR / ".targets_cache.json"


_PROFILE_ANCHOR = "a[href*='/user/profile/']"


_HEAVY_RESOURCES = ("image", "media", "font")


@dataclass
class Target:
    uid: str = ""
    nickname: str = ""
    xsec_token: str = ""
    profile_url: str = ""
    raw: str = ""
    resolved_by: str = ""
    note: str = field(default="")     

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





def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  
        pass
    return {}


def load_cached(key: str) -> Target | None:





    item = _load_cache().get((key or "").strip())
    if not isinstance(item, dict) or not item.get("uid"):
        return None
    target = Target(uid=item.get("uid", ""), nickname=item.get("nickname", ""),
                    raw=key, resolved_by="cache")
    stamp = item.get("resolved_at", "")
    fresh = False
    try:
        fresh = (time.time() - time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))) < 86400
    except Exception:  
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
    except Exception as err:  
        log.warning("目标缓存写入失败（不影响本次抓取）：%s", err)


def clear_cache() -> int:

    count = len(_load_cache())
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:  
        pass
    return count





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

    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome124", allow_redirects=True, timeout=20)
        return str(resp.url)
    except Exception:  
        pass
    try:
        import requests
        resp = requests.get(url, allow_redirects=True, timeout=20,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                   "Chrome/131.0.0.0 Safari/537.36"})
        return str(resp.url)
    except Exception:  
        return url


def resolve(raw: str, browser=None, use_cache: bool = True) -> Target:






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





def _reload(page, timeout_ms: int) -> bool:

    try:
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1200)
        return True
    except Exception as err:  
        log.warning("刷新页面失败：%s", str(err)[:100])
        return False


def _collect_profile_anchors(page, keyword: str) -> list[Target]:

    try:
        anchors = page.query_selector_all(_PROFILE_ANCHOR)
    except Exception:  
        return []

    candidates: list[Target] = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
        except Exception:  
            continue
        m = PROFILE_RE.search(href)
        if not m:
            continue
        t = TOKEN_RE.search(href)
        full = href if href.startswith("http") else BASE + href
        try:
            name = (a.inner_text() or "").strip().split("\n")[0]
        except Exception:  
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









    import urllib.parse as up
    from xhs_browser import human_scroll, is_password_protected

    url = (f"{BASE}/search_result?keyword={up.quote(keyword)}"
           f"&type=51&source=web_search_result_notes")

    def _block(route):
        try:
            if route.request.resource_type in _HEAVY_RESOURCES:
                return route.abort()
        except Exception:  
            pass
        return route.continue_()

    routed = False
    try:
        page.route("**/*", _block)
        routed = True
        log.info("已屏蔽图片/媒体资源，为搜索页减负")
    except Exception as err:  
        log.warning("无法设置资源屏蔽（忽略）：%s", str(err)[:80])

    candidates: list[Target] = []
    try:
        for attempt in range(1, retries + 2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as err:  
                log.warning("搜索页加载超时（第 %s/%s 次）：%s",
                            attempt, retries + 1, str(err)[:100])
                if attempt <= retries:
                    _reload(page, timeout_ms)
                    continue
                return Target(raw=keyword, resolved_by="search_timeout")

            
            try:
                page.wait_for_selector(_PROFILE_ANCHOR, timeout=15000)
            except Exception:  
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
            except Exception:  
                pass

    if not candidates:
        return Target(raw=keyword, resolved_by="search_empty")
    return _pick(candidates, keyword)


def _author_from_note(page, note_url: str, timeout_ms: int = 30000) -> Target:

    try:
        page.goto(note_url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as err:  
        log.warning("笔记页加载超时：%s", str(err)[:100])
        return Target(raw=note_url, resolved_by="note_timeout")

    try:
        page.wait_for_selector(_PROFILE_ANCHOR, timeout=12000)
    except Exception:  
        pass

    hits = _collect_profile_anchors(page, note_url)
    if not hits:
        return Target(raw=note_url, resolved_by="note_no_author")
    picked = hits[0]
    picked.resolved_by = "note_author"
    log.info("从笔记详情反查到作者：%s（%s）", picked.uid, picked.nickname or "未知昵称")
    return picked
