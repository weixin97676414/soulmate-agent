# -*- coding: utf-8 -*-



























from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Callable

from xhs_common import (BASE, PROFILE_DIR, RateLimiter, STATE_FILE, ensure_runtime,
                        human_num, jitter, log, read_json, write_json)
from xhs_resolve import Target, resolve

API_RULES: list[tuple[str, re.Pattern]] = [
    
    ("user_posted", re.compile(r"/api/sns/web/v\d+/user_posted")),
    ("user_info", re.compile(r"/api/sns/web/v\d+/user/(otherinfo|selfinfo|self)|/api/sns/web/v\d+/user_info")),
    ("note_detail", re.compile(r"/api/sns/web/v\d+/(feed|note/detail)")),
    ("comments", re.compile(r"/api/sns/web/v\d+/comment/(page|list)")),
]

WALL_MARKERS = ("登录", "安全验证", "滑动验证", "异常访问", "请完成验证", "访问受限")



FULL_STALL_LIMIT = 8






_DUAL = {
    "liked_count": "likedCount",
    "collected_count": "collectedCount",
    "comment_count": "commentCount",
    "share_count": "shareCount",
    "note_id": "noteId",
    "display_title": "displayTitle",
    "tag_list": "tagList",
    "image_list": "imageList",
    "xsec_token": "xsecToken",
    "ip_location": "ipLocation",
    "user_id": "userId",
    "nick_name": "nickName",
}


def pick(d: dict, key: str, default=None):

    if not isinstance(d, dict):
        return default
    for name in (key, _DUAL.get(key, key)):
        if name in d and d[name] not in (None, "", [], {}):
            return d[name]
    return default


def _interact(card: dict, key: str) -> int:

    if not isinstance(card, dict):
        return 0
    info = pick(card, "interact_info")
    if info is None:                       
        info = card.get("interactInfo") or {}
    if not isinstance(info, dict):
        return 0
    if key in info:
        return human_num(info[key])
    camel = _DUAL.get(key)
    return human_num(info.get(camel)) if camel else 0


def pick_video(video: dict) -> tuple[str, int]:








    if not isinstance(video, dict):
        return "", 0

    def _from_stream(stream_obj: dict) -> str:





        if not isinstance(stream_obj, dict):
            return ""
        backup_best, backup_h = "", -1
        master_best, master_h = "", -1
        for bucket in stream_obj.values():
            if not isinstance(bucket, list):
                continue
            for entry in bucket:
                if not isinstance(entry, dict):
                    continue
                h = entry.get("height") or 0
                
                for bu in (entry.get("backupUrls") or entry.get("backup_urls") or []):
                    if isinstance(bu, str) and bu.startswith(("http://", "https://")) and h >= backup_h:
                        backup_best, backup_h = bu, h
                mu = entry.get("masterUrl") or entry.get("master_url")
                if isinstance(mu, str) and mu.startswith(("http://", "https://")) and h > master_h:
                    master_best, master_h = mu, h
        return backup_best or master_best

    url = _from_stream((video.get("media") or {}).get("stream") or {})

    if not url:
        mv2 = video.get("mediaV2") or video.get("media_v2")
        if isinstance(mv2, str) and mv2.strip():
            try:
                mv2 = json.loads(mv2)
            except Exception:  
                mv2 = None
        if isinstance(mv2, dict):
            url = _from_stream(mv2.get("stream") or (mv2.get("video") or {}).get("stream") or {})

    
    secs = 0
    capa = video.get("capa") or {}
    if isinstance(capa, dict):
        secs = int(capa.get("duration") or 0)
    if not secs:
        mv = (video.get("media") or {}).get("video") or {}
        if isinstance(mv, dict):
            secs = int(mv.get("duration") or 0)
    if not secs and isinstance(mv2, dict):
        secs = int((mv2.get("video") or {}).get("duration") or mv2.get("duration") or 0)

    return url, int(secs * 1000)


def normalize_note(item: dict, author: dict | None = None) -> dict:






    if not isinstance(item, dict):
        return {}
    card = pick(item, "note_card") or item.get("noteCard") or item
    if not isinstance(card, dict):
        card = {}
    note_id = (pick(card, "note_id") or pick(item, "note_id") or pick(item, "id")
               or item.get("noteId") or "")

    imgs = []
    for im in (pick(card, "image_list") or []):
        if not isinstance(im, dict):
            continue
        url = pick(im, "url_default") or im.get("url")
        if not url:
            info_list = pick(im, "info_list") or im.get("infoList") or []
            url = (info_list[0] if info_list else {}).get("url", "")
        if url:
            imgs.append({"url": url, "width": im.get("width"), "height": im.get("height")})

    cover_obj = card.get("cover") or {}
    cover = ""
    if isinstance(cover_obj, dict):
        cover = pick(cover_obj, "url_default") or ""
        if not cover:
            info_list = pick(cover_obj, "info_list") or cover_obj.get("infoList") or []
            for prefer in ("WB_DFT", "WB_PRV"):
                for entry in info_list:
                    if isinstance(entry, dict) and entry.get("imageScene") == prefer:
                        cover = entry.get("url", "")
                        break
                if cover:
                    break
            if not cover and info_list:
                cover = info_list[0].get("url", "")
    if not cover and imgs:
        cover = imgs[0]["url"]

    video_url, duration_ms = pick_video(card.get("video") or {})

    ts = card.get("time") or card.get("lastUpdateTime") or card.get("last_update_time") or 0
    token = pick(item, "xsec_token") or pick(card, "xsec_token") or ""

    if not isinstance(author, dict) or not author:
        author = card.get("user") or {}
    tags_raw = pick(card, "tag_list") or []
    return {
        "note_id": note_id,
        "type": "video" if card.get("type") == "video" or video_url else "normal",
        "title": (pick(card, "display_title") or card.get("title") or "").strip(),
        "desc": (card.get("desc") or "").strip(),
        "tags": [t.get("name", "") for t in tags_raw if isinstance(t, dict) and t.get("name")],
        "liked": _interact(card, "liked_count"),
        "collected": _interact(card, "collected_count"),
        "commented": _interact(card, "comment_count"),
        "shared": _interact(card, "share_count"),
        "cover": cover,
        "images": imgs,
        "video_url": video_url,
        "duration_ms": duration_ms,
        "timestamp": int(ts) if isinstance(ts, (int, float)) else 0,
        "ip_location": pick(card, "ip_location") or "",
        "xsec_token": token,
        "note_url": f"{BASE}/explore/{note_id}?xsec_token={token}" if token else f"{BASE}/explore/{note_id}",
        "author": {
            "user_id": pick(author, "user_id") or "",
            "nickname": pick(author, "nickname") or pick(author, "nick_name") or "",
            "avatar": author.get("avatar") or "",
        },
    }


