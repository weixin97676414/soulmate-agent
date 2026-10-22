# -*- coding: utf-8 -*-




















from __future__ import annotations

import argparse
import json
import sys
import time

from xhs_common import BASE, COOKIE_FILE, STATE_FILE, ensure_runtime, log


SMS_TAB_TEXTS = ("手机号登录", "手机登录", "短信登录", "验证码登录")
PHONE_PLACEHOLDERS = ("手机号", "请输入手机号", "输入手机号")


def wait_for_login(page, timeout: int = 300, hint: str = "") -> bool:





    deadline = time.time() + timeout
    log.info("等待登录完成（最长 %s 秒）%s", timeout, hint)
    last_log = 0.0
    while time.time() < deadline:
        try:
            cookies = {c.get("name") for c in page.context.cookies()}
            if "web_session" in cookies:
                return True
        except Exception:  
            pass
        remain = int(deadline - time.time())
        if remain % 30 == 0 and remain != last_log and remain > 0:
            log.info("  仍在等待…剩余 %s 秒", remain)
            last_log = remain
        page.wait_for_timeout(2000)
    return False


def open_login_panel(page, prefer_sms: bool = True) -> bool:






    try:
        page.goto(f"{BASE}/explore", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as err:  
        log.warning("打开首页失败：%s", str(err)[:100])
        return False

    
    for selector in ("text=登录", "button:has-text('登录')", ".login-btn", "#login-btn"):
        try:
            page.click(selector, timeout=2500)
            page.wait_for_timeout(1200)
            break
        except Exception:  
            continue

    if not prefer_sms:
        log.info("已弹出登录面板，请使用小红书 App 扫码")
        return True

    
    for text in SMS_TAB_TEXTS:
        try:
            page.click(f"text={text}", timeout=2000)
            page.wait_for_timeout(1000)
            log.info("已切换到「%s」", text)
            return True
        except Exception:  
            continue

    
    for selector in (".tab-item:has-text('手机')", "[class*='phone']", "li:has-text('手机')"):
        try:
            page.click(selector, timeout=2000)
            page.wait_for_timeout(1000)
            log.info("已通过选择器切到手机号登录")
            return True
        except Exception:  
            continue

    log.warning("未能自动切换到「手机号登录」标签，请在窗口里手动点一下")
    return False


def interactive_login(page, mode: str = "qr", timeout: int = 600) -> bool:





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
        except Exception:  
            pass
        session.save_state()

    log.info("登录态已保存：%s / %s", STATE_FILE, COOKIE_FILE)
    return 0


if __name__ == "__main__":
    from xhs_env import ensure_ready
    ensure_ready(need_browser=True)      
    raise SystemExit(main())
