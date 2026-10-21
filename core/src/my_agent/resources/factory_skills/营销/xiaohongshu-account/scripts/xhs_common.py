# -*- coding: utf-8 -*-





from __future__ import annotations

import json
import logging
import random
import re
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = SKILL_DIR / ".runtime"
STATE_FILE = RUNTIME_DIR / "storage_state.json"   
COOKIE_FILE = RUNTIME_DIR / "cookies.json"        
PROFILE_DIR = RUNTIME_DIR / "browser_profile"     
CACHE_DIR = RUNTIME_DIR / "cache"

BASE = "https://www.xiaohongshu.com"
EDITH = "https://edith.xiaohongshu.com"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
]

VIEWPORTS = [(1440, 900), (1512, 950), (1366, 850), (1680, 1000)]


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def reset_runtime(include_profile: bool = True, logger=None) -> dict:












    removed: list[str] = []
    failed: list[str] = []

    for path in (STATE_FILE, COOKIE_FILE):
        try:
            if path.exists():
                path.unlink()
                removed.append(path.name)
        except Exception as err:  
            failed.append(f"{path.name}：{err}")

    targets = [CACHE_DIR] + ([PROFILE_DIR] if include_profile else [])
    for path in targets:
        if not path.exists():
            continue
        try:
            if not any(path.iterdir()):
                
                
                continue
        except Exception:  
            pass
        try:
            trash = path.with_name(f"{path.name}_discard_{time.strftime('%Y%m%d%H%M%S')}")
            path.rename(trash)
            removed.append(f"{path.name}/")
        except Exception as err:  
            failed.append(f"{path.name}/（改名失败）：{err}")

    ensure_runtime()          

    if logger is not None:
        logger.info("已清除历史登录态与缓存：%s", "、".join(removed) or "（无残留）")
        for item in failed:
            logger.warning("清理失败：%s", item)
    return {"removed": removed, "failed": failed}

    ensure_runtime()          

    if logger is not None:
        logger.info("已清除历史登录态与缓存：%s", "、".join(removed) or "（无残留）")
        for item in failed:
            logger.warning("清理失败（多半是浏览器进程仍在占用）：%s", item)
    return {"removed": removed, "failed": failed}


def get_logger(name: str = "xhs") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = get_logger()


class RateLimiter:


    def __init__(self, min_sec: float = 1.2, max_sec: float = 3.0):
        self.min_sec = min_sec
        self.max_sec = max_sec
        self._last = 0.0

    def wait(self) -> None:
        delta = time.time() - self._last
        target = random.uniform(self.min_sec, self.max_sec)
        if delta < target:
            time.sleep(target - delta)
        self._last = time.time()

    def rest(self, min_sec: float = 8.0, max_sec: float = 18.0) -> None:

        time.sleep(random.uniform(min_sec, max_sec))


def jitter(min_sec: float = 0.3, max_sec: float = 1.2) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def random_headers(cookie: str = "") -> dict:
    ua = random.choice(UA_POOL)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": BASE + "/",
        "Origin": BASE,
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def human_num(value) -> int:

    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    
    text = str(value).strip().replace(",", "").replace(" ", "").rstrip("+")
    if not text:
        return 0
    match = re.match(r"^([\d.]+)\s*([万wW千kK亿]?)$", text)
    if not match:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else 0
    num, unit = float(match.group(1)), match.group(2)
    scale = {"": 1, "千": 1_000, "k": 1_000, "K": 1_000,
             "万": 10_000, "w": 10_000, "W": 10_000, "亿": 100_000_000}[unit]
    return int(num * scale)


def fmt_num(n) -> str:
    n = human_num(n)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.2f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def detect_lang(text: str) -> str:

    if not text:
        return "unknown"
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    return "zh" if chinese >= max(3, len(text) * 0.1) else "other"