def extract_initial_state(html: str) -> dict:

    idx = html.find("window.__INITIAL_STATE__")
    if idx < 0:
        return {}
    start = html.find("{", idx)
    if start < 0:
        return {}
    
    
    
    blob = re.sub(r"\bundefined\b", "null", html[start:])
    
    
    blob = re.sub(r"new\s+Map\(\s*\[?\s*\]?\s*\)", "{}", blob)
    blob = re.sub(r"new\s+Set\(\s*\[?\s*\]?\s*\)", "[]", blob)
    try:
        obj, _ = json.JSONDecoder().raw_decode(blob)
        return obj if isinstance(obj, dict) else {}
    except Exception:  
        return {}


def notes_from_state(state: dict) -> list[dict]:





    user = state.get("user") or {}
    raw = (user.get("notes") or user.get("postedNotes")
           or (state.get("notes") or {}).get("list") or [])
    flat: list[dict] = []
    for page in raw:
        if isinstance(page, list):
            flat.extend(x for x in page if isinstance(x, dict))
        elif isinstance(page, dict):
            flat.append(page)
    return flat


def profile_from_state(state: dict) -> dict:


    user = state.get("user") or {}
    page_data = user.get("userPageData") or {}
    if page_data.get("basicInfo"):
        return page_data
    return (user.get("userInfo") or user.get("info") or user)


def note_detail_from_state(state: dict, note_id: str = "") -> dict:





    if not isinstance(state, dict):
        return {}
    ndm = (state.get("note") or {}).get("noteDetailMap") or {}
    if not isinstance(ndm, dict) or not ndm:
        return {}

    entry = ndm.get(note_id) if note_id and note_id in ndm else list(ndm.values())[0]
    if not isinstance(entry, dict):
        return {}
    note = entry.get("note") or {}
    if not isinstance(note, dict) or not note:
        return {}

    video_url, duration_ms = pick_video(note.get("video") or {})
    interact = note.get("interactInfo") or note.get("interact_info") or {}

    def _num(snake: str, camel: str) -> int:
        return human_num(interact.get(snake, interact.get(camel)))

    images = []
    for im in (note.get("imageList") or note.get("image_list") or []):
        if not isinstance(im, dict):
            continue
        url = im.get("urlDefault") or im.get("url_default") or im.get("url") or ""
        if not url:
            for e in (im.get("infoList") or im.get("info_list") or []):
                if isinstance(e, dict) and e.get("url"):
                    url = e["url"]
                    break
        if url:
            images.append({"url": url, "width": im.get("width"), "height": im.get("height")})

    tags = [t.get("name", "") for t in (note.get("tagList") or note.get("tag_list") or [])
            if isinstance(t, dict) and t.get("name")]

    ts = note.get("time") or note.get("lastUpdateTime") or 0
    return {
        "note_id": note.get("noteId") or note.get("note_id") or note_id,
        "title": (note.get("title") or note.get("displayTitle") or "").strip(),
        "desc": (note.get("desc") or "").strip(),
        "tags": tags,
        "liked": _num("likedCount", "liked_count"),
        "collected": _num("collectedCount", "collected_count"),
        "commented": _num("commentCount", "comment_count"),
        "shared": _num("shareCount", "share_count"),
        "images": images,
        "video_url": video_url,
        "duration_ms": duration_ms,
        "timestamp": int(ts) if isinstance(ts, (int, float)) else 0,
        "ip_location": note.get("ipLocation") or note.get("ip_location") or "",
    }





class HttpChannel:
    name = "http"

    def __init__(self, cookie: str = "", out_dir: Path | None = None):
        self.cookie = cookie
        self.out_dir = out_dir
        self.limiter = RateLimiter(1.5, 3.5)

    def _get(self, url: str) -> str:
        from xhs_common import random_headers
        self.limiter.wait()
        headers = random_headers(self.cookie)
        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(url, headers=headers, impersonate="chrome124", timeout=25)
            if resp.status_code == 200:
                return resp.text
            log.warning("HTTP 通道状态码 %s", resp.status_code)
            return ""
        except ImportError:
            import requests
            resp = requests.get(url, headers=headers, timeout=25)
            return resp.text if resp.status_code == 200 else ""

    def available(self) -> bool:
        try:
            import curl_cffi  
            return True
        except Exception:  
            try:
                import requests  
                return True
            except Exception:  
                return False

    def fetch_profile(self, target: Target):
        html = self._get(target.url())
        if not html:
            return None, None, "http_empty"
        if any(m in html[:4000] for m in WALL_MARKERS) and "__INITIAL_STATE__" not in html:
            return None, None, "http_walled"
        state = extract_initial_state(html)
        if not state:
            return None, None, "http_no_state"
        profile = profile_from_state(state)
        raw_notes = notes_from_state(state)
        if not raw_notes:
            return profile, [], "http_no_notes"
        return profile, [normalize_note(n, profile) for n in raw_notes], "ok"

    def fetch_note_detail(self, note: dict, comments_limit: int = 0) -> tuple[dict, list[dict]]:







        url = note.get("note_url") or f"{BASE}/explore/{note.get('note_id')}"
        html = self._get(url)
        if not html:
            return {}, []
        if any(m in html[:4000] for m in WALL_MARKERS) and "__INITIAL_STATE__" not in html:
            return {}, []
        state = extract_initial_state(html)
        if not state:
            return {}, []
        detail = note_detail_from_state(state, note.get("note_id") or "")
        if not detail:
            return {}, []
        if self.out_dir:
            try:
                d = self.out_dir / "raw" / "notes"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{note.get('note_id')}.json").write_text(
                    json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:  
                pass
        return detail, []





