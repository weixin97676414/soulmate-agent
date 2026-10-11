# -*- coding: utf-8 -*-
"""小红书账号/笔记爬取主程序。

通道（--tier）：
  auto         自动降级：persistent(持久化登录态) -> cdp(接管本机Chrome) -> http(带cookie)
  persistent   Playwright 持久化 profile（首次扫码后长期复用）← 默认主力
  cdp          接管本机已登录 Chrome（--remote-debugging-port=9222）
  http         纯 HTTP + TLS 指纹，解析 SSR __INITIAL_STATE__，最快但最易受限

登录门禁（强制，**无免登录通道**）：
  每次运行都先清空历史登录态与浏览器缓存（`reset_runtime`：storage_state /
  cookies / cache / browser_profile），再弹出**有头浏览器**让用户扫码（--login qr，
  默认）或走手机号+短信验证码（--login web），登录完成后复用同一会话继续抓取。
  没有 `--no-login` 之类的后门：列表页 noteId 只有登录态才下发，
  免登录 SSR 恒为空串，既抓不到全量，也补不了详情。

默认全量抓取：--limit 0（滚动到主页底部取全部笔记）、
              --detail-top 0（全部笔记都抓详情+评论）。

产物：
  <out>/raw/api/*.json       原始接口响应（排障用）
  <out>/raw/profile.json     账号信息
  <out>/raw/notes.json       笔记列表
  <out>/raw/notes/<id>.json  笔记详情
  <out>/raw/comments/<id>.json
  <out>/dataset.json         归一化后的分析数据集（下游 xhs_analyze.py 直接消费）
  <out>/media/...            封面图 / 视频
"""
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
    # 真实接口是 user_posted（下划线），不是 user/posted；版本号放宽到 v\d+
    ("user_posted", re.compile(r"/api/sns/web/v\d+/user_posted")),
    ("user_info", re.compile(r"/api/sns/web/v\d+/user/(otherinfo|selfinfo|self)|/api/sns/web/v\d+/user_info")),
    ("note_detail", re.compile(r"/api/sns/web/v\d+/(feed|note/detail)")),
    ("comments", re.compile(r"/api/sns/web/v\d+/comment/(page|list)")),
]

WALL_MARKERS = ("登录", "安全验证", "滑动验证", "异常访问", "请完成验证", "访问受限")

#: 全量抓取时，连续多少轮滚动无新增才判定「到底」。
#: 小红书主页一次接口下发一批，滚动后偶有 1-2 轮空窗，阈值太小会提前收工。
FULL_STALL_LIMIT = 8


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
#: 同一字段在「接口 JSON（snake_case）」与「SSR JSON（camelCase）」里的两种写法
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
    """按 key 取值，同时兼容 snake_case 与 camelCase 两种来源。"""
    if not isinstance(d, dict):
        return default
    for name in (key, _DUAL.get(key, key)):
        if name in d and d[name] not in (None, "", [], {}):
            return d[name]
    return default


def _interact(card: dict, key: str) -> int:
    """互动数。SSR 列表页只下发 likedCount，其余为 0（需详情页或接口补全）。"""
    if not isinstance(card, dict):
        return 0
    info = pick(card, "interact_info")
    if info is None:                       # SSR 的写法是 interactInfo
        info = card.get("interactInfo") or {}
    if not isinstance(info, dict):
        return 0
    if key in info:
        return human_num(info[key])
    camel = _DUAL.get(key)
    return human_num(info.get(camel)) if camel else 0


