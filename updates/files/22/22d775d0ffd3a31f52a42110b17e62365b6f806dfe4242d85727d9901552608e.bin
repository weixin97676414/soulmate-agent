# -*- coding: utf-8 -*-
"""反风控：拟人节奏 + 遇验证暂停等人工处理。

设计原则（**合规底线**）：

- **不破解、不绕过验证码**。检测到滑块 / 短信 / 风控页就停下来，把浏览器交给用户，
  等他人工完成，脚本再继续 —— 见 `wait_for_human()`。
- **宁可慢、宁可少，也不要把账号或 IP 玩坏**。靠三件事降低触发概率：
  1. 缩短采集窗口（近半年，而不是全量）—— 请求量直接砍掉一大半；
  2. 拟人节奏：间隔随机、批量长休、单任务总动作预算；
  3. 见好就收：预算用尽或反复触发验证时主动收工，并在 `meta.stopped_reason` 里说清。

用法（在 xhs_crawl.py 里）：

    pacer = HumanPacer(level=args.pace)
    guard(page, pacer)             # 每个页面动作前调一次
"""
from __future__ import annotations

import calendar
import random
import re
import time
from datetime import datetime

from xhs_common import log

# --------------------------------------------------------------------------- #
# 1. 挑战检测
# --------------------------------------------------------------------------- #
#: 触发风控时页面上会出现的文案。判定要求页面正文较短（验证页通常只有一两行），
#: 避免把笔记正文中恰好出现的「验证码」三个字误判成挑战。
_TEXT_MARKS = [
    ("slider", ("滑动验证", "拖动滑块", "向右滑动", "请完成滑动", "完成拼图")),
    ("sms", ("短信验证", "安全验证", "身份验证", "请输入验证码")),
    ("risk", ("异常访问", "访问受限", "操作频繁", "请求过于频繁", "请稍后再试",
              "系统繁忙", "流量异常")),
    ("login", ("扫码登录", "登录后查看", "登录查看更多")),
]

#: 验证组件的 DOM 选择器（比文案更可靠）
_CHALLENGE_SELECTORS = (
    ".verify-page", "#captcha", ".red-captcha", ".slider-verify",
    "iframe[src*='captcha']", "iframe[src*='verify']",
    ".reds-mask", "[class*='captcha']", "[class*='verify-page']",
)

#: 页面正文短于这个长度才按文案判定为挑战页
_SHORT_PAGE = 600


def detect(page) -> str:
    """判断当前页面是否撞上人机验证 / 风控。

    返回 `""` 表示正常；否则返回 `slider` / `sms` / `risk` / `login` / `unknown`。
    """
    url = ""
    try:
        url = page.url or ""
    except Exception:  # noqa: BLE001
        pass
    if "/website-login" in url:
        return "login"

    for selector in _CHALLENGE_SELECTORS:
        try:
            if page.query_selector(selector):
                return "slider"
        except Exception:  # noqa: BLE001
            continue

    text = ""
    try:
        if page.query_selector("body"):
            text = (page.inner_text("body") or "")[:_SHORT_PAGE]
    except Exception:  # noqa: BLE001
        pass
    if not text:
        return ""

    for kind, marks in _TEXT_MARKS:
        for mark in marks:
            if mark in text:
                # 登录类文案在正常长页面里也常见，只在短页面时才算挑战
                if kind == "login" and len(text) > 200:
                    continue
                return kind

    if len(text) < 200 and re.search(r"验证|安全|滑块", text):
        return "unknown"
    return ""


# --------------------------------------------------------------------------- #
# 2. 拟人节奏
# --------------------------------------------------------------------------- #
#: 三档节奏。slow 用于粉丝量大/已出现过风控的账号
PACE_LEVELS = {
    "slow":   {"gap": (4.0, 9.0),  "every": 5,  "rest": (45, 90),  "budget": 120},
    "normal": {"gap": (2.5, 6.0),  "every": 8,  "rest": (25, 55),  "budget": 200},
    "fast":   {"gap": (1.5, 3.5),  "every": 12, "rest": (12, 25),  "budget": 320},
}


class HumanPacer:
    """拟人节奏控制器。

    真人浏览不会匀速翻页：看几屏会停一会儿、偶尔发呆、总时长也有限。
    这里用「随机间隔 + 批量长休 + 总预算」三件事模拟这种不规律性。
    """

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
        """每个页面动作前调用一次：随机间隔，到点长休，超预算抛异常。"""
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
        """风控后额外降温：比普通长休更久。"""
        seconds = seconds or random.uniform(60, 120)
        log.info("  [降温] 风控后额外等待 %.0f 秒", seconds)
        time.sleep(seconds)

    def remaining(self) -> int:
        return max(0, self.budget - self.actions)


class BudgetExhausted(RuntimeError):
    """单任务动作预算用尽。调用方应把它当成「正常收工」而非崩溃。"""


# --------------------------------------------------------------------------- #
# 3. 遇验证：暂停 + 等人工处理
# --------------------------------------------------------------------------- #
_TIPS = {
    "slider": "页面出现【滑动验证】—— 请在弹出的浏览器窗口里手动拖一下滑块。",
    "sms": "页面出现【短信/身份验证】—— 请在窗口里完成验证（手机号与验证码由你自己输入）。",
    "risk": "页面提示【访问异常 / 操作频繁】—— 建议在窗口里刷新或稍等片刻。",
    "login": "页面要求【重新登录】—— 请在窗口里重新扫码或验证码登录。",
    "unknown": "页面疑似出现人机验证 —— 请检查窗口里的提示并完成操作。",
}


def wait_for_human(page, kind: str, timeout: int = 600, logger=None) -> bool:
    """在打开的浏览器里等用户完成验证，**不破解、不绕过**。

    返回 True 表示验证已消失（可以继续）；False 表示超时。
    """
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
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return False


def guard(page, pacer: HumanPacer | None = None, label: str = "",
          wait_timeout: int = 600, logger=None) -> str:
    """每个页面动作前调一次：先控节奏，再查验证。

    `page=None` 时只控节奏、不检测验证（HTTP 通道没有页面对象，
    它自己会用 `WALL_MARKERS` 判断登录墙）。

    返回 `""` 表示可以继续；`"budget"` 表示预算用尽（调用方应正常收工）；
    `"resumed"` 表示刚经历一次人工验证并已恢复。
    """
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


# --------------------------------------------------------------------------- #
# 4. 时间窗口
# --------------------------------------------------------------------------- #
def months_ago(n: int, now: datetime | None = None) -> datetime:
    """n 个月前的今天（自动处理月末，例如 3 月 31 日往前推 1 个月得到 2 月 28/29 日）。"""
    now = now or datetime.now()
    index = now.month - 1 - n
    year = now.year + index // 12
    month = index % 12 + 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


def window_start_ms(months: int = 6, since: str = "") -> tuple[int, str]:
    """计算采集窗口起点（毫秒时间戳 + 可读日期）。

    `--since YYYY-MM-DD` 优先；否则按 `--months N`（默认 6 个月 = 近半年）。
    `months <= 0` 表示不限（全量），返回 0。
    """
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
    """笔记是否落在窗口内。

    **没有时间戳的笔记默认保留** —— 没有证据说明它超出窗口，
    直接丢弃会造成静默的数据缺口（比多抓几条危险得多）。
    """
    if start_ms <= 0:
        return True
    ts = note.get("timestamp") or 0
    return ts == 0 or ts >= start_ms