class BrowserChannel:


    def __init__(self, mode: str = "persistent", cdp_port: int = 9222, headless: bool = False,
                 out_dir: Path | None = None):
        self.mode = mode
        self.cdp_port = cdp_port
        self.headless = headless
        self.out_dir = out_dir or Path(".")
        self.bucket: dict[str, list] = {k: [] for k, _ in API_RULES}
        self.session = None
        self.page = None
        self.api_dir = self.out_dir / "raw" / "api"
        self.api_dir.mkdir(parents=True, exist_ok=True)
        
        self.stop_reason = ""

    
    def __enter__(self):
        from xhs_browser import BrowserSession
        self.session = BrowserSession(mode=self.mode, headless=self.headless, cdp_port=self.cdp_port)
        self.session.__enter__()
        self.page = self.session.page
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc):
        if self.session:
            self.session.__exit__(*exc)
        return False

    
    def _on_response(self, response) -> None:
        url = response.url or ""
        for key, pattern in API_RULES:
            if not pattern.search(url):
                continue
            if response.status != 200:
                continue
            try:
                data = response.json()
            except Exception:  
                continue
            if not isinstance(data, dict) or data.get("success") is False:
                continue
            self.bucket[key].append(data)
            stamp = int(time.time() * 1000)
            write_json(self.api_dir / f"{key}_{stamp}_{random.randint(100, 999)}.json", data)
            return

    def reset(self, *keys: str) -> None:
        for k in (keys or tuple(self.bucket)):
            self.bucket[k] = []

    
    def fetch_profile(self, target: Target, limit: int = 0, max_scroll_rounds: int = 400,
                      window_ms: int = 0, pacer=None) -> tuple[dict, list[dict], str]:












        from xhs_antibot import guard
        from xhs_browser import human_scroll, is_password_protected
        self.reset("user_posted", "user_info")
        self.page.goto(target.url(), wait_until="domcontentloaded")
        self.page.wait_for_timeout(3000)

        if is_password_protected(self.page):
            return {}, [], "browser_walled"

        full = limit is None or limit <= 0
        cap = 10 ** 9 if full else limit
        stall_limit = FULL_STALL_LIMIT if full else 3

        stalled, seen, rounds = 0, 0, 0
        hit_window_edge = False
        while len(self._notes()) < cap and stalled < stall_limit and rounds < max_scroll_rounds:
            if pacer is not None:
                state = guard(self.page, pacer, label=f"滚动第 {rounds + 1} 轮")
                if state == "budget":
                    self.stop_reason = "budget_exhausted（滚动阶段）"
                    break
            human_scroll(self.page, times=2)
            rounds += 1
            current = len(self._notes())
            if current <= seen:
                stalled += 1
            else:
                stalled = 0
                seen = current
            if rounds % 10 == 0:
                log.info("  滚动中：第 %s 轮，累计 %s 条（连续无增量 %s/%s）",
                         rounds, current, stalled, stall_limit)
            if len(self._notes()) >= cap:
                break

            
            if window_ms > 0:
                stamps = [n.get("timestamp") or 0
                          for n in self._notes() if isinstance(n, dict)]
                oldest = min((s for s in stamps if s > 0), default=0)
                if oldest and oldest < window_ms:
                    hit_window_edge = True
                    log.info("  已滚到窗口边界（%s 之前的笔记不再采集），停止滚动",
                             time.strftime("%Y-%m-%d", time.localtime(window_ms / 1000)))
                    break

        if hit_window_edge:
            self.stop_reason = "window_edge（已覆盖设定的时间窗口）"
        elif rounds >= max_scroll_rounds:
            self.stop_reason = f"max_scroll_rounds（达到 {max_scroll_rounds} 轮上限）"
        elif stalled >= stall_limit:
            self.stop_reason = "no_more_notes（滚动到底）"

        profile = self._profile(target)
        notes = [normalize_note(n, profile) for n in self._notes()]

        if not notes:  
            state = extract_initial_state(self.page.content())
            if state:
                profile = profile or profile_from_state(state)
                notes = [normalize_note(n, profile) for n in notes_from_state(state)]

        if window_ms > 0 and notes:
            from xhs_antibot import in_window
            kept = [n for n in notes if in_window(n, window_ms)]
            if len(kept) != len(notes):
                log.info("  时间窗口过滤：保留 %s 条，丢弃 %s 条更早的笔记",
                         len(kept), len(notes) - len(kept))
            notes = kept
        
        
        return profile, (notes if (limit is None or limit <= 0) else notes[:limit]), \
            "ok" if notes else "browser_no_notes"

    def _extract_detail_dom(self, page, note_id: str) -> dict:








        
        
        for sel in ("#detail-desc", ".note-content", ".like-wrapper .count",
                    ".interact-container"):
            try:
                page.wait_for_selector(sel, timeout=6000)
                break
            except Exception:  
                continue

        def text_of(selector: str) -> str:
            try:
                el = page.query_selector(selector)
                return (el.inner_text() or "").strip() if el else ""
            except Exception:  
                return ""

        desc = text_of("#detail-desc") or text_of(".note-text") or text_of(".desc")
        tags = []
        try:
            for el in page.query_selector_all("a.tag, .tag, #detail-desc a"):
                t = (el.inner_text() or "").strip().lstrip("#").strip()
                if t and t not in tags and len(t) < 40:
                    tags.append(t)
        except Exception:  
            pass

        def count_of(selector: str) -> int:
            return human_num(text_of(selector))

        video_url = ""
        try:
            for sel in ("video source", "video"):
                el = page.query_selector(sel)
                if el:
                    src = el.get_attribute("src") or ""
                    if src.startswith("http"):
                        video_url = src
                        break
        except Exception:  
            pass

        
        
        
        if not video_url:
            try:
                entries = page.evaluate(
                    "() => performance.getEntriesByType('resource')"
                    ".map(e => ({name: e.name, size: e.encodedBodySize || 0}))")
                best_name, best_size = "", -1
                for e in entries or []:
                    name = (e or {}).get("name") or ""
                    if not name.startswith(("http://", "https://")):
                        continue
                    if ("sns-video" in name or ".mp4" in name
                            and "video-signal" not in name):
                        size = (e or {}).get("size") or 0
                        if size > best_size:
                            best_name, best_size = name, size
                if best_name:
                    video_url = best_name
            except Exception:  
                pass

        
        
        images: list[dict] = []
        seen_urls: set[str] = set()
        try:
            for el in page.query_selector_all(
                    ".media-container img, .swiper-slide img, .note-slider img, "
                    ".img-container img, .note-detail img"):
                src = el.get_attribute("src") or ""
                if not src.startswith(("http://", "https://")):
                    continue
                if "sns-avatar" in src or "/avatar" in src:   
                    continue
                if src in seen_urls:
                    continue
                seen_urls.add(src)
                images.append({"url": src,
                               "width": el.get_attribute("width"),
                               "height": el.get_attribute("height")})
        except Exception:  
            pass

        
        bottom = text_of(".bottom-container") or text_of(".date") or ""
        ip_location = ""
        m = re.search(r"IP[属地 locator]*[：:]\s*([^\s]+)", bottom)
        if m:
            ip_location = m.group(1)

        return {
            "note_id": note_id,
            "title": text_of("#detail-title") or text_of(".title"),
            "desc": desc,
            "tags": tags,
            "liked": count_of(".like-wrapper .count"),
            "collected": count_of(".collect-wrapper .count"),
            "commented": count_of(".chat-wrapper .count"),
            "shared": count_of(".share-wrapper .count"),
            "images": images,
            "video_url": video_url,
            "ip_location": ip_location,
            "date_text": bottom[:40],
        }

    def fetch_note_detail(self, note: dict, comments_limit: int = 100) -> tuple[dict, list[dict]]:
        from xhs_browser import human_scroll, is_password_protected
        self.reset("note_detail", "comments")
        url = note.get("note_url") or f"{BASE}/explore/{note.get('note_id')}"
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(2500)
        if is_password_protected(self.page):
            return {}, []

        
        detail = self._extract_detail_dom(self.page, note.get("note_id") or "")
        
        for item in self.bucket.get("note_detail", []):
            items = ((item.get("data") or {}).get("items") or [])
            for it in items:
                card = it.get("note_card") or it.get("noteCard") or {}
                nid = card.get("note_id") or card.get("noteId") or ""
                if not nid or nid == note.get("note_id"):
                    api_detail = normalize_note(it)
                    for key in ("images", "video_url", "duration_ms", "timestamp"):
                        if api_detail.get(key) and not detail.get(key):
                            detail[key] = api_detail[key]
                    break
            if detail.get("images"):
                break

        collected: dict[str, dict] = {}
        self._drain_comments(collected)
        
        
        
        
        hovered = False
        for sel in (".comments-el", ".comments-container", ".comments-wrapper",
                    ".comments-list", "[class*='comments']"):
            try:
                el = self.page.query_selector(sel)
                if not el:
                    continue
                box = el.bounding_box()
                if box and box.get("width") and box["width"] > 120:
                    self.page.mouse.move(
                        box["x"] + box["width"] * 0.5,
                        box["y"] + min(box["height"] * 0.5, 320))
                    hovered = True
                    break
            except Exception:  
                continue
        if not hovered:
            try:
                vp = self.page.viewport_size or {"width": 1440, "height": 900}
                self.page.mouse.move(vp["width"] * 0.78, vp["height"] * 0.5)
            except Exception:  
                pass
        stalled = 0
        while len(collected) < comments_limit and stalled < 4:
            before = len(collected)
            
            human_scroll(self.page, times=3, min_px=400, max_px=900, recenter=False)
            self._drain_comments(collected)
            if len(collected) <= before:
                stalled += 1
            else:
                stalled = 0
        return detail, list(collected.values())[:comments_limit]

    def _drain_comments(self, collected: dict) -> None:
        for payload in self.bucket.get("comments", []):
            for c in ((payload.get("data") or {}).get("comments") or []):
                cid = c.get("id")
                if not cid:
                    continue
                user = c.get("user_info") or {}
                collected[cid] = {
                    "id": cid,
                    "content": c.get("content", ""),
                    "like_count": human_num(c.get("like_count")),
                    "nickname": user.get("nickname", ""),
                    "user_id": user.get("user_id", ""),
                    "ip_location": c.get("ip_location", ""),
                    "create_time": c.get("create_time", 0),
                    "sub_comment_count": len(c.get("sub_comments") or c.get("sub_comment_list") or []),
                }
        self.bucket["comments"] = []

    
    def _notes(self) -> list[dict]:
        notes: list[dict] = []
        seen = set()
        for payload in self.bucket.get("user_posted", []):
            for n in ((payload.get("data") or {}).get("notes") or []):
                nid = (n.get("note_card") or n.get("noteCard") or {}).get("note_id") \
                    or (n.get("note_card") or n.get("noteCard") or {}).get("noteId") \
                    or n.get("note_id") or n.get("noteId")
                if nid and nid not in seen:
                    seen.add(nid)
                    notes.append(n)
        return notes

    def _profile(self, target: Target) -> dict:
        for payload in self.bucket.get("user_info", []):
            data = payload.get("data") or {}
            user = data.get("user")
            if user:
                return user
            
            
            
            if data.get("basic_info") or data.get("interactions"):
                flat = dict(data.get("basic_info") or {})
                flat["interactions"] = data.get("interactions") or []
                flat["tags"] = data.get("tags") or []
                return flat
        state = extract_initial_state(self.page.content())
        info = profile_from_state(state) if state else {}
        if info:
            return info
        return {"user_id": target.uid, "nickname": target.nickname}