def pick_video(video: dict) -> tuple[str, int]:
    """从 SSR 的 note.video 里取出「可直接下载的视频地址」和时长（毫秒）。

    SSR 里存在三种变体，必须都覆盖：
      A. video.media.stream.h264[0]        -> masterUrl / backupUrls（camelCase）
      B. video.mediaV2（**JSON 字符串**）   -> 需二次解析，内部是 master_url / backup_urls
      C. video.capa.duration               -> 单位「秒」，不是毫秒
    另一个坑：masterUrl 带 sign + t 参数，会过期；backupUrls 无签名、长期有效，优先用。
    """
    if not isinstance(video, dict):
        return "", 0

    def _from_stream(stream_obj: dict) -> str:
        """按码率档位挑一个能用的地址。

        编码档位的 key 会随平台改版变化（实测出现过 h264/h265、也有 EF4/EF5/EF6/EF7），
        写死白名单会在改版后整段失效，所以这里遍历 stream 下的全部档位。
        """
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
                # 无签名的备份源优先，避免 masterUrl 的 sign/t 过期
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
            except Exception:  # noqa: BLE001
                mv2 = None
        if isinstance(mv2, dict):
            url = _from_stream(mv2.get("stream") or (mv2.get("video") or {}).get("stream") or {})

    # 时长：capa.duration 与 media.video.duration 都是「秒」
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
    """把 user/posted、feed、SSR 三种来源的笔记卡片压成统一结构。

    两套命名都要兼容：
      接口 JSON -> note_card / interact_info / liked_count / url_default
      SSR  JSON -> noteCard  / interactInfo  / likedCount  / infoList[].url
    """
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
    """从 SSR 页面里抠出 window.__INITIAL_STATE__（含 undefined 的脏 JSON）。"""
    idx = html.find("window.__INITIAL_STATE__")
    if idx < 0:
        return {}
    start = html.find("{", idx)
    if start < 0:
        return {}
    # 不能再用「数花括号」截取：字符串里的 { } 会让计数提前归零
    # （实测把 42KB 的 state 截成 278 字节）。改用 raw_decode 让它自己解析出边界，
    # 尾部残留的 HTML 会被自然丢弃。
    blob = re.sub(r"\bundefined\b", "null", html[start:])
    # SSR 里混着 JS 字面量：`"noteDetailMap":new Map([])`、`new Set([])`，
    # 不是合法 JSON，会让整段解析失败，先换成空容器。
    blob = re.sub(r"new\s+Map\(\s*\[?\s*\]?\s*\)", "{}", blob)
    blob = re.sub(r"new\s+Set\(\s*\[?\s*\]?\s*\)", "[]", blob)
    try:
        obj, _ = json.JSONDecoder().raw_decode(blob)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def notes_from_state(state: dict) -> list[dict]:
    """取 SSR 里的笔记列表。

    注意：新版 SSR 的 `user.notes` 是**分页数组（list of list）**，
    直接遍历会得到 list 而不是 dict，必须先拍平。
    """
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
    """SSR 的账号信息在 `user.userPageData`（basicInfo / interactions / tags），
    老版本或接口返回则用 `user.userInfo`。"""
    user = state.get("user") or {}
    page_data = user.get("userPageData") or {}
    if page_data.get("basicInfo"):
        return page_data
    return (user.get("userInfo") or user.get("info") or user)


def note_detail_from_state(state: dict, note_id: str = "") -> dict:
    """从详情页 SSR 的 `note.noteDetailMap` 提取完整笔记字段。

    免登录也完整下发：desc / tagList / interactInfo（收藏·评论·分享）/ video 流 / 时间戳。
    SSR 用 camelCase，接口用 snake_case，这里两种都兼容。
    """
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


# --------------------------------------------------------------------------- #
# 通道一：HTTP
# --------------------------------------------------------------------------- #
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
            import curl_cffi  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            try:
                import requests  # noqa: F401
                return True
            except Exception:  # noqa: BLE001
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
        """详情页 SSR 解析（免登录可用）。

        这是拿「视频流地址 / 收藏数 / 评论数 / 分享数 / 话题标签」最稳的通道：
        列表页 SSR 只下发点赞数，详情页 SSR 才给全量；而登录态下 __INITIAL_STATE__
        反而被前端移除，只能走 DOM —— 所以免登录的 SSR 反而是信息最全的一条路。
        评论不在此列：SSR 不下发评论，需要登录 + 浏览器滚动（见 BrowserChannel）。
        """
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
            except Exception:  # noqa: BLE001
                pass
        return detail, []


