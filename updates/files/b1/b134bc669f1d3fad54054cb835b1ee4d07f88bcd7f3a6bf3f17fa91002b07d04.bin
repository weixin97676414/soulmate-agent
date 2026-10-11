# -*- coding: utf-8 -*-
"""登录小红书网页版，保存登录态。

两种登录方式：

    python xhs_login.py                 # App 扫码（默认）
    python xhs_login.py --mode qr       # App 扫码
    python xhs_login.py --mode web      # 手机号 + 短信验证码（不用手机 App）
    python xhs_login.py --check         # 只检查登录态是否有效
    python xhs_login.py --reset         # 只清除登录态与缓存后退出

**每次登录前都会先清空历史登录态**（`reset_runtime()`）：
storage_state / cookies / 浏览器缓存 / browser_profile 全部删除，保证是全新会话。
本技能不提供免登录通道 —— 列表页的 noteId 只有登录态才下发。

`--mode web` 全程在浏览器窗口里完成，不需要掏手机：脚本只负责打开页面并切到
「手机号登录」标签，手机号与验证码由用户自己输入（敏感信息不经过本脚本）。

登录态写入 .runtime/storage_state.json 与 .runtime/cookies.json，
后续 xhs_crawl.py 的 persistent / http 通道会自动复用。
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from xhs_common import BASE, COOKIE_FILE, STATE_FILE, ensure_runtime, log

#: 可能出现在登录面板上的「手机号登录」入口文案
SMS_TAB_TEXTS = ("手机号登录", "手机登录", "短信登录", "验证码登录")
PHONE_PLACEHOLDERS = ("手机号", "请输入手机号", "输入手机号")


def wait_for_login(page, timeout: int = 300, hint: str = "") -> bool:
    """轮询 cookie，等待 web_session 出现即视为登录成功。

    只认 `web_session`：`a1`、`webId`、`acw_tc` 等是访客 cookie，打开页面就有，
    若把它们当凭证会导致「还没登录就判定成功」。
    """
    deadline = time.time() + timeout
    log.info("等待登录完成（最长 %s 秒）%s", timeout, hint)
    last_log = 0.0
    while time.time() < deadline:
        try:
            cookies = {c.get("name") for c in page.context.cookies()}
            if "web_session" in cookies:
                return True
        except Exception:  # noqa: BLE001
            pass
        remain = int(deadline - time.time())
        if remain % 30 == 0 and remain != last_log and remain > 0:
            log.info("  仍在等待…剩余 %s 秒", remain)
            last_log = remain
        page.wait_for_timeout(2000)
    return False


def open_login_panel(page, prefer_sms: bool = True) -> bool:
    """打开登录面板。`prefer_sms=True` 时额外切到「手机号登录」标签。

    扫码模式（`prefer_sms=False`）只负责把登录面板弹出来，让二维码自己显示，
    **不要**切到手机号标签——切走之后二维码就消失了。
    两种模式下失败都不影响用户手动操作。
    """
    try:
        page.goto(f"{BASE}/explore", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as err:  # noqa: BLE001
        log.warning("打开首页失败：%s", str(err)[:100])
        return False

    # 1) 若登录面板未自动弹出，点一下「登录」
    for selector in ("text=登录", "button:has-text('登录')", ".login-btn", "#login-btn"):
        try:
            page.click(selector, timeout=2500)
            page.wait_for_timeout(1200)
            break
        except Exception:  # noqa: BLE001
            continue

    if not prefer_sms:
        log.info("已弹出登录面板，请使用小红书 App 扫码")
        return True

    # 2) 切到手机号登录标签
    for text in SMS_TAB_TEXTS:
        try:
            page.click(f"text={text}", timeout=2000)
            page.wait_for_timeout(1000)
            log.info("已切换到「%s」", text)
            return True
        except Exception:  # noqa: BLE001
            continue

    # 3) 兜底：有些版本是 tab 形式
    for selector in (".tab-item:has-text('手机')", "[class*='phone']", "li:has-text('手机')"):
        try:
            page.click(selector, timeout=2000)
            page.wait_for_timeout(1000)
            log.info("已通过选择器切到手机号登录")
            return True
        except Exception:  # noqa: BLE001
            continue

    log.warning("未能自动切换到「手机号登录」标签，请在窗口里手动点一下")
    return False


def interactive_login(page, mode: str = "qr", timeout: int = 600) -> bool:
    """在一个**已打开的**浏览器页面上引导用户完成登录，返回是否成功。

    供 `xhs_crawl.py` 复用同一个会话（避免为登录再开一个浏览器窗口）。
    调用方负责保存登录态（`session.save_state()`）。
    """
    if mode == "qr":
        open_login_panel(page, prefer_sms=False)
        banner = [
            "=" * 58,
            "  请在弹出的浏览器窗口里用小红书 App 扫码登录：",
            "    1) 打开小红书 App → 左上角「扫一扫」",
            "    2) 扫描窗口中的二维码 → 手机上点「确认登录」",
            "  登录成功后脚本会自动继续抓取（本窗口不要手动关闭）。",
            "=" * 58,
        ]
        hint = "（用小红书 App 扫码）"
    else:
        open_login_panel(page, prefer_sms=True)
        banner = [
            "=" * 58,
            "  请在弹出的浏览器窗口里完成登录：",
            "    1) 输入手机号 → 点「获取验证码」",
            "    2) 收到短信后填入验证码 → 点「登录」",
            "  手机号与验证码由你自己输入，不会经过本脚本。",
            "=" * 58,
        ]
        hint = ""
    print("\n" + "\n".join(banner) + "\n")

    if not wait_for_login(page, timeout, hint):
        log.error("登录超时（%s 秒）。可重跑本命令，或改用 CDP 通道："
                  "python xhs_browser.py open 9222", timeout)
        return False
    page.wait_for_timeout(2000)
    return True


def check_only() -> int:
    from xhs_browser import has_login
    if has_login():
        log.info("登录态有效（%s）", COOKIE_FILE)
        return 0
    log.warning("未检测到登录态，请执行 `python xhs_login.py --mode qr`")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="qr", choices=["qr", "web"],
                        help="qr=App 扫码（默认）；web=手机号+验证码")
    parser.add_argument("--timeout", type=int, default=600, help="等待登录完成的秒数")
    parser.add_argument("--check", action="store_true", help="只检查登录态")
    parser.add_argument("--reset", action="store_true",
                        help="只清除登录态与浏览器缓存后退出（不登录）")
    args = parser.parse_args()

    if args.reset:
        from xhs_common import reset_runtime
        result = reset_runtime(logger=log)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.check:
        return check_only()

    ensure_runtime()
    # 本技能不复用历史登录态：每次登录前先清干净，保证是全新会话
    from xhs_common import reset_runtime
    reset_runtime(logger=log)
    from xhs_browser import BrowserSession

    with BrowserSession(mode="persistent", headless=False) as session:
        page = session.page
        if not interactive_login(page, args.mode, args.timeout):
            return 1
        try:
            page.goto(f"{BASE}/user/profile/self", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        except Exception:  # noqa: BLE001
            pass
        session.save_state()

    log.info("登录态已保存：%s / %s", STATE_FILE, COOKIE_FILE)
    return 0


if __name__ == "__main__":
    from xhs_env import ensure_ready
    ensure_ready(need_browser=True)      # 扫码必须有浏览器，缺就自动装
    raise SystemExit(main())