def normalize_profile(profile: dict, target: Target) -> dict:






    profile = profile if isinstance(profile, dict) else {}
    
    basic = profile.get("basicInfo") or profile.get("basic_info") or {}
    if not isinstance(basic, dict):
        basic = {}

    
    counts: dict[str, int] = {}
    for entry in (profile.get("interactions") or []):
        if isinstance(entry, dict) and entry.get("type"):
            counts[entry["type"]] = human_num(entry.get("count"))
    inter = profile.get("interact_info") or profile.get("interaction") or {}
    if not isinstance(inter, dict):
        inter = {}

    tags_raw = profile.get("tags") or profile.get("tag_list") or []
    gender_raw = basic.get("gender", profile.get("gender"))
    
    
    gender = ""
    for t in tags_raw:
        icon = (t.get("icon") or "") if isinstance(t, dict) else ""
        if "gender-female" in icon:
            gender = "女"
            break
        if "gender-male" in icon:
            gender = "男"
            break
    if not gender:
        gender = {0: "未知", 1: "男", 2: "女"}.get(gender_raw, "")

    return {
        "user_id": (basic.get("user_id") or basic.get("userId") or profile.get("user_id")
                    or profile.get("id") or target.uid),
        "nickname": (basic.get("nickname") or profile.get("nickname")
                     or profile.get("nick_name") or target.nickname),
        "red_id": (basic.get("red_id") or basic.get("redId") or profile.get("red_id")
                   or profile.get("redId") or ""),
        "desc": basic.get("desc") or profile.get("desc") or "",
        "ip_location": (basic.get("ip_location") or basic.get("ipLocation")
                        or profile.get("ip_location") or profile.get("ipLocation") or ""),
        "gender": gender,
        "avatar": basic.get("imageb") or basic.get("images") or profile.get("avatar") or "",
        "fans": counts.get("fans") or human_num(profile.get("fans") or inter.get("fans") or 0),
        "follows": counts.get("follows") or human_num(profile.get("follows")
                                                      or profile.get("follow") or 0),
        "liked_and_collected": counts.get("interaction") or human_num(
            inter.get("liked_count") or profile.get("liked") or profile.get("interaction") or 0),
        "tags": [t.get("name") for t in tags_raw if isinstance(t, dict) and t.get("name")],
        "profile_url": target.url(),
        "source_input": target.raw,
    }





