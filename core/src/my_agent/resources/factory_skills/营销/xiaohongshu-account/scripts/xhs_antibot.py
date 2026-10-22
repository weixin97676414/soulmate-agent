# -*- coding: utf-8 -*-
















from __future__ import annotations

import calendar
import random
import re
import time
from datetime import datetime

from xhs_common import log






_TEXT_MARKS = [
    ("slider", ("滑动验证", "拖动滑块", "向右滑动", "请完成滑动", "完成拼图")),
    ("sms", ("短信验证", "安全验证", "身份验证", "请输入验证码")),
    ("risk", ("异常访问", "访问受限", "操作频繁", "请求过于频繁", "请稍后再试",
              "系统繁忙", "流量异常")),
    ("login", ("扫码登录", "登录后查看", "登录查看更多")),
]


_CHALLENGE_SELECTORS = (
    ".verify-page", "#captcha", ".red-captcha", ".slider-verify",
    "iframe[src*='captcha']", "iframe[src*='verify']",
    ".reds-mask", "[class*='captcha']", "[class*='verify-page']",
)


_SHORT_PAGE = 600


def detect(page) -> str:




    url = ""
    try:
        url = page.url or ""
    except Exception:  
        pass
    if "/website-login" in url:
        return "login"

    for selector in _CHALLENGE_SELECTORS:
        try:
            if page.query_selector(selector):
                return "slider"
        except Exception:  
            continue

    text = ""
    try:
        if page.query_selector("body"):
            text = (page.inner_text("body") or "")[:_SHORT_PAGE]
    except Exception:  
        pass
    if not text:
        return ""

    for kind, marks in _TEXT_MARKS:
        for mark in marks:
            if mark in text:
                
                if kind == "login" and len(text) > 200:
                    continue
                return kind

    if len(text) < 200 and re.search(r"验证|安全|滑块", text):
        return "unknown"
    return ""






PACE_LEVELS = {
    "slow":   {"gap": (4.0, 9.0),  "every": 5,  "rest": (45, 90),  "budget": 120},
    "normal": {"gap": (2.5, 6.0),  "every": 8,  "rest": (25, 55),  "budget": 200},
    "fast":   {"gap": (1.5, 3.5),  "every": 12, "rest": (12, 25),  "budget": 320},
}


class HumanPacer:






    def __init__(self, level: str = "normal"):
        cfg = PACE_LEVELS.get(level, PACE_LEVELS["normal"])
        self.level = level if level in PACE_LEVELS else "normal"
        self.gap = cfg["gap"]
        self.every = cfg["every"]
        self.rest = cfg["rest"]
        self.budget = cfg["budget"]
        self.actions = 0
        self.rests = 0

    def tick(self, label: str = "") -> None:

        if self.actions >= self.budget:
            raise BudgetExhausted(
                f"已达单任务动作上限 {self.budget} 次（节奏档位 {self.level}），主动收工。"
                f"剩余笔记可下次继续，或改用 --pace slow 提高上限的反向操作："
                f"先缩小 --months 窗口再跑。"
            )
        if self.actions > 0:
            delay = random.uniform(*self.gap)
            if label:
                log.info("  [节奏] %s：等待 %.1fs", label, delay)
            time.sleep(delay)
        self.actions += 1

        if self.actions % self.every == 0:
            self.rests += 1
            seconds = random.uniform(*self.rest)
            log.info("  [降温] 已连续 %s 个动作，长休 %.0f 秒（模拟真人离开一会儿）",
                     self.actions, seconds)
            time.sleep(seconds)

    def cool_down(self, seconds: float | None = None) -> None:

        seconds = seconds or random.uniform(60, 120)
        log.info("  [降温] 风控后额外等待 %.0f 秒", seconds)
        time.sleep(seconds)

    def remaining(self) -> int:
        return max(0, self.budget - self.actions)


class BudgetExhausted(RuntimeError):
    pass





_TIPS = {
    "slider": "页面出现【滑动验证】—— 请在弹出的浏览器窗口里手动拖一下滑块。",
    "sms": "页面出现【短信/身份验证】—— 请在窗口里完成验证（手机号与验证码由你自己输入）。",
    "risk": "页面提示【访问异常 / 操作频繁】—— 建议在窗口里刷新或稍等片刻。",
    "login": "页面要求【重新登录】—— 请在窗口里重新扫码或验证码登录。",
    "unknown": "页面疑似出现人机验证 —— 请检查窗口里的提示并完成操作。",
}


def wait_for_human(page, kind: str, timeout: int = 600, logger=None) -> bool:




    logger = logger or log
    tip = _TIPS.get(kind, _TIPS["unknown"])
    print("\n" + "=" * 60)
    print("  ⚠️  触发小红书人机验证（%s），脚本已暂停" % kind)
    print("  " + tip)
    print("  完成后脚本会自动继续；脚本不会替你操作验证码。")
    print(f"  最长等待 {timeout} 秒。")
    print("=" * 60 + "\n")

    deadline = time.time() + timeout
    last_log = 0
    while time.time() < deadline:
        if not detect(page):
            logger.info("验证已通过，继续采集")
            time.sleep(random.uniform(1.5, 3.0))
            return True
        remain = int(deadline - time.time())
        if remain % 30 == 0 and remain != last_log and remain > 0:
            logger.info("  仍在等待人工验证…剩余 %s 秒", remain)
            last_log = remain
        try:
            page.wait_for_timeout(3000)
        except Exception:  
            time.sleep(3)
    return False


def guard(page, pacer: HumanPacer | None = None, label: str = "",
          wait_timeout: int = 600, logger=None) -> str:








    if pacer is not None:
        try:
            pacer.tick(label)
        except BudgetExhausted as err:
            (logger or log).warning(str(err))
            return "budget"

    if page is None:
        return ""

    kind = detect(page)
    if not kind:
        return ""

    if not wait_for_human(page, kind, wait_timeout, logger):
        raise RuntimeError(
            f"等待人工处理验证超时（{kind}），本次采集中止。"
            f"建议过一会儿再跑，或把 --months 调小以缩短采集量。"
        )
    if pacer is not None:
        pacer.cool_down()
    return "resumed"





def months_ago(n: int, now: datetime | None = None) -> datetime:

    now = now or datetime.now()
    index = now.month - 1 - n
    year = now.year + index // 12
    month = index % 12 + 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


def window_start_ms(months: int = 6, since: str = "") -> tuple[int, str]:





    if since:
        try:
            day = datetime.strptime(since.strip(), "%Y-%m-%d")
            return int(day.timestamp() * 1000), day.strftime("%Y-%m-%d")
        except ValueError as err:
            raise SystemExit(f"--since 格式应为 YYYY-MM-DD，收到：{since}（{err}）")
    if months <= 0:
        return 0, ""
    start = months_ago(months)
    return int(start.timestamp() * 1000), start.strftime("%Y-%m-%d")


def in_window(note: dict, start_ms: int) -> bool:





    if start_ms <= 0:
        return True
    ts = note.get("timestamp") or 0
    return ts == 0 or ts >= start_ms
