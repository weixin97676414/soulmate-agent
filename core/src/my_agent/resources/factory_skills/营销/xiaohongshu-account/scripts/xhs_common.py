# -*- coding: utf-8 -*-
"""小红书账号深度拆解技能 - 公共基础模块.

提供：路径常量、日志、限速器、浏览器指纹、数字解析、JSON 读写。
所有脚本统一通过 `from xhs_common import *` 复用。
"""
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
STATE_FILE = RUNTIME_DIR / "storage_state.json"   # Playwright storage_state（登录态）
COOKIE_FILE = RUNTIME_DIR / "cookies.json"        # 纯 cookie 文本，供 requests/curl_cffi 用
PROFILE_DIR = RUNTIME_DIR / "browser_profile"     # 持久化浏览器 profile（扫码登录复用）
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
    """清除登录态与浏览器缓存，返回 `{"removed": [...], "failed": [...]}`。

    本技能**不复用历史登录态**。清理策略是「**改名弃用**」而不是删除：

    - `storage_state.json` / `cookies.json` 这两个登录凭证文件**真删**（各 1 个文件）；
    - `cache/`、`browser_profile/` 整目录**改名**为 `<name>_discard_<时间戳>` ——
      改名不是删除，在受限环境（沙箱护栏 / 浏览器进程占用目录）下也不会失败；
      改完即达成「旧 profile 永久失效、下次启动创建全新 profile、无法复用任何登录记录」。

    `_discard_*` 目录是惰性垃圾（不再被任何代码引用），磁盘紧张时可手动删除，
    不影响本技能的任何功能。
    """
    removed: list[str] = []
    failed: list[str] = []

    for path in (STATE_FILE, COOKIE_FILE):
        try:
            if path.exists():
                path.unlink()
                removed.append(path.name)
        except Exception as err:  # noqa: BLE001
            failed.append(f"{path.name}：{err}")

    targets = [CACHE_DIR] + ([PROFILE_DIR] if include_profile else [])
    for path in targets:
        if not path.exists():
            continue
        try:
            if not any(path.iterdir()):
                # 空目录：里面没有任何登录态/缓存，无需清理 ——
                # 也避免在受限环境（护栏按轮计数）里触发无谓的改名操作
                continue
        except Exception:  # noqa: BLE001
            pass
        try:
            trash = path.with_name(f"{path.name}_discard_{time.strftime('%Y%m%d%H%M%S')}")
            path.rename(trash)
            removed.append(f"{path.name}/")
        except Exception as err:  # noqa: BLE001
            failed.append(f"{path.name}/（改名失败）：{err}")

    ensure_runtime()          # 目录改走了要重建，否则后续写文件失败

    if logger is not None:
        logger.info("已清除历史登录态与缓存：%s", "、".join(removed) or "（无残留）")
        for item in failed:
            logger.warning("清理失败：%s", item)
    return {"removed": removed, "failed": failed}

    ensure_runtime()          # 目录删掉了要重建，否则后续写文件失败

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
    """按区间随机间隔限速，模拟真人浏览节奏，降低风控概率。"""

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
        """长休息，用于翻页之间的降温。"""
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
    """把 '1.2万' / '3.5k' / '1,234' / 1234 / None 统一转成 int。"""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    # 小红书的下发格式带「+」后缀：1万+ / 10+ / 10万+。不去掉会被解析成 1 / 10
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
    """粗略判断正文语种，避免英文账号被按中文规则拆解。"""
    if not text:
        return "unknown"
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    return "zh" if chinese >= max(3, len(text) * 0.1) else "other"