def crawl(args) -> dict:
    ensure_runtime()

    
    if getattr(args, "clear_target_cache", False):
        from xhs_resolve import clear_cache
        removed = clear_cache()
        log.info("目标解析缓存已清空（%s 条）。可重新运行抓取命令。", removed)
        return {"meta": {"action": "clear_target_cache", "removed": removed}}

    out_dir = Path(args.out).resolve()
    (out_dir / "raw" / "notes").mkdir(parents=True, exist_ok=True)
    (out_dir / "raw" / "comments").mkdir(parents=True, exist_ok=True)
    (out_dir / "media").mkdir(parents=True, exist_ok=True)

    from xhs_browser import cookie_header, has_login
    cookie = cookie_header()

    
    from xhs_antibot import HumanPacer, in_window, window_start_ms
    window_ms, window_label = window_start_ms(getattr(args, "months", 6),
                                              getattr(args, "since", ""))
    pacer = HumanPacer(getattr(args, "pace", "normal"))
    if window_ms:
        log.info("采集窗口：%s 之后发布的笔记（近 %s 个月）", window_label, args.months)
    else:
        log.warning("采集窗口：不限时间（--months 0）。请求量越大越容易触发风控，"
                    "建议保留默认窗口或改用 --pace slow")
    log.info("采集节奏：%s（单任务动作上限 %s 次）", pacer.level, pacer.budget)

    
    pre_session = _ensure_login(args)

    
    target, pre_session = _resolve_with_recovery(args, pre_session)

    if not target.ok:
        tips = [
            "1) 直接给**主页链接**（浏览器地址栏复制，带 xsec_token 最好）—— 最稳，不用搜索页；",
            "2) 给**该账号任意一篇笔记的链接**（/explore/...）—— 会从笔记页反查作者，比搜索页轻得多；",
            "3) 给 24 位用户 ID —— 无需任何页面加载；",
            "4) 增大重试次数与超时：--resolve-retries 3；",
            "5) 若确认缓存里的旧结果已失效：--no-target-cache 跳过缓存重新解析。",
        ]
        raise SystemExit(
            f"无法解析目标：{args.target}（最后状态：{target.resolved_by}）\n\n"
            "已尝试：解析 → 刷新页面重试 → 重启浏览器重新登录重试。仍失败，请换一种输入：\n"
            + "\n".join(tips)
        )
    write_json(out_dir / "raw" / "target.json", target.to_dict())
    log.info("目标：%s (uid=%s, token=%s, 解析方式：%s)",
             target.nickname or target.uid, target.uid,
             "有" if target.xsec_token else "无", target.resolved_by)

    
    
    
    tier_order = {
        "auto": ["persistent", "cdp", "http"],
        "http": ["http", "persistent", "cdp"],
        "persistent": ["persistent", "cdp", "http"],
        "cdp": ["cdp", "persistent", "http"],
    }[args.tier]

    if args.headless and not has_login():
        
        log.info("无头模式且未保存登录态，浏览器通道会被登录墙拦截，优先尝试 http")
        tier_order = ["http"] + [t for t in tier_order if t != "http"]

    profile, notes, used_tier = {}, [], ""
    stop_reason = ""                  
    failures: list[str] = []          
    for tier in tier_order:
        try:
            if tier == "http":
                if not has_login():
                    failures.append("http：未登录（本技能无免登录通道，必须先扫码/验证码登录）")
                    log.warning("通道 http 跳过：未登录")
                    continue
                if not target.xsec_token:
                    failures.append("http：缺少 xsec_token（主页链接需带该参数）")
                    log.warning("通道 http 跳过：缺少 xsec_token")
                    continue
                channel = HttpChannel(cookie, out_dir=out_dir)
                if not channel.available():
                    failures.append("http：依赖缺失（执行 bootstrap.py --install）")
                    log.warning("通道 http 跳过：依赖缺失")
                    continue
                profile, notes, status = channel.fetch_profile(target)
                if status == "ok" and notes:
                    used_tier = "http"
                    
                    
                    
                    
                    if args.detail_top >= 0:
                        try:
                            _fetch_details(channel, notes, args, out_dir, pacer=pacer)
                        except Exception as err:  
                            log.warning("http 详情采集失败（列表数据仍可用）：%s", str(err)[:120])
                    break
                failures.append(f"http：{status}")
                log.warning("通道 http 失败：%s", status)
            else:
                session = pre_session if pre_session is not None else _open_browser(args, mode=tier)
                channel = BrowserChannel(mode=session.mode, cdp_port=args.cdp_port,
                                         headless=args.headless, out_dir=out_dir)
                channel.session, channel.page = session, session.page
                channel.page.on("response", channel._on_response)
                try:
                    profile, notes, status = channel.fetch_profile(
                        target, args.limit, max_scroll_rounds=args.max_scroll_rounds,
                        window_ms=window_ms, pacer=pacer)
                    if status == "ok" and notes and args.detail_top >= 0:
                        
                        
                        
                        
                        if args.detail_top == 0:
                            log.info("详情采集：全部 %s 条（默认 detail_top=0）", len(notes))
                        else:
                            log.info("详情采集：点赞最高的前 %s 条", args.detail_top)
                        try:
                            _fetch_details(channel, notes, args, out_dir, pacer=pacer)
                        except Exception as err:  
                            log.warning("详情采集失败（列表数据仍可用）：%s", str(err)[:120])
                finally:
                    stop_reason = getattr(channel, "stop_reason", "") or stop_reason
                    if session is not pre_session:
                        session.__exit__(None, None, None)
                if status == "ok" and notes:
                    used_tier = tier
                    break
                failures.append(f"{tier}：{status}")
                log.warning("通道 %s 失败：%s", tier, status)
        except Exception as err:  
            failures.append(f"{tier}：异常 {str(err)[:120]}")
            log.warning("通道 %s 异常：%s", tier, str(err)[:160])
            continue

    
    
    stale_session = pre_session
    pre_session = None

    if not notes:
        detail = "\n".join(f"  · {f}" for f in failures) or "  · 无"
        walled = any("walled" in f or "登录" in f for f in failures)
        tips = [
            "1) 执行 `python xhs_login.py` 扫码登录后重试（最常见的原因就是没登录）；",
            "2) 或手动启动调试浏览器 `python xhs_browser.py open 9222`，"
            "登录后用 --tier cdp --cdp-port 9222 重试；",
            "3) 确认目标主页链接带 xsec_token（该凭证时效很短，需现复制现用）；",
            "4) 执行 `python bootstrap.py` 复查运行环境。",
        ]
        if walled:
            tips.insert(0, "0) 检测到登录墙 —— 小红书要求登录后才能看主页，先完成上面第 1 或第 2 步；")
        raise SystemExit(
            "全部通道均未取到数据。各通道情况：\n" + detail +
            "\n\n处置建议：\n" + "\n".join(tips)
        )

    log.info("通道：%s，取到笔记 %s 条", used_tier, len(notes))

    
    dropped = 0
    if window_ms > 0 and notes:
        before = len(notes)
        notes = [n for n in notes if in_window(n, window_ms)]
        dropped = before - len(notes)
        if dropped:
            log.info("时间窗口过滤：%s → %s 条（丢弃 %s 条早于 %s 的笔记）",
                     before, len(notes), dropped, window_label)
    if not notes:
        raise SystemExit(
            f"窗口内没有笔记（{window_label} 之后无内容）。\n"
            f"可调大窗口：--months 12，或用 --since YYYY-MM-DD 指定起点；\n"
            f"也可用 --months 0 不限时间（请求量大，更容易触发风控）。"
        )

    
    profile = normalize_profile(profile or {}, target)
    write_json(out_dir / "raw" / "profile.json", profile)
    write_json(out_dir / "raw" / "notes.json", notes)

    dataset = {
        "meta": {
            "target": target.to_dict(),
            "tier": used_tier,
            "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note_limit": args.limit,
            "full_crawl": args.limit <= 0,          
            "detail_top": args.detail_top,
            "detail_all": args.detail_top == 0,     
            "detail_skipped": args.detail_top < 0,  
            "comments_limit": args.comments,
            "window": {
                "months": getattr(args, "months", 6),
                "since": getattr(args, "since", ""),
                "start_ms": window_ms,
                "start_date": window_label or "不限",
                "dropped": dropped,
            },
            "pace": pacer.level,
            "pace_actions": pacer.actions,
            "stopped_reason": stop_reason or "completed",
            "skill": "xhs-account-deconstruct",
        },
        "profile": profile,
        "notes": notes,
    }
    _merge_details(out_dir, dataset)
    _data_quality_report(dataset)

    if args.media:
        try:
            from xhs_media import download_media
            stats = download_media(dataset, out_dir / "media", args.media_top)
            dataset["meta"]["media"] = stats
        except Exception as err:  
            log.warning("素材下载失败（不影响文本分析）：%s", err)
            dataset["meta"]["media"] = {"error": str(err)[:200]}

    dataset["notes"].sort(key=lambda n: n.get("timestamp") or 0, reverse=True)
    write_json(out_dir / "dataset.json", dataset)
    log.info("完成：%s", out_dir / "dataset.json")

    _close_session_safe(stale_session)
    return dataset


