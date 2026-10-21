



























from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from ..errors import SkillExecutionError

logger = logging.getLogger(__name__)


_BLOCKER_HINTS = (
    "login", "sign in", "signin", "log in", "captcha", "verification",
    "verify", "2fa", "two-factor", "authenticate",
    "登录", "验证码", "验证", "扫码", "身份验证",
)


_EDGE_PATHS = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
)
_CHROME_PATHS = (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),)


def _apply_frozen_shim() -> None:

    if not getattr(sys, "frozen", False):
        return
    import playwright  

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    driver_dir = Path(meipass) / "playwright" / "driver"
    if (driver_dir / "node.exe").exists():
        
        
        playwright.__file__ = str(Path(meipass) / "playwright" / "__init__.py")
    
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


def _detect_channel() -> str | None:

    for candidate in _EDGE_PATHS:
        if candidate.exists():
            return "msedge"
    for candidate in _CHROME_PATHS:
        if candidate.exists():
            return "chrome"
    
    if shutil.which("msedge") or shutil.which("microsoft-edge"):
        return "msedge"
    if shutil.which("chrome") or shutil.which("google-chrome"):
        return "chrome"
    return None


class BrowserSession:









    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pw = None
        self._context = None
        self._pages: dict[str, Any] = {}
        self._profile_dir: Path | None = None

    
    
    
    async def ensure(self, profile_dir: Path) -> Any:














        async with self._lock:
            if self._context is not None and not self._is_alive(self._context):
                logger.info("浏览器已不可用（被关闭或进程退出），引用已清空，准备重新拉起")
                self._context = None
                self._pages.clear()
            if self._context is not None:
                return self._context

            _apply_frozen_shim()
            channel = _detect_channel()
            if channel is None:
                raise SkillExecutionError(
                    "没有检测到系统里的 Edge 或 Chrome 浏览器，无法使用浏览器能力。"
                    "请安装 Microsoft Edge 或 Google Chrome 后重试。"
                )

            from playwright.async_api import async_playwright

            self._profile_dir = profile_dir
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            self._pw = await async_playwright().start()
            try:
                self._context = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._profile_dir),
                    channel=channel,
                    headless=False,
                    
                    no_viewport=True,
                )
            except Exception as exc:
                
                await self._pw.stop()
                self._pw = None
                raise SkillExecutionError(
                    f"浏览器启动失败（channel={channel}）：{exc}。"
                    "请确认 Edge/Chrome 未被其他进程占用或损坏。"
                ) from exc

            
            self._context.on("close", self._on_context_closed)
            self._pages = {page: page for page in self._context.pages}
            logger.info("浏览器已启动（channel=%s，profile=%s）", channel, profile_dir)
            return self._context

    def _on_context_closed(self) -> None:





        self._context = None
        self._pages.clear()
        logger.info("浏览器已被关闭，引用已清空；下次使用时会自动重新拉起")

    @staticmethod
    def _is_alive(context: Any) -> bool:

        try:
            _ = context.pages
            return True
        except Exception:  
            return False

    @staticmethod
    def looks_closed(exc: BaseException) -> bool:





        text = str(exc).lower()
        return any(
            hint in text
            for hint in (
                "has been closed",
                "target closed",
                "browser has been closed",
                "context has been closed",
                "closed",
            )
        )

    async def close(self) -> None:

        async with self._lock:
            self._pages.clear()
            if self._context is not None:
                try:
                    await self._context.close()
                except Exception as exc:  
                    logger.debug("关闭浏览器 context 失败：%s", exc)
                self._context = None
            if self._pw is not None:
                try:
                    await self._pw.stop()
                except Exception as exc:  
                    logger.debug("停止 playwright 驱动失败：%s", exc)
                self._pw = None

    
    
    
    async def page(self, context: Any, label: str | None) -> Any:






        if label and label in self._pages:
            cached = self._pages[label]
            if not self._is_page_alive(cached):
                logger.info("标签页「%s」已被关闭，重新打开一个", label)
                self._pages.pop(label, None)
            else:
                return cached
        if context.pages:
            live = [item for item in context.pages if self._is_page_alive(item)]
            if live:
                page = live[-1]
                if label:
                    self._pages[label] = page
                return page
        page = await context.new_page()
        if label:
            self._pages[label] = page
        return page

    @staticmethod
    def _is_page_alive(page: Any) -> bool:
        try:
            return not page.is_closed()
        except Exception:  
            return False

    async def open(self, context: Any, url: str, label: str | None) -> dict[str, Any]:
        if label and label in self._pages:
            page = self._pages[label]
        else:
            page = await context.new_page()
            if label:
                self._pages[label] = page
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        return {"url": page.url, "title": await page.title(), "label": label}

    async def list_tabs(self, context: Any) -> list[dict[str, Any]]:
        tabs = []
        for page in context.pages:
            try:
                title = await page.title()
            except Exception:  
                title = ""
            tabs.append({"url": page.url, "title": title})
        return tabs

    async def close_tab(self, context: Any, label: str | None) -> None:
        page = await self.page(context, label)
        await page.close()
        if label:
            self._pages.pop(label, None)

    
    
    
    async def read_text(self, page: Any) -> str:

        for selector in ("article", "main", "body"):
            loc = page.locator(selector).first
            try:
                text = (await loc.inner_text(timeout=3000)).strip()
            except Exception:  
                continue
            if text:
                return text
        return ""

    async def snapshot(self, page: Any) -> dict[str, Any]:





        elements: list[dict[str, Any]] = []
        for role in (
            "button", "link", "textbox", "combobox", "checkbox",
            "radio", "tab", "menuitem", "heading",
        ):
            locs = page.get_by_role(role)
            count = await locs.count()
            for index in range(count):
                loc = locs.nth(index)
                try:
                    if not await loc.is_visible():
                        continue
                    name = (
                        (await loc.get_attribute("aria-label"))
                        or (await loc.inner_text())
                        or (await loc.get_attribute("placeholder"))
                        or (await loc.get_attribute("name"))
                        or ""
                    )
                except Exception:  
                    name = ""
                name = " ".join(str(name).strip().split())
                if not name:
                    continue
                elements.append(
                    {"ref": len(elements) + 1, "role": role, "name": name[:160]}
                )
        return {
            "url": page.url,
            "title": await page.title(),
            "element_count": len(elements),
            "elements": elements,
        }

    async def screenshot(self, page: Any, target: Path) -> None:
        await page.screenshot(path=str(target), full_page=True, type="png")

    
    
    
    async def act(
        self, page: Any, *, action: str, target: str | None, value: str | None
    ) -> dict[str, Any]:

        if action == "goto":
            await page.goto(target or "", wait_until="domcontentloaded", timeout=45_000)
            return {"url": page.url}
        if action == "back":
            await page.go_back()
            return {"url": page.url}
        if action == "press":
            await page.keyboard.press(value or "Enter")
            return {"pressed": value or "Enter"}
        if action == "scroll":
            delta = 800 if (value or "down") == "down" else -800
            await page.mouse.wheel(0, delta)
            return {"scrolled": value or "down"}

        if action == "click":
            loc = await self._locate(page, target or "")
            if loc is None:
                raise SkillExecutionError(
                    f"页面上没找到可点击的「{target}」。可能页面已经变化，"
                    "请先调用 browser_snapshot 看看当前有哪些元素。"
                )
            await loc.click(timeout=10_000)
        elif action == "fill":
            loc = await self._locate_input(page, target or "")
            if loc is None:
                raise SkillExecutionError(
                    f"页面上没找到输入框「{target}」。可能页面已经变化，"
                    "请先调用 browser_snapshot 看看当前有哪些元素。"
                )
            await loc.fill(value or "", timeout=10_000)
        elif action == "type":
            loc = await self._locate_input(page, target or "") if target else None
            if loc is not None:
                await loc.click(timeout=5_000)
            await page.keyboard.type(value or "")
        else:
            raise SkillExecutionError(
                f"不支持的动作「{action}」。可用：goto / back / click / fill / type / press / scroll。"
            )

        return {"url": page.url, "title": await page.title()}

    
    
    
    @staticmethod
    async def _locate(page: Any, target: str) -> Any:
        
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=target)
            try:
                if await loc.count():
                    return loc.first
            except Exception:  
                continue
        for exact in (True, False):
            loc = page.get_by_text(target, exact=exact)
            try:
                if await loc.count():
                    return loc.first
            except Exception:  
                continue
        return None

    @staticmethod
    async def _locate_input(page: Any, target: str) -> Any:
        makers = (
            lambda: page.get_by_label(target),
            lambda: page.get_by_placeholder(target),
            lambda: page.get_by_role("textbox", name=target),
        )
        for maker in makers:
            loc = maker()
            try:
                if await loc.count():
                    return loc.first
            except Exception:  
                continue
        return None

    @staticmethod
    async def detect_blocker(page: Any) -> str | None:





        url = (page.url or "").lower()
        try:
            title = (await page.title() or "").lower()
        except Exception:  
            title = ""
        for hint in _BLOCKER_HINTS:
            if hint in url or hint in title:
                return f"页面疑似需要人工处理（命中关键词「{hint}」）：{page.url}"
        return None



browser = BrowserSession()