# --------------------------------------------------------------------------- #
# 通道二/三：Playwright
# --------------------------------------------------------------------------- #
class BrowserChannel:
    """通过「页面正常浏览 + 拦截 XHR 响应」拿结构化数据，避免自行实现 x-s 签名。"""

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
        #: 抓取是「主动收工」还是「正常到底」，写入 dataset.meta.stopped_reason
        self.stop_reason = ""

    # -- 生命周期 ---------------------------------------------------------- #
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

    # -- 响应拦截 ---------------------------------------------------------- #
    def _on_response(self, response) -> None:
        url = response.url or ""
        for key, pattern in API_RULES:
            if not pattern.search(url):
                continue
            if response.status != 200:
                continue
            try:
                data = response.json()
            except Exception:  # noqa: BLE001
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

    # -- 抓取动作 ---------------------------------------------------------- #
    def fetch_profile(self, target: Target, limit: int = 0, max_scroll_rounds: int = 400,
                      window_ms: int = 0, pacer=None) -> tuple[dict, list[dict], str]:
        """抓主页笔记列表。

        `limit <= 0` 表示不限条数；`window_ms > 0` 表示只要该时间点之后的笔记。
        两者叠加后滚动会在**任意一个条件先满足**时停止：

        - 列表按时间倒序，一旦滚到早于窗口的笔记，后面的必然更老 → 立即停，
          这是「近半年窗口」能大幅压低请求量的原因；
        - 连续 `FULL_STALL_LIMIT` 轮无增量判定到底；
        - `max_scroll_rounds` 兜底防异常页面无限滚动。

        `pacer` 传入时会按拟人节奏控速，并在触发验证时暂停等人工处理。
        """
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

            # 窗口边界：列表倒序，最早一条已早于窗口 → 后面必然更老，停
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

        if not notes:  # SSR 兜底
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
        # 注意：limit<=0 表示「不限条数」，不能写成 notes[:limit] —— notes[:0] 会得到空列表，
        # 导致默认抓取永远返回 0 条，静默降级到 http 通道（SSR 仅首页几十条且无 noteId）。
        return profile, (notes if (limit is None or limit <= 0) else notes[:limit]), \
            "ok" if notes else "browser_no_notes"

    def _extract_detail_dom(self, page, note_id: str) -> dict:
        """从笔记详情页 DOM 提取正文/标签/互动数/图片。

        实测结论：登录态下笔记详情**不走接口**（/api/sns/web/v1/feed 不触发），
        `window.__INITIAL_STATE__` 也已被移除（顶层键为空），数据只存在于 DOM：
            正文+话题标签  #detail-desc
            点赞/收藏/评论  .like-wrapper/.collect-wrapper/.chat-wrapper .count
            图片列表        媒体容器内的 img（.media-container / .swiper-slide）
        """
        # 等水合：固定 sleep 在慢网下会提取到空 DOM。等正文或互动条出现（尽力而为，
        # 超时不报错 —— 图文/视频两种布局的选择器不同，有一个出现就够了）
        for sel in ("#detail-desc", ".note-content", ".like-wrapper .count",
                    ".interact-container"):
            try:
                page.wait_for_selector(sel, timeout=6000)
                break
            except Exception:  # noqa: BLE001
                continue

        def text_of(selector: str) -> str:
            try:
                el = page.query_selector(selector)
                return (el.inner_text() or "").strip() if el else ""
            except Exception:  # noqa: BLE001
                return ""

        desc = text_of("#detail-desc") or text_of(".note-text") or text_of(".desc")
        tags = []
        try:
            for el in page.query_selector_all("a.tag, .tag, #detail-desc a"):
                t = (el.inner_text() or "").strip().lstrip("#").strip()
                if t and t not in tags and len(t) < 40:
                    tags.append(t)
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
            pass

        # 登录态下 video 的 src 多为 blob: 地址，拿不到真实 CDN。
        # 从 performance 资源日志里捞已请求过的视频地址（sns-video / .mp4），
        # 按传输体积取最大的一段（通常就是正片，预览片段很小）。
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
            except Exception:  # noqa: BLE001
                pass

        # 图片列表：登录态下接口兜底通常不触发，图文笔记的图片只能从 DOM 拿。
        # 缺了它，篇均图片数与素材下载都会偏差。
        images: list[dict] = []
        seen_urls: set[str] = set()
        try:
            for el in page.query_selector_all(
                    ".media-container img, .swiper-slide img, .note-slider img, "
                    ".img-container img, .note-detail img"):
                src = el.get_attribute("src") or ""
                if not src.startswith(("http://", "https://")):
                    continue
                if "sns-avatar" in src or "/avatar" in src:   # 排除头像
                    continue
                if src in seen_urls:
                    continue
                seen_urls.add(src)
                images.append({"url": src,
                               "width": el.get_attribute("width"),
                               "height": el.get_attribute("height")})
        except Exception:  # noqa: BLE001
            pass

        # 发布时间与 IP 属地混在底部信息里
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

        # 主通道：DOM 直读（登录态下详情不走接口、__INITIAL_STATE__ 已移除）
        detail = self._extract_detail_dom(self.page, note.get("note_id") or "")
        # 兜底：若接口恰好触发（旧版本页面），用接口数据补齐媒体字段
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
        # 详情页的滚动发生在内部容器，窗口本身不滚；滚轮只作用于光标所在的元素。
        # 评论区在**右侧面板**（自己的滚动容器）—— 光标停在视口中央（左侧媒体面板）
        # 时滚轮滚的是媒体区，评论永远不翻页（每篇只能拿到第一页约 10 条）。
        # 所以优先把光标移到评论区容器上，找不到再退到视口右侧。
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
            except Exception:  # noqa: BLE001
                continue
        if not hovered:
            try:
                vp = self.page.viewport_size or {"width": 1440, "height": 900}
                self.page.mouse.move(vp["width"] * 0.78, vp["height"] * 0.5)
            except Exception:  # noqa: BLE001
                pass
        stalled = 0
        while len(collected) < comments_limit and stalled < 4:
            before = len(collected)
            # recenter=False：光标已定位在评论区容器上，不能被拉回视口中央
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

    # -- 解析辅助 ---------------------------------------------------------- #
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
            # 新版扁平结构（2026-09 实测）：data.basic_info + data.interactions，
            # interactions 里是**精确值**（如 fans="19706"），远比 SSR 的
            # 「1万+」近似值可靠 —— 缺了这一支，粉丝数会系统性偏小。
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
    """统一账号信息。兼容三种来源：

    - SSR：`user.userPageData` → basicInfo + interactions[{type,count}] + tags[{name}]
    - 接口：`data.user` → snake_case 平铺字段
    - 兜底：只有 uid / 昵称
    """
    profile = profile if isinstance(profile, dict) else {}
    # 接口/SSR 两套写法：basicInfo（camelCase，SSR）/ basic_info（snake_case，新版接口）
    basic = profile.get("basicInfo") or profile.get("basic_info") or {}
    if not isinstance(basic, dict):
        basic = {}

    # interactions 是 [{type: follows|fans|interaction, count: "1万+"}]
    counts: dict[str, int] = {}
    for entry in (profile.get("interactions") or []):
        if isinstance(entry, dict) and entry.get("type"):
            counts[entry["type"]] = human_num(entry.get("count"))
    inter = profile.get("interact_info") or profile.get("interaction") or {}
    if not isinstance(inter, dict):
        inter = {}

    tags_raw = profile.get("tags") or profile.get("tag_list") or []
    gender_raw = basic.get("gender", profile.get("gender"))
    # basicInfo.gender 的数值含义各版本不一致，不能硬猜；
    # 但标签里的性别图标是明确的（icons/user/gender-female-v1.png），优先用它。
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


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def crawl(args) -> dict:
    ensure_runtime()

    # 单独清理解析缓存：不登录、不抓取，清完即退
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

    # 0a. 采集窗口 + 反风控节奏（时间窗口是降低风控触发概率最有效的手段）
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

    # 0b. 登录门禁：每次运行都清空后重新扫码/验证码登录，无免登录通道
    pre_session = _ensure_login(args)

    # 1. 目标解析（带「刷新页面 → 重启浏览器重新登录」的恢复机制）
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

    # 2. 通道降级
    #    默认不再把 http 免登录通道排第二：未登录时它只能拿到残缺的 SSR 列表
    #    （列表里没有 noteId），拿全量笔记必须走登录态的浏览器通道。
    tier_order = {
        "auto": ["persistent", "cdp", "http"],
        "http": ["http", "persistent", "cdp"],
        "persistent": ["persistent", "cdp", "http"],
        "cdp": ["cdp", "persistent", "http"],
    }[args.tier]

    if args.headless and not has_login():
        # 无头 + 未登录 = 浏览器通道必然被登录墙拦截（也没法扫码），先走 HTTP 更省时间
        log.info("无头模式且未保存登录态，浏览器通道会被登录墙拦截，优先尝试 http")
        tier_order = ["http"] + [t for t in tier_order if t != "http"]

    profile, notes, used_tier = {}, [], ""
    stop_reason = ""                  # 抓取为何结束（到底 / 窗口边界 / 预算用尽）
    failures: list[str] = []          # 记录每个通道的具体失败原因，避免被最后一个覆盖
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
                    # 详情页 SSR 能补齐视频流地址与收藏/评论/分享数，务必抓
                    # （列表页 SSR 只有点赞数；评论仍需登录态，此处拿不到）
                    # 注意门禁必须是 >= 0：默认 0 = 全部抓详情；只有 -1 才是显式跳过。
                    # 旧代码写成 `!= 0`，默认配置下详情采集被整体跳过（严重 bug）。
                    if args.detail_top >= 0:
                        try:
                            _fetch_details(channel, notes, args, out_dir, pacer=pacer)
                        except Exception as err:  # noqa: BLE001
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
                        # 必须在会话关闭前抓详情，否则 page 已失效
                        # 门禁用 >= 0（0 = 全部抓详情，默认；-1 = 显式跳过）。
                        # 旧代码写成 `!= 0`，默认配置下详情被整体跳过 —— 这正是
                        # 「详情页数据完全没抓到」的根因。
                        if args.detail_top == 0:
                            log.info("详情采集：全部 %s 条（默认 detail_top=0）", len(notes))
                        else:
                            log.info("详情采集：点赞最高的前 %s 条", args.detail_top)
                        try:
                            _fetch_details(channel, notes, args, out_dir, pacer=pacer)
                        except Exception as err:  # noqa: BLE001
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
        except Exception as err:  # noqa: BLE001
            failures.append(f"{tier}：异常 {str(err)[:120]}")
            log.warning("通道 %s 异常：%s", tier, str(err)[:160])
            continue

    # 会话关闭**挪到数据落盘之后**（见 _close_session_safe）：
    # context.close() 偶发挂起（视频流未断等），绝不能让它挡在数据写入前面。
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

    # 3. 时间窗口过滤（覆盖 http 通道：它只有首页几十条，同样要按时间截）
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

    # 4. 详情/评论补齐（http 通道仅能拿列表，详情靠公开页补）
    profile = normalize_profile(profile or {}, target)
    write_json(out_dir / "raw" / "profile.json", profile)
    write_json(out_dir / "raw" / "notes.json", notes)

    dataset = {
        "meta": {
            "target": target.to_dict(),
            "tier": used_tier,
            "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note_limit": args.limit,
            "full_crawl": args.limit <= 0,          # True = 不限条数
            "detail_top": args.detail_top,
            "detail_all": args.detail_top == 0,     # True = 全部笔记都抓了详情
            "detail_skipped": args.detail_top < 0,  # True = 显式跳过详情（--detail-top -1）
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
        except Exception as err:  # noqa: BLE001
            log.warning("素材下载失败（不影响文本分析）：%s", err)
            dataset["meta"]["media"] = {"error": str(err)[:200]}

    dataset["notes"].sort(key=lambda n: n.get("timestamp") or 0, reverse=True)
    write_json(out_dir / "dataset.json", dataset)
    log.info("完成：%s", out_dir / "dataset.json")

    _close_session_safe(stale_session)
    return dataset


def _close_session_safe(session, timeout: int = 30) -> None:
    """带看门狗的会话关闭：context.close() 偶发挂起，不能挡住收尾。

    数据此时已经全部落盘，关不掉就留给用户手动关窗口，不影响结果。
    注意 save_state 必须在主线程调（Playwright sync API 不允许跨线程操作
    greenlet，在子线程调用会报 Cannot switch to a different thread），
    之后子线程只负责关闭。
    """
    if session is None:
        return
    import threading

    try:
        session.save_state()
    except Exception:  # noqa: BLE001
        pass

    def _close():
        try:
            session.context.close()
        except Exception:  # noqa: BLE001
            pass

    t = threading.Thread(target=_close, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log.warning("浏览器会话关闭超时（%s 秒），数据已全部落盘；"
                    "残留的浏览器窗口可手动关闭，不影响结果。", timeout)


def _ensure_login(args):
    """登录门禁：**每次运行都必须全新登录**，且没有免登录通道。

    流程：清空历史登录态与浏览器缓存 → 弹出有头浏览器 → 扫码 / 短信验证码 →
    复用该会话继续抓取。返回已登录的 persistent 会话。

    两条硬约束：

    1. **不复用旧登录态** —— 每次先 `reset_runtime()` 清干净（storage_state /
       cookies / 浏览器缓存 / browser_profile）再登录，不留下任何历史登录记录；
    2. **不提供免登录通道** —— 列表页 noteId 只有登录态才下发，免登录 SSR 恒为
       空串，既抓不到全量也补不了详情。
    """
    from xhs_browser import BrowserSession
    from xhs_common import reset_runtime

    reset_runtime(logger=log)

    # CDP 通道用的是用户自己 Chrome 里的登录态，不该再弹一个窗口让他扫第二次
    if getattr(args, "tier", "auto") == "cdp":
        return _ensure_login_cdp(args)

    log.info("正在打开浏览器，请完成登录（历史登录态与缓存已清除，本次为全新登录）")
    args.headless = False                      # 扫码必须有界面
    session = BrowserSession(mode="persistent", headless=False)
    session.__enter__()
    try:
        from xhs_login import interactive_login
        ok = interactive_login(session.page, mode=getattr(args, "login", "qr"),
                               timeout=getattr(args, "login_timeout", 600))
    except Exception as err:  # noqa: BLE001
        try:
            session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(f"登录流程异常：{err}")

    if not ok:
        try:
            session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
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
    """CDP 通道的登录门禁：用被接管 Chrome 里已有的登录态，没有就等用户登录。

    同样遵循「必须登录」的硬约束，只是换了个窗口 —— 用户自己的 Chrome
    里没有 `web_session` 时，脚本会一直等到登录完成或超时。
    """
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
    except Exception:  # noqa: BLE001
        pass

    if not wait_for_login(session.page, args.login_timeout,
                          hint="（请在被接管的 Chrome 窗口里登录小红书）"):
        try:
            session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(
            "CDP 浏览器里未检测到登录态（web_session）。本技能无免登录通道，"
            "请在被接管的 Chrome 窗口里登录小红书后重跑；"
            "或去掉 --tier cdp，改用默认的扫码登录。"
        )

    log.info("CDP 浏览器已登录，继续抓取")
    return session


def _restart_session(args, session=None):
    """关掉当前浏览器 → 重新打开 → 重新登录，返回新会话。

    对付「搜索页/主页加载超时、解析卡死」这类**页面状态污染**：
    在同一个卡死的标签页上反复重试往往无效，重开一个干净会话更管用。

    CDP 模式不适用（那是用户自己的浏览器，不能替他关掉），
    此时返回原 session，由调用方改走刷新重试。
    """
    mode = getattr(session, "mode", "persistent")
    if mode == "cdp":
        log.warning("CDP 模式下不重启浏览器（那是你自己的 Chrome），改为刷新页面")
        if session is not None:
            try:
                session.page.reload(wait_until="domcontentloaded", timeout=30000)
                session.page.wait_for_timeout(1500)
            except Exception as err:  # noqa: BLE001
                log.warning("刷新失败：%s", str(err)[:100])
        return session

    if session is not None:
        try:
            session.__exit__(None, None, None)
        except Exception as err:  # noqa: BLE001
            log.warning("关闭旧会话失败（忽略）：%s", str(err)[:100])

    log.info("重启浏览器并重新登录…")
    from xhs_browser import BrowserSession
    new_session = BrowserSession(mode="persistent", headless=False)
    new_session.__enter__()
    try:
        from xhs_login import interactive_login
        ok = interactive_login(new_session.page, mode=getattr(args, "login", "qr"),
                               timeout=getattr(args, "login_timeout", 600))
    except Exception as err:  # noqa: BLE001
        try:
            new_session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(f"重启后登录流程异常：{err}")

    if not ok:
        try:
            new_session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit("重启后重新登录未完成，采集中止。")

    new_session.save_state()
    log.info("浏览器已重启并重新登录")
    return new_session


def _resolve_with_recovery(args, session):
    """解析目标，带「刷新页面 → 重启浏览器重新登录」两级恢复。

    返回 `(Target, session)`；session 可能被替换成重启后的新会话。

    为什么需要恢复：搜索页极重，加载超时会把整个抓取带崩。
    现在解析失败不会抛异常，而是先刷新重试，再重启浏览器重登重试，
    全部失败才交给上层，并给出可用的替代输入建议。
    """
    from xhs_resolve import Target, resolve, save_cached

    raw = args.target.strip()
    attempts = max(1, int(getattr(args, "resolve_retries", 2)))
    last = Target(raw=raw, resolved_by="unresolved")

    # 1) 不需要浏览器的路径先试（正则 / 短链 / uid / 缓存）
    target = resolve(raw, use_cache=not getattr(args, "no_target_cache", False))
    if target.ok:
        return target, session

    # 2) 需要浏览器：解析 → 刷新 → 重启重登
    for i in range(1, attempts + 1):
        if session is None:
            session = _open_browser(args)
        try:
            target = resolve(raw, browser=session,
                             use_cache=not getattr(args, "no_target_cache", False))
        except Exception as err:  # noqa: BLE001
            log.warning("目标解析异常（第 %s/%s 次）：%s", i, attempts, str(err)[:160])
            target = Target(raw=raw, resolved_by="resolve_exception")

        if target.ok:
            save_cached(raw, target)
            return target, session

        last = target
        log.warning("目标解析未命中（%s），第 %s/%s 次尝试", target.resolved_by, i, attempts)

        if i >= attempts:
            break

        # 恢复动作一：刷新页面（轻）
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
        except Exception as err:  # noqa: BLE001
            log.warning("刷新重试失败：%s", str(err)[:120])

        # 恢复动作二：重启浏览器 + 重新登录（重）
        try:
            session = _restart_session(args, session)
        except SystemExit:
            raise
        except Exception as err:  # noqa: BLE001
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
        ranked = ranked[: args.detail_top]   # 0 = 全部笔记都抓详情
    if len(ranked) > 30:
        pace = pacer.level if pacer is not None else "normal"
        per = {"slow": 14, "normal": 7, "fast": 4}.get(pace, 7)
        log.warning("全量详情共 %s 条，按 %s 节奏约需 %s 分钟；持续输出进度，"
                    "中途 Ctrl+C 中断已抓部分仍然有效",
                    len(ranked), pace, round(len(ranked) * per / 60))

    from xhs_antibot import guard
    page = getattr(channel, "page", None)     # HttpChannel 没有 page，此时只控节奏
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
        except Exception as err:  # noqa: BLE001
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
    """把详情/评论合并进数据集。

    原实现条件写反了（详情为空时会用空值覆盖列表里的好数据，且缺 key 直接 KeyError）。
    现在的规则：详情值非空才考虑；desc 取更长的，列表字段取更长的，数值字段列表里没有才补。
    """
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
    """抓取结束后的数据自检：详情/评论/标签覆盖了多少笔记，缺了哪些。

    写进 dataset.meta.quality，同时打印到日志 —— 让「详情没抓到」这类问题
    在现场就暴露，而不是等分析阶段才发现数据对不上。
    """
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
    ensure_ready(need_browser=True)      # 环境缺失时自动跑 setup.py 补齐
    try:
        crawl(parsed)
    finally:
        pass