def _close_session_safe(session, timeout: int = 30) -> None:







    if session is None:
        return
    import threading

    try:
        session.save_state()
    except Exception:  
        pass

    def _close():
        try:
            session.context.close()
        except Exception:  
            pass

    t = threading.Thread(target=_close, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log.warning("浏览器会话关闭超时（%s 秒），数据已全部落盘；"
                    "残留的浏览器窗口可手动关闭，不影响结果。", timeout)


def _ensure_login(args):












    from xhs_browser import BrowserSession
    from xhs_common import reset_runtime

    reset_runtime(logger=log)

    
    if getattr(args, "tier", "auto") == "cdp":
        return _ensure_login_cdp(args)

    log.info("正在打开浏览器，请完成登录（历史登录态与缓存已清除，本次为全新登录）")
    args.headless = False                      
    session = BrowserSession(mode="persistent", headless=False)
    session.__enter__()
    try:
        from xhs_login import interactive_login
        ok = interactive_login(session.page, mode=getattr(args, "login", "qr"),
                               timeout=getattr(args, "login_timeout", 600))
    except Exception as err:  
        try:
            session.__exit__(None, None, None)
        except Exception:  
            pass
        raise SystemExit(f"登录流程异常：{err}")

    if not ok:
        try:
            session.__exit__(None, None, None)
        except Exception:  
            pass
        raise SystemExit(
            "登录未完成，抓取中止（本技能不提供免登录通道）。处置建议：\n"
            "  1) 重跑本命令，在弹出的浏览器窗口里完成扫码；\n"
            "  2) 换短信验证码方式：加 --login web；\n"
            "  3) 或手动开调试浏览器 `python xhs_browser.py open 9222`，登录后加 --tier cdp；\n"
            "  4) 想单独保存登录态可执行 `python xhs_login.py`（同样会先清空旧登录态）。"
        )

    session.save_state()
    log.info("登录成功；下次运行会再次清空并要求重新登录")
    return session


def _ensure_login_cdp(args):





    from xhs_browser import BrowserSession, port_open
    from xhs_login import wait_for_login

    if not port_open(args.cdp_port):
        raise SystemExit(
            f"未检测到 {args.cdp_port} 端口的 Chrome 调试服务。请先启动：\n"
            f"  python xhs_browser.py open {args.cdp_port}\n"
            "然后在打开的窗口里登录小红书网页版，再重跑本命令。"
        )

    session = BrowserSession(mode="cdp", cdp_port=args.cdp_port)
    session.__enter__()
    try:
        session.page.goto(f"{BASE}/explore", wait_until="domcontentloaded")
    except Exception:  
        pass

    if not wait_for_login(session.page, args.login_timeout,
                          hint="（请在被接管的 Chrome 窗口里登录小红书）"):
        try:
            session.__exit__(None, None, None)
        except Exception:  
            pass
        raise SystemExit(
            "CDP 浏览器里未检测到登录态（web_session）。本技能无免登录通道，"
            "请在被接管的 Chrome 窗口里登录小红书后重跑；"
            "或去掉 --tier cdp，改用默认的扫码登录。"
        )

    log.info("CDP 浏览器已登录，继续抓取")
    return session


def _restart_session(args, session=None):








    mode = getattr(session, "mode", "persistent")
    if mode == "cdp":
        log.warning("CDP 模式下不重启浏览器（那是你自己的 Chrome），改为刷新页面")
        if session is not None:
            try:
                session.page.reload(wait_until="domcontentloaded", timeout=30000)
                session.page.wait_for_timeout(1500)
            except Exception as err:  
                log.warning("刷新失败：%s", str(err)[:100])
        return session

    if session is not None:
        try:
            session.__exit__(None, None, None)
        except Exception as err:  
            log.warning("关闭旧会话失败（忽略）：%s", str(err)[:100])

    log.info("重启浏览器并重新登录…")
    from xhs_browser import BrowserSession
    new_session = BrowserSession(mode="persistent", headless=False)
    new_session.__enter__()
    try:
        from xhs_login import interactive_login
        ok = interactive_login(new_session.page, mode=getattr(args, "login", "qr"),
                               timeout=getattr(args, "login_timeout", 600))
    except Exception as err:  
        try:
            new_session.__exit__(None, None, None)
        except Exception:  
            pass
        raise SystemExit(f"重启后登录流程异常：{err}")

    if not ok:
        try:
            new_session.__exit__(None, None, None)
        except Exception:  
            pass
        raise SystemExit("重启后重新登录未完成，采集中止。")

    new_session.save_state()
    log.info("浏览器已重启并重新登录")
    return new_session


def _resolve_with_recovery(args, session):








    from xhs_resolve import Target, resolve, save_cached

    raw = args.target.strip()
    attempts = max(1, int(getattr(args, "resolve_retries", 2)))
    last = Target(raw=raw, resolved_by="unresolved")

    
    target = resolve(raw, use_cache=not getattr(args, "no_target_cache", False))
    if target.ok:
        return target, session

    
    for i in range(1, attempts + 1):
        if session is None:
            session = _open_browser(args)
        try:
            target = resolve(raw, browser=session,
                             use_cache=not getattr(args, "no_target_cache", False))
        except Exception as err:  
            log.warning("目标解析异常（第 %s/%s 次）：%s", i, attempts, str(err)[:160])
            target = Target(raw=raw, resolved_by="resolve_exception")

        if target.ok:
            save_cached(raw, target)
            return target, session

        last = target
        log.warning("目标解析未命中（%s），第 %s/%s 次尝试", target.resolved_by, i, attempts)

        if i >= attempts:
            break

        
        try:
            log.info("刷新页面后重试…")
            session.page.reload(wait_until="domcontentloaded", timeout=30000)
            session.page.wait_for_timeout(1500)
            target = resolve(raw, browser=session, use_cache=False)
            if target.ok:
                save_cached(raw, target)
                log.info("刷新后解析成功")
                return target, session
            last = target
        except Exception as err:  
            log.warning("刷新重试失败：%s", str(err)[:120])

        
        try:
            session = _restart_session(args, session)
        except SystemExit:
            raise
        except Exception as err:  
            log.warning("重启浏览器失败：%s", str(err)[:160])

    return last, session


def _open_browser(args, mode: str = "persistent"):
    from xhs_browser import BrowserSession
    session = BrowserSession(mode=mode, headless=args.headless, cdp_port=args.cdp_port)
    session.__enter__()
    return session


def _fetch_details(channel: BrowserChannel, notes: list[dict], args, out_dir: Path,
                   pacer=None) -> None:
    ranked = sorted(notes, key=lambda n: (n.get("liked") or 0), reverse=True)
    if args.detail_top > 0:
        ranked = ranked[: args.detail_top]   
    if len(ranked) > 30:
        pace = pacer.level if pacer is not None else "normal"
        per = {"slow": 14, "normal": 7, "fast": 4}.get(pace, 7)
        log.warning("全量详情共 %s 条，按 %s 节奏约需 %s 分钟；持续输出进度，"
                    "中途 Ctrl+C 中断已抓部分仍然有效",
                    len(ranked), pace, round(len(ranked) * per / 60))

    from xhs_antibot import guard
    page = getattr(channel, "page", None)     
    stopped = ""
    for i, note in enumerate(ranked, 1):
        if pacer is not None:
            state = guard(page, pacer, label=f"详情 {i}/{len(ranked)}",
                          wait_timeout=getattr(args, "challenge_timeout", 600))
            if state == "budget":
                stopped = f"budget_exhausted（详情阶段，已完成 {i - 1}/{len(ranked)}）"
                break
        else:
            RateLimiter(1.5, 3.5).wait()
        log.info("  [%s/%s] 详情+评论 %s", i, len(ranked), note.get("title") or note.get("note_id"))
        try:
            detail, comments = channel.fetch_note_detail(note, args.comments)
        except Exception as err:  
            log.warning("  详情抓取失败：%s", str(err)[:120])
            continue
        nid = note.get("note_id")
        if detail:
            write_json(out_dir / "raw" / "notes" / f"{nid}.json", detail)
        if comments:
            write_json(out_dir / "raw" / "comments" / f"{nid}.json", comments)
        jitter(0.5, 1.5)

    if stopped:
        channel.stop_reason = stopped
        log.warning("详情采集提前收工：%s", stopped)


def _merge_details(out_dir: Path, dataset: dict) -> None:





    index = {n["note_id"]: n for n in dataset["notes"]}
    merge_keys = ("desc", "tags", "liked", "collected", "commented", "shared",
                  "video_url", "images", "duration_ms", "ip_location", "timestamp")
    for detail_file in (out_dir / "raw" / "notes").glob("*.json"):
        nid = detail_file.stem
        detail = read_json(detail_file)
        if not detail or nid not in index:
            continue
        target = index[nid]
        for key in merge_keys:
            value = detail.get(key)
            if value in (None, "", [], 0):
                continue
            current = target.get(key)
            if key == "desc":
                if len(str(value)) > len(str(current or "")):
                    target[key] = value
            elif key in ("tags", "images"):
                if len(value or []) > len(current or []):
                    target[key] = value
            elif not current:
                target[key] = value
    for comment_file in (out_dir / "raw" / "comments").glob("*.json"):
        nid = comment_file.stem
        if nid in index:
            index[nid]["comments"] = read_json(comment_file, [])


def _data_quality_report(dataset: dict) -> None:





    notes = dataset.get("notes") or []
    total = len(notes)
    with_detail = sum(1 for n in notes if n.get("desc") or n.get("collected")
                      or n.get("commented") or n.get("tags"))
    with_tags = sum(1 for n in notes if n.get("tags"))
    with_comments = sum(1 for n in notes if n.get("comments"))
    comment_total = sum(len(n.get("comments") or []) for n in notes)
    with_media = sum(1 for n in notes if n.get("video_url")
                     or len(n.get("images") or []) > 1)

    missing = [n.get("note_id") for n in notes
               if not (n.get("desc") or n.get("collected") or n.get("commented"))]
    quality = {
        "notes_total": total,
        "detail_coverage": f"{with_detail}/{total}",
        "tag_coverage": f"{with_tags}/{total}",
        "notes_with_comments": with_comments,
        "comments_total": comment_total,
        "notes_with_media_urls": with_media,
        "missing_detail_ids": missing[:10],
        "missing_detail_count": len(missing),
    }
    dataset.setdefault("meta", {})["quality"] = quality
    log.info("数据自检：详情 %s/%s · 标签 %s/%s · 评论 %s 条（覆盖 %s 篇）· 媒体地址 %s 篇",
             with_detail, total, with_tags, total, comment_total, with_comments, with_media)
    if missing:
        log.warning("仍有 %s 条笔记无详情数据（示例：%s）。"
                    "可能是详情页被限流；可重跑（已抓的会保留），或加 --pace slow 放慢。",
                    len(missing), "、".join(missing[:5]))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="小红书账号/笔记爬取")
    ap.add_argument("--target", required=True, help="主页链接 / 短链 / 24位ID / 昵称")
    ap.add_argument("--out", default=str(Path.cwd() / "xhs_out"), help="输出目录")
    ap.add_argument("--limit", type=int, default=0,
                    help="笔记条数上限；0 = 不限（默认，实际由 --months 窗口收口）")
    ap.add_argument("--months", type=int, default=6,
                    help="只采集近 N 个月发布的笔记（默认 6 = 近半年）；0 = 不限时间")
    ap.add_argument("--since", default="",
                    help="只采集该日期之后发布的笔记（YYYY-MM-DD），优先于 --months")
    ap.add_argument("--pace", default="normal", choices=["slow", "normal", "fast"],
                    help="采集节奏：越慢越不容易触发风控（默认 normal）")
    ap.add_argument("--challenge-timeout", type=int, default=600,
                    help="触发人机验证后，等待人工处理的秒数")
    ap.add_argument("--resolve-retries", type=int, default=2,
                    help="目标解析失败后的恢复轮数（每轮：刷新页面 → 重启浏览器重新登录）")
    ap.add_argument("--no-target-cache", action="store_true",
                    help="跳过本地解析缓存，强制重新解析（缓存里旧结果失效时用）")
    ap.add_argument("--clear-target-cache", action="store_true",
                    help="只清空目标解析缓存后退出，不做抓取")
    ap.add_argument("--detail-top", type=int, default=0,
                    help="抓取详情+评论的笔记条数（按点赞排序）；0 = 全部（默认）；-1 = 跳过详情")
    ap.add_argument("--comments", type=int, default=100, help="每篇评论条数上限")
    ap.add_argument("--media", action="store_true", help="下载封面与视频")
    ap.add_argument("--media-top", type=int, default=8, help="下载素材的笔记条数")
    ap.add_argument("--tier", default="auto", choices=["auto", "http", "persistent", "cdp"])
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--headless", action="store_true",
                    help="无头模式（需要登录时会被强制改为有头，因为要扫码）")
    ap.add_argument("--login", default="qr", choices=["qr", "web"],
                    help="每次运行的登录方式：qr=App 扫码（默认）；web=手机号+验证码")
    ap.add_argument("--login-timeout", type=int, default=600, help="等待扫码/验证码完成的秒数")
    ap.add_argument("--max-scroll-rounds", type=int, default=400,
                    help="全量抓取的滚动轮次上限，防止异常页面无限滚动")
    return ap


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    from xhs_env import ensure_ready
    ensure_ready(need_browser=True)      
    try:
        crawl(parsed)
    finally:
        pass
