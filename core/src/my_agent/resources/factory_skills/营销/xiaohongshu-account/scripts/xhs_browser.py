# -*- coding: utf-8 -*-
"""浏览器会话管理：持久化登录态 / 接管本机 Chrome(CDP) / 反自动化指纹。

三级通道统一入口：
    BrowserSession(mode="persistent", headless=False)   # 复用本机 profile，已扫码则免登录
    BrowserSession(mode="cdp", cdp_port=9222)           # 接管用户手动启动的 Chrome
"""
from __future__ import annotations

import json
import random
import socket
import subprocess
import sys
import time
from pathlib import Path

from xhs_common import (BASE, COOKIE_FILE, PROFILE_DIR, STATE_FILE, VIEWPORTS,
                        ensure_runtime, log)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
window.chrome = window.chrome || { runtime: {} };
try {
  const originalQuery = window.navigator.permissions.query;
  window.navigator.permissions.query = (params) =>
    params && params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(params);
} catch (e) {}
try {
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter(parameter);
  };
} catch (e) {}
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--lang=zh-CN",
    "--disable-features=IsolateOrigins,site-per-process",
]


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def is_password_protected(page) -> bool:
    """判断是否撞上登录墙 / 风控拦截页。"""
    try:
        url = page.url or ""
        text = page.inner_text("body")[:800] if page.query_selector("body") else ""
    except Exception:  # noqa: BLE001
        return False
    if "/website-login" in url or "login" in url:
        return True
    for marker in ("登录", "验证", "滑动", "安全验证", "异常流量", "请完成安全验证"):
        if marker in text and len(text) < 400:
            return True
    return False


class BrowserSession:
    """上下文管理器：统一封装三种浏览器启动方式。"""

    def __init__(self, mode: str = "persistent", headless: bool = False,
                 cdp_port: int = 9222, slow_mo: int = 0):
        self.mode = mode
        self.headless = headless
        self.cdp_port = cdp_port
        self.slow_mo = slow_mo
        self._pw = None
        self.context = None
        self.browser = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        ensure_runtime()
        self._pw = sync_playwright().start()
        viewport = random.choice(VIEWPORTS)

        if self.mode == "cdp":
            if not port_open(self.cdp_port):
                raise RuntimeError(
                    f"未检测到 {self.cdp_port} 端口的 Chrome 调试服务。请先手动启动：\n"
                    f'  chrome.exe --remote-debugging-port={self.cdp_port} '
                    f'--user-data-dir="%LOCALAPPDATA%\\Google\\Chrome\\User Data"\n'
                    "然后在打开的浏览器里登录小红书网页版。"
                )
            self.browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.cdp_port}")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            log.info("已接管本机 Chrome(CDP:%s)，使用真实登录态", self.cdp_port)
        else:
            kwargs = {
                "user_data_dir": str(PROFILE_DIR),
                "headless": self.headless,
                "args": LAUNCH_ARGS,
                "viewport": {"width": viewport[0], "height": viewport[1]},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "slow_mo": self.slow_mo,
            }
            if STATE_FILE.exists() and not PROFILE_DIR.exists():
                kwargs["storage_state"] = str(STATE_FILE)
            self.context = self._pw.chromium.launch_persistent_context(**kwargs)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            log.info("已启动持久化浏览器 profile：%s", PROFILE_DIR)

        self.context.add_init_script(STEALTH_JS)
        try:
            self.page.set_default_timeout(45_000)
        except Exception:  # noqa: BLE001
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.save_state()
        except Exception as err:  # noqa: BLE001
            log.warning("保存登录态失败：%s", err)
        try:
            if self.mode == "cdp":
                if self.browser:
                    self.browser.close()
            elif self.context:
                self.context.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        return False

    def save_state(self) -> None:
        if self.mode == "cdp":
            return
        if not self.context:
            return
        try:
            self.context.storage_state(path=str(STATE_FILE))
            cookies = self.context.cookies()
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as err:  # noqa: BLE001
            log.warning("storage_state 保存跳过：%s", err)


def cookie_header() -> str:
    """把已保存的 cookie 拼成请求头字符串，供 HTTP 通道使用。"""
    if not COOKIE_FILE.exists():
        return ""
    try:
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    parts = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name, value = c.get("name"), c.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def has_login() -> bool:
    """是否已登录。

    只认 `web_session`。注意 `a1` / `webId` / `acw_tc` 是**访客 cookie**，
    每次打开小红书都会下发，把它们当登录凭证会导致「未登录却判定为已登录」，
    进而让扫码等待瞬间假成功。
    """
    return "web_session" in cookie_header()


def human_scroll(page, times: int = 3, min_px: int = 600, max_px: int = 1400,
                 recenter: bool = True) -> None:
    """模拟真人滚动，触发懒加载与分页接口。

    滚轮事件只作用于**光标所在元素**。Playwright 的光标默认停在 (0,0)，
    而小红书主页/详情页的滚动都发生在内部容器（.feeds-container / .note-scroller）
    而非窗口 —— 光标不在容器上时，滚轮滚不动、接口不翻页，会造成
    「列表抓不全 / 评论只有第一页」的数据偏差。所以每次滚动前先把光标
    移到视口中央（真人浏览时光标本来就在内容上）。

    `recenter=False` 供调用方**已经把光标定位到特定容器**（如详情页右侧评论面板）
    的场景 —— 此时不能把光标拉回中央，否则滚动又落在媒体面板上，翻页失效。
    """
    for _ in range(times):
        if recenter:
            try:
                vp = page.viewport_size or {"width": 1440, "height": 900}
                page.mouse.move(vp["width"] * random.uniform(0.4, 0.6),
                                vp["height"] * random.uniform(0.45, 0.65))
            except Exception:  # noqa: BLE001
                pass
        try:
            page.mouse.wheel(0, random.randint(min_px, max_px))
        except Exception:  # noqa: BLE001
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        time.sleep(random.uniform(0.8, 1.8))


def launch_chrome_debug(cdp_port: int = 9222) -> subprocess.Popen:
    """尝试为用户启动带调试端口的 Chrome（找不到时抛出明确指引）。"""
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    exe = next((p for p in candidates if p.exists()), None)
    if not exe:
        raise RuntimeError("未找到 Chrome/Edge，请手动启动带 --remote-debugging-port 的浏览器。")
    profile = Path.home() / "AppData" / "Local" / "XhsDebugProfile"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), f"--remote-debugging-port={cdp_port}", f"--user-data-dir={profile}",
           "--no-first-run", "--no-default-browser-check"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    if action == "check":
        print("cookie 已保存" if has_login() else "未检测到登录态")
    elif action == "open":
        proc = launch_chrome_debug(int(sys.argv[2]) if len(sys.argv) > 2 else 9222)
        print(f"Chrome 调试实例已启动 pid={proc.pid}，请在窗口中登录 {BASE}")
